"""Gemini-powered natural-language interpretation for supported video edits."""

import json
import os
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.prompt_parser import ParseResult, parse_prompt

GEMINI_MODEL = "gemini-3.8-flash"
GEMINI_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)


class GeminiEditorError(RuntimeError):
    """Raised when Gemini cannot interpret an editing request."""


class GeminiEditorNotConfigured(GeminiEditorError):
    """Raised when the backend has no Gemini API key configured."""


def interpret_edit(
    prompt: str,
    history: list[dict[str, str]] | None = None,
) -> dict:
    """Interpret a chat request, then validate its edit plan with the rule parser."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise GeminiEditorNotConfigured(
            "Gemini is not configured. Set GEMINI_API_KEY in the backend terminal, "
            "then restart the backend."
        )

    contents = []
    conversation = (history or [])[-8:]
    while conversation and conversation[0]["role"] != "user":
        conversation = conversation[1:]
    for turn in conversation:
        text = turn["text"].strip()
        if text:
            contents.append({
                "role": "user" if turn["role"] == "user" else "model",
                "parts": [{"text": text[:2000]}],
            })
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    request_body = {
        "systemInstruction": {
            "parts": [{
                "text": (
                    "You are a video-editing assistant. Understand natural, informal "
                    "descriptions and follow-up corrections. This app can only apply "
                    "trim/cut time ranges, mute audio, adjust volume, change aspect "
                    "ratio to 16:9, 9:16, 1:1, 4:3, or 21:9, change speed from >0 "
                    "through 16x, rotate 90/180/270 degrees, flip horizontally or "
                    "vertically, scale to 360p/480p/720p/1080p/4k, and convert to "
                    "grayscale using standard FFmpeg edits. Choose mode='standard' "
                    "for plans consisting only of those operations. The app also has "
                    "a generative video-edit mode that sends the uploaded video to "
                    "Gemini Omni Flash. Choose mode='generative' for visual-content "
                    "changes (such as adding fictional adults in ordinary swimwear to "
                    "a river scene), subtitles, transitions, effects, or other natural "
                    "video edits that need generated changes to the footage. Do not "
                    "choose generative for general chat or unrelated tasks. For an "
                    "unsupported, ambiguous, or non-video-editing request, set "
                    "understood=false, leave normalizedPrompt empty, and explain or "
                    "ask a concise clarifying question in reply. For a supported edit, "
                    "return the FULL intended plan, preserving prior edits from the "
                    "conversation unless the user explicitly changes or removes them. "
                    "normalizedPrompt must be a short English instruction that the "
                    "existing video parser can read using these forms: 'trim from "
                    "5 to 10 seconds', 'keep the first 10 seconds', 'keep the last "
                    "10 seconds', 'mute the audio', 'increase volume by 50%', "
                    "'decrease volume by 20%', 'convert to 9:16 portrait', 'speed up "
                    "to 2x', 'rotate 90 degrees', 'flip horizontal', 'scale to 720p', "
                    "and 'make it grayscale'. For mode='generative', normalizedPrompt "
                    "must instead be the complete plain-language description of the "
                    "visual edit for Gemini Omni Flash. Combine compatible operations "
                    "with 'and'. Never include commentary in normalizedPrompt. Do "
                    "not infer missing time ranges or numeric values."
                )
            }]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "understood": {"type": "BOOLEAN"},
                    "reply": {"type": "STRING"},
                    "normalizedPrompt": {"type": "STRING"},
                    "mode": {"type": "STRING", "enum": ["standard", "generative"]},
                },
                "required": ["understood", "reply", "normalizedPrompt", "mode"],
            },
        },
    }
    request = Request(
        GEMINI_ENDPOINT,
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise GeminiEditorError(
            f"Gemini API returned HTTP {error.code}: {detail[:500]}"
        ) from error
    except (URLError, TimeoutError) as error:
        raise GeminiEditorError(f"Could not reach the Gemini API: {error}") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise GeminiEditorError("Gemini returned an invalid response.") from error

    try:
        response_text = payload["candidates"][0]["content"]["parts"][0]["text"]
        interpreted = json.loads(response_text)
        understood = interpreted["understood"]
        reply = interpreted["reply"]
        normalized_prompt = interpreted["normalizedPrompt"]
        mode = interpreted["mode"]
        if (
            not isinstance(understood, bool)
            or not isinstance(reply, str)
            or not isinstance(normalized_prompt, str)
            or mode not in ("standard", "generative")
        ):
            raise TypeError("Unexpected response field types.")
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise GeminiEditorError("Gemini returned an invalid editing plan.") from error

    if not understood:
        return {
            "understood": False,
            "operations": [],
            "warnings": [reply],
            "prompt": "",
            "reply": reply,
            "mode": mode,
        }

    if not normalized_prompt.strip() or len(normalized_prompt) > 2000:
        raise GeminiEditorError("Gemini returned an empty or oversized editing plan.")

    if mode == "generative":
        return {
            "understood": True,
            "operations": [],
            "warnings": [],
            "prompt": normalized_prompt,
            "reply": reply,
            "mode": mode,
        }

    result: ParseResult = parse_prompt(normalized_prompt)
    if not result.understood:
        return {
            "understood": False,
            "operations": [],
            "warnings": result.warnings,
            "prompt": "",
            "reply": "I couldn’t safely validate that edit plan. Please rephrase the request.",
            "mode": mode,
        }

    return {
        "understood": True,
        "operations": [
            {
                "operation": operation.operation,
                "description": operation.description,
                "params": operation.params,
            }
            for operation in result.operations
        ],
        "warnings": result.warnings,
        "prompt": normalized_prompt,
        "reply": reply,
        "mode": mode,
    }
