"""Generative video editing through Gemini Omni Flash."""

import base64
import binascii
import logging
import os
import time
from collections.abc import Callable

GEMINI_VIDEO_MODEL = "gemini-omni-1.1-flash"
VIDEO_PROCESSING_TIMEOUT_SECONDS = 600
logger = logging.getLogger(__name__)


class GeminiVideoEditError(RuntimeError):
    """Raised when Gemini cannot produce an edited video."""


def edit_video(
    input_path: str,
    output_path: str,
    prompt: str,
    update_progress: Callable[[str, int], None],
) -> None:
    """Upload a source video, request an edit, and save the generated MP4."""
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise GeminiVideoEditError(
            "Gemini is not configured. Set GEMINI_API_KEY in the backend terminal."
        )

    try:
        client = genai.Client(
            api_key=api_key,
            http_options=genai.types.HttpOptions(timeout=VIDEO_PROCESSING_TIMEOUT_SECONDS * 1000),
        )
    except (TypeError, ValueError) as error:
        raise GeminiVideoEditError(f"Could not configure the Gemini video client: {error}") from error

    video_file = None
    try:
        update_progress("Uploading source video to Gemini for AI editing...", 42)
        video_file = client.files.upload(file=input_path)
        file_name = video_file.name
        deadline = time.monotonic() + VIDEO_PROCESSING_TIMEOUT_SECONDS

        while True:
            state = video_file.state
            state_name = getattr(state, "name", str(state)).upper().rsplit(".", 1)[-1]
            if state_name == "FAILED":
                raise GeminiVideoEditError("Gemini could not prepare the uploaded video.")
            if state_name != "PROCESSING":
                break
            if time.monotonic() >= deadline:
                raise GeminiVideoEditError("Gemini timed out while preparing the uploaded video.")
            update_progress("Gemini is preparing the uploaded video...", 52)
            time.sleep(5)
            video_file = client.files.get(name=file_name)

        if not video_file.uri:
            raise GeminiVideoEditError("Gemini did not return a usable video reference.")

        update_progress("Gemini is generating the edited video...", 65)
        interaction = client.interactions.create(
            model=GEMINI_VIDEO_MODEL,
            input=[
                {"type": "video", "uri": video_file.uri},
                {"type": "text", "text": prompt},
            ],
        )
        output_video = getattr(interaction, "output_video", None)
        encoded_video = getattr(output_video, "data", None)
        if not encoded_video:
            raise GeminiVideoEditError("Gemini completed without returning an edited video.")

        try:
            video_bytes = base64.b64decode(encoded_video, validate=True)
        except (binascii.Error, ValueError) as error:
            raise GeminiVideoEditError("Gemini returned invalid video data.") from error
        if not video_bytes:
            raise GeminiVideoEditError("Gemini returned an empty video.")

        with open(output_path, "wb") as output_file:
            output_file.write(video_bytes)
        update_progress("Validating the generated video...", 90)
    finally:
        if video_file is not None:
            try:
                client.files.delete(name=video_file.name)
            except genai.errors.APIError as error:
                logger.warning("Could not delete temporary Gemini video upload: %s", error)
        client.close()
