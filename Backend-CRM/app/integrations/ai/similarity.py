"""Thread similarity analysis for the combine-threads workflow."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from app.integrations.ai.client import AIClient
from app.integrations.ai.formatters import format_thread_messages_for_analysis


async def analyze_thread_similarity(
    client: AIClient,
    thread1_data: Dict[str, Any],
    thread2_data: Dict[str, Any],
    thread1_messages: List[Dict[str, Any]],
    thread2_messages: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Analyze similarity between two threads and suggest if they should be combined.

    Returns dict with should_combine, similarity_score, reasoning, factors, recommendation.
    """
    if not client.is_available():
        print("⚠️ AI service not available for thread similarity analysis")
        return None

    try:
        thread1_text = format_thread_messages_for_analysis(thread1_messages)
        thread2_text = format_thread_messages_for_analysis(thread2_messages)

        prompt = f"""Analyze two threads from a clinical trials CRM system and determine if they should be combined.

Thread 1:
- Title: {thread1_data.get('title', 'N/A')}
- Type: {thread1_data.get('thread_type', 'N/A')}
- Patient ID: {thread1_data.get('related_patient_id', 'N/A')}
- Study ID: {thread1_data.get('related_study_id', 'N/A')}
- Description: {thread1_data.get('description', 'N/A')}
- Messages:
{thread1_text}

Thread 2:
- Title: {thread2_data.get('title', 'N/A')}
- Type: {thread2_data.get('thread_type', 'N/A')}
- Patient ID: {thread2_data.get('related_patient_id', 'N/A')}
- Study ID: {thread2_data.get('related_study_id', 'N/A')}
- Description: {thread2_data.get('description', 'N/A')}
- Messages:
{thread2_text}

Analyze if these threads should be combined. Consider:
1. Same patient (if patient IDs match or are mentioned) - HIGH PRIORITY
2. Same title - HIGH PRIORITY (if titles match exactly, strongly recommend combining)
3. Same conversation (if conversation_id matches) - HIGH PRIORITY
4. Same medical condition/side effect/disease
5. Same topic or issue
6. Related discussions that would benefit from being together
7. Temporal proximity (recent related discussions)

IMPORTANT RULES:
- If titles are EXACTLY the same (case-insensitive), recommend combining with score 80-100
- If conversation_id is the same AND titles are similar, recommend combining with score 70-90
- If patient IDs match AND titles are similar, recommend combining with score 70-90
- Be generous with recommendations when there are clear matches

Return a JSON object with this exact structure:
{{
    "should_combine": true/false,
    "similarity_score": 0-100,
    "reasoning": "Detailed explanation of why they should or shouldn't be combined",
    "factors": ["Factor 1", "Factor 2", ...],
    "recommendation": "strong" | "moderate" | "weak" | "no"
}}

Be reasonable: recommend combining when there are clear matches (same title, same conversation, same patient, or similar topics)."""

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.model.generate_content(prompt)
        )

        if not response:
            return None

        raw_text = response.text if hasattr(response, 'text') else str(response)
        raw_text = raw_text.strip()

        parsed = client.parse_json_response(raw_text)
        if parsed:
            if 'should_combine' in parsed and 'similarity_score' in parsed:
                return {
                    'should_combine': bool(parsed['should_combine']),
                    'similarity_score': float(parsed.get('similarity_score', 0)),
                    'reasoning': parsed.get('reasoning', ''),
                    'factors': parsed.get('factors', []),
                    'recommendation': parsed.get('recommendation', 'no')
                }

        return None

    except Exception as e:
        print(f"Error in analyze_thread_similarity: {e}")
        import traceback
        traceback.print_exc()
        return None
