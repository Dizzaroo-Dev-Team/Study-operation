"""Document-grounded chat + general-purpose chat with history."""
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

import aiofiles
import google.generativeai as genai

from app.integrations.ai.client import AIClient


async def chat_with_document(
    client: AIClient,
    question: str,
    document_path: Optional[str] = None,
    chat_history: Optional[List[Dict[str, str]]] = None,
    mode: str = "general",  # "general" or "document"
) -> Optional[str]:
    """Chat with AI, optionally using a document for context."""
    if not client.is_available():
        return None

    try:
        loop = asyncio.get_event_loop()

        # If document mode, use document-based Q&A
        if mode == "document" and document_path:
            import os
            import pathlib

            if not os.path.exists(document_path):
                raise FileNotFoundError(f"Document file not found at path: {document_path}")

            try:
                # Read file and pass it directly to Gemini
                # For version 0.3.2, we need to read the file and pass it as content
                file_path_obj = pathlib.Path(document_path)
                print(f"Reading file for Gemini: {file_path_obj}")

                # Async file read so we do not pin the event loop on disk
                # I/O. Documents here can be 10s of MB; the difference between
                # blocking and yielding becomes visible the moment two users
                # hit chat-with-document at the same time.
                async with aiofiles.open(file_path_obj, 'rb') as f:
                    file_data = await f.read()

                import mimetypes
                mime_type, _ = mimetypes.guess_type(str(file_path_obj))
                if not mime_type:
                    # Default based on extension
                    if str(file_path_obj).lower().endswith('.pdf'):
                        mime_type = "application/pdf"
                    elif str(file_path_obj).lower().endswith(('.doc', '.docx')):
                        mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    elif str(file_path_obj).lower().endswith('.txt'):
                        mime_type = "text/plain"
                    else:
                        mime_type = "application/octet-stream"

                print(f"File read: {len(file_data)} bytes, MIME type: {mime_type}")

                prompt_text = f"""Please answer the following question based on the uploaded document.
Be thorough, accurate, and cite specific information from the document when possible.
If the question cannot be fully answered from the document, provide the best answer you can based on the document content.

Question: {question}"""

                print("Generating response with document...")

                # Try multiple methods to pass file to Gemini
                response = None
                last_error = None

                # Method 1: Use upload_file (available in 0.8.0+)
                try:
                    file_part = await loop.run_in_executor(
                        None,
                        lambda: genai.upload_file(path=str(file_path_obj), mime_type=mime_type)
                    )

                    print(f"File uploaded: {file_part.name}, state: {getattr(file_part, 'state', 'unknown')}")

                    # Wait for file to be processed (if it has a state attribute)
                    if hasattr(file_part, 'state'):
                        max_wait = 60
                        wait_time = 0
                        while wait_time < max_wait:
                            state = file_part.state
                            state_str = str(state).upper() if hasattr(state, 'upper') else str(state)

                            if "ACTIVE" in state_str or "READY" in state_str:
                                break
                            elif "PROCESSING" in state_str or "PENDING" in state_str:
                                await asyncio.sleep(2)
                                wait_time += 2
                                if hasattr(genai, 'get_file') and hasattr(file_part, 'name'):
                                    file_part = await loop.run_in_executor(
                                        None,
                                        lambda: genai.get_file(file_part.name)
                                    )
                            else:
                                break

                    print("File ready, generating response...")
                    response = await loop.run_in_executor(
                        None,
                        lambda: client.model.generate_content([prompt_text, file_part])
                    )
                except Exception as e1:
                    last_error = e1
                    print(f"Method 1 (upload_file) failed: {e1}")

                    # Method 2: Try passing file data directly as dict
                    try:
                        response = await loop.run_in_executor(
                            None,
                            lambda: client.model.generate_content([
                                prompt_text,
                                {
                                    "mime_type": mime_type,
                                    "data": file_data
                                }
                            ])
                        )
                    except Exception as e2:
                        last_error = e2
                        print(f"Method 2 (direct dict) failed: {e2}")

                        # Method 3: Try using Part if available
                        try:
                            from google.generativeai.types import Part
                            file_part = Part.from_data(mime_type=mime_type, data=file_data)
                            response = await loop.run_in_executor(
                                None,
                                lambda: client.model.generate_content([prompt_text, file_part])
                            )
                        except ImportError:
                            raise Exception(f"Unable to process file. Please upgrade google-generativeai package to version >= 0.8.0 for file support. Current error: {str(e2)}")
                        except Exception as e3:
                            last_error = e3
                            raise Exception(f"Unable to process file with Gemini API. All methods failed. Last error: {str(e3)}. Please ensure the file is a supported format (PDF, DOC, DOCX, TXT) and the google-generativeai package is up to date.")

                if response is None:
                    raise Exception(f"Failed to generate response. Last error: {str(last_error)}")

                print("Response generated successfully")

            except FileNotFoundError as e:
                print(f"File not found error: {e}")
                raise Exception(f"Document file not found: {str(e)}")
            except Exception as e:
                error_details = str(e)
                print(f"Error processing document: {error_details}")
                import traceback
                traceback.print_exc()
                if "not supported" in error_details.lower() or "format" in error_details.lower():
                    raise Exception("Document format not supported. Please upload a PDF, DOC, DOCX, or TXT file.")
                elif "timeout" in error_details.lower() or "timed out" in error_details.lower():
                    raise Exception("Document processing timed out. The file might be too large. Please try a smaller file.")
                else:
                    raise Exception(f"Failed to process document: {error_details}. Please ensure the file is valid and try again.")
        else:
            # General chat mode - build conversation with history
            prompt_parts = []

            if chat_history:
                for msg in chat_history:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if role == "user":
                        prompt_parts.append(f"User: {content}")
                    elif role == "assistant":
                        prompt_parts.append(f"Assistant: {content}")

            prompt_parts.append(f"User: {question}")
            prompt_parts.append("Assistant:")

            prompt = "\n\n".join(prompt_parts)

            response = await loop.run_in_executor(
                None,
                lambda: client.model.generate_content(prompt)
            )

        # Extract response text
        if hasattr(response, 'text'):
            return response.text.strip()
        elif isinstance(response, str):
            return response.strip()
        else:
            return str(response).strip()

    except Exception as e:
        print(f"Error in chat_with_document: {e}")
        import traceback
        traceback.print_exc()
        return None
