"""
Gemini client wrapper: model init, availability check, JSON-mode call helper.

This module is the single place that talks to ``google.generativeai``. Feature
modules (summarization, compose_assist, classification, chat, similarity) take
an ``AIClient`` instance and call its ``model`` / ``generate_json`` / ``parse_json_response``.
Switching providers later (e.g. Gemini -> Anthropic) only touches this file.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

import google.generativeai as genai


class AIClient:
    """Holds the Gemini model plus init/availability/JSON-call helpers."""

    def __init__(self, model_name: Optional[str] = None):
        # `model_name` (optional) is the PREFERRED Gemini model id to try first; callers
        # that care (e.g. workflow generation) pass settings.workflow_generation_model so
        # the model is config/env-driven. When None, the built-in default order is used.
        self.api_key = None
        self.model = None  # GenerativeModel instance
        self.model_name = None
        self._preferred_model = (model_name or "").strip() or None
        self._initialized = False
        self._init_error = None
        self._try_initialize()

    def _try_initialize(self):
        """Try to initialize the Gemini API using GenerativeModel."""
        # Reload settings to get latest API key
        from app.config import settings
        self.api_key = settings.gemini_api_key

        if not self.api_key:
            print("⚠️ GEMINI_API_KEY not configured in settings")
            self._init_error = "API key not configured"
            self.model = None
            self._initialized = False
            return

        print(f"🔑 Loading API key: {self.api_key[:10]}...{self.api_key[-5:]} (length: {len(self.api_key)})")

        try:
            # Configure genai with API key (using GenerativeModel API)
            genai.configure(api_key=self.api_key)
            print("✅ Configured genai with API key")

            # Default model order (newest first). The 2.5/2.0/1.5 generations were
            # retired by Google (404 NOT_FOUND); gemini-flash-latest is a rolling
            # alias so this list survives the next retirement too.
            default_models = ["gemini-3.5-flash", "gemini-flash-latest", "gemini-3.1-flash-lite"]
            # A caller-preferred model (e.g. WORKFLOW_GENERATION_MODEL=gemini-3.5-flash)
            # is tried FIRST; the logs below print which model actually initialized, so a
            # clean model-vs-model comparison is visible even if a fallback is hit.
            if self._preferred_model:
                models_to_try = [self._preferred_model] + [m for m in default_models if m != self._preferred_model]
            else:
                models_to_try = default_models

            for model_to_try in models_to_try:
                try:
                    # Test the API key with a simple call using GenerativeModel
                    print(f"🔄 Testing API key with {model_to_try}...")
                    self.model = genai.GenerativeModel(model_to_try)
                    test_response = self.model.generate_content("Say OK")
                    if test_response and hasattr(test_response, 'text'):
                        print(f"✅ API key test successful with {model_to_try}: {test_response.text[:50]}")
                        self.model_name = model_to_try
                        self._initialized = True
                        break
                    else:
                        print(f"⚠️ API key test returned no response for {model_to_try}")
                        continue
                except Exception as e:
                    error_msg = str(e)
                    print(f"⚠️ {model_to_try} failed: {type(e).__name__}: {error_msg}")

                    # If it's an API key error, stop trying
                    if "API key" in error_msg or "API_KEY" in error_msg or "expired" in error_msg.lower() or "invalid" in error_msg.lower():
                        self._init_error = f"API key error: {error_msg}"
                        self.model = None
                        self._initialized = False
                        return

                    # If it's a model not found error, try next model
                    if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
                        print(f"   Model {model_to_try} not available, trying next...")
                        continue

                    # For other errors, try next model
                    continue

            if not self._initialized:
                print("❌ All Gemini models failed to initialize")
                self._init_error = "All models failed to initialize. Check backend logs for details."
                self.model = None
                self._initialized = False
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Error initializing Gemini API: {type(e).__name__}: {error_msg}")
            import traceback
            traceback.print_exc()
            self._init_error = error_msg
            self.model = None

    def is_available(self) -> bool:
        """Check if AI service is available (API key configured)."""
        # Always re-check API key in case it was set after initialization
        from app.config import settings
        current_api_key = settings.gemini_api_key

        # If API key changed or service not initialized, re-initialize
        if current_api_key != self.api_key or not self._initialized:
            if current_api_key:
                print(f"🔄 Re-initializing AI service with API key: {current_api_key[:10]}...{current_api_key[-5:]}")
                self._try_initialize()
            else:
                print("⚠️ No API key available, AI service unavailable")
                self.model = None
                self._initialized = False

        return self.model is not None and self._initialized

    async def generate_json(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Call Gemini with a prompt that is expected to return pure JSON.

        Centralises error-handling and JSON parsing. If the response is not
        valid JSON we try to salvage the content, otherwise we return None so
        callers can apply sensible fallbacks.
        """
        if not self.is_available():
            print("❌ AI service not available in generate_json")
            return None

        raw_text = ""
        try:
            print(f"🔄 Calling Gemini API with prompt length: {len(prompt)}")
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.model.generate_content(prompt)
            )

            if not response:
                print("❌ Gemini API returned None response")
                return None

            raw_text = response.text if hasattr(response, "text") else str(response)
            if not raw_text:
                print("❌ Gemini API returned empty text")
                return None

            raw_text = raw_text.strip()
            print(f"✅ Got response from Gemini (length: {len(raw_text)})")

            # Some models wrap JSON in markdown fences; strip them if present.
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```", 2)
                if len(raw_text) >= 3:
                    raw_text = raw_text[1] if "{" in raw_text[1] else raw_text[2]
                else:
                    raw_text = raw_text[-1]
            raw_text = raw_text.strip("`\n ")

            # Remove "json" prefix if present (some models return "json\n{...}")
            if raw_text.lower().startswith("json"):
                json_start = raw_text.find("{")
                if json_start == -1:
                    json_start = raw_text.find("[")
                if json_start != -1:
                    raw_text = raw_text[json_start:]
                else:
                    lines = raw_text.split("\n", 1)
                    if len(lines) > 1:
                        raw_text = lines[1].strip()

            try:
                parsed = json.loads(raw_text)
            except json.JSONDecodeError:
                # Recovery: Gemini sometimes emits a bare comma-separated list
                # of objects, possibly truncated mid-stream. Peel complete
                # objects with raw_decode so we keep whatever fully parsed.
                stripped = raw_text.strip()
                # 1. Strip leading '[' that's missing a closing ']'
                if stripped.startswith("["):
                    stripped = stripped[1:]
                objects: List[Dict[str, Any]] = []
                decoder = json.JSONDecoder()
                idx = 0
                n = len(stripped)
                while idx < n:
                    while idx < n and stripped[idx] in " \t\n\r,":
                        idx += 1
                    if idx >= n:
                        break
                    if stripped[idx] not in "{[":
                        idx += 1
                        continue
                    try:
                        obj, end_idx = decoder.raw_decode(stripped, idx)
                        if isinstance(obj, list):
                            objects.extend(o for o in obj if isinstance(o, dict))
                        elif isinstance(obj, dict):
                            objects.append(obj)
                        idx = end_idx
                    except json.JSONDecodeError:
                        # Likely the tail object got truncated mid-stream;
                        # stop and return whatever complete objects we collected.
                        break

                if objects:
                    parsed = objects
                    print(f"✅ Recovered {len(objects)} JSON object(s) via raw_decode peel")
                else:
                    raise
            print("✅ Successfully parsed JSON from Gemini")
            return parsed
        except json.JSONDecodeError as e:
            print(f"❌ JSON decode error in generate_json: {e}")
            print(f"   Raw response (first 500 chars): {raw_text[:500]}")
            import traceback
            traceback.print_exc()
            return None
        except Exception as e:
            print(f"❌ Error in generate_json / Gemini API call: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def parse_json_response(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from AI response, handling markdown fences and prefixes."""
        try:
            # Remove markdown fences
            if raw_text.startswith("```"):
                parts = raw_text.split("```", 2)
                if len(parts) >= 3:
                    raw_text = parts[1] if "{" in parts[1] else parts[2]
                else:
                    raw_text = parts[-1]
            raw_text = raw_text.strip("`\n ")

            # Remove "json" prefix if present
            if raw_text.lower().startswith("json"):
                json_start = raw_text.find("{")
                if json_start != -1:
                    raw_text = raw_text[json_start:]
                else:
                    lines = raw_text.split("\n", 1)
                    if len(lines) > 1:
                        raw_text = lines[1].strip()

            return json.loads(raw_text)
        except Exception as e:
            print(f"Error parsing JSON response: {e}")
            return None
