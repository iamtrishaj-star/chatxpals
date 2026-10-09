import os
import json
import re
from typing import Dict, Any
from dotenv import load_dotenv
import bleach
import google.generativeai as genai

# Load environment variables at the very top of the file before genai.configure()
load_dotenv()


def sanitize_chat_text(raw_text: str) -> str:
    """
    Sanitize raw chat log text to prevent Cross-Site Scripting (XSS) and injection attacks.
    Strips all HTML tags, script/style blocks with contents, and dangerous control characters.
    """
    if not raw_text:
        return ""

    # Remove null bytes
    clean_text = raw_text.replace("\x00", "")

    # Strip script, style, iframe, object, and embed blocks including their inner contents
    clean_text = re.sub(
        r"<\s*(script|style|iframe|object|embed)[^>]*>.*?<\s*/\s*\1\s*>",
        "",
        clean_text,
        flags=re.DOTALL | re.IGNORECASE
    )

    # Bleach strips any remaining tags and attributes completely
    clean_text = bleach.clean(
        clean_text,
        tags=[],
        attributes={},
        protocols=[],
        strip=True
    )

    return clean_text.strip()


async def process_chat_log(text: str) -> Dict[str, Any]:
    """
    Process chat log exclusively using the google-generativeai SDK.
    Calls Gemini model asynchronously to extract summary, action items, and mentions.
    Raises exceptions on failure without falling back to mock or fake data.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY environment variable is missing or empty. "
            "Please configure GEMINI_API_KEY in your .env file."
        )

    # Configure Gemini SDK
    genai.configure(api_key=api_key)

    # Candidate models in priority order (gemini-3.7-flash has active quota)
    candidate_models = [
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-flash-latest",
        "gemini-3.8-flash"
    ]

    prompt = f"""You are an expert chat log analyzer. Analyze the following chat transcript and return a structured JSON response.

Required JSON schema:
{{
  "summary": "Concise executive overview of the conversation",
  "action_items": ["Action item 1", "Action item 2"],
  "mentions": ["@username1", "@username2"]
}}

Guidelines:
- "summary": A coherent summary string covering key discussions and decisions.
- "action_items": A list of strings for tasks or to-dos. If none, return [].
- "mentions": A list of strings for user handles or participant names mentioned (e.g., @name). If none, return [].
- Return ONLY valid JSON matching the specified keys. Do not return markdown fences or extra commentary.

Chat Transcript:
---
{text}
---"""

    response = None
    last_error = None

    for model_name in candidate_models:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config={
                    "response_mime_type": "application/json"
                }
            )
            response = await model.generate_content_async(prompt)
            if response and hasattr(response, "text") and response.text:
                break
        except Exception as exc:
            last_error = exc
            # If quota exhausted (429 / ResourceExhausted) or model not found, try next candidate
            err_msg = str(exc).lower()
            if "quota" in err_msg or "resource_exhausted" in err_msg or "429" in err_msg or "404" in err_msg or "not found" in err_msg:
                continue
            # For other unexpected errors, re-raise immediately
            raise

    if response is None or not hasattr(response, "text") or not response.text:
        if last_error:
            raise last_error
        raise RuntimeError("Gemini API returned an empty or invalid response across all candidate models.")

    # Parse and validate JSON structure
    try:
        data = json.loads(response.text.strip())
    except json.JSONDecodeError as err:
        raise ValueError(f"Failed to parse Gemini response as JSON: {str(err)}. Raw response: {response.text}") from err

    # Validate required keys
    required_keys = ("summary", "action_items", "mentions")
    missing_keys = [k for k in required_keys if k not in data]
    if missing_keys:
        raise KeyError(f"Gemini response missing required keys: {missing_keys}. Response: {data}")

    # Ensure summary is a clean string
    summary_val = data["summary"]
    if isinstance(summary_val, (dict, list)):
        summary_str = json.dumps(summary_val)
    else:
        summary_str = str(summary_val).strip()

    # Normalize action items into clean list of strings
    raw_actions = data.get("action_items") or []
    if not isinstance(raw_actions, list):
        raw_actions = [raw_actions]

    formatted_actions = []
    for item in raw_actions:
        if isinstance(item, dict):
            task = item.get("task") or item.get("action") or item.get("description") or str(item)
            assignee = item.get("assignee") or item.get("owner")
            if assignee:
                formatted_actions.append(f"{task} (Assigned to: {assignee})")
            else:
                formatted_actions.append(str(task))
        else:
            formatted_actions.append(str(item).strip())

    # Normalize mentions into clean list of strings
    raw_mentions = data.get("mentions") or []
    if not isinstance(raw_mentions, list):
        raw_mentions = [raw_mentions]

    formatted_mentions = []
    for m in raw_mentions:
        if isinstance(m, dict):
            name = m.get("name") or m.get("username") or m.get("user") or str(m)
            formatted_mentions.append(str(name).strip())
        else:
            formatted_mentions.append(str(m).strip())

    return {
        "summary": summary_str,
        "action_items": formatted_actions,
        "mentions": formatted_mentions
    }
