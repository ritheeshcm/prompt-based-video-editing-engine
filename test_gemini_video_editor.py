import base64
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.gemini_video_editor import edit_video


class GeminiVideoEditorTests(unittest.TestCase):
    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
    @patch("google.genai.Client")
    def test_uploads_video_requests_edit_and_writes_output(self, client_factory):
        client = client_factory.return_value
        client.files.upload.return_value = SimpleNamespace(
            name="files/source",
            state="ACTIVE",
            uri="https://example.invalid/source",
        )
        output_bytes = b"generated mp4 bytes"
        client.interactions.create.return_value = SimpleNamespace(
            output_video=SimpleNamespace(data=base64.b64encode(output_bytes).decode())
        )
        progress = []

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.mp4"
            output = Path(directory) / "output.mp4"
            source.write_bytes(b"source")

            edit_video(
                str(source),
                str(output),
                "Add two fictional adults in ordinary swimwear bathing in the river.",
                lambda message, pct: progress.append((message, pct)),
            )

            self.assertEqual(output.read_bytes(), output_bytes)

        client.files.upload.assert_called_once_with(file=str(source))
        client.files.delete.assert_called_once_with(name="files/source")
        client.close.assert_called_once()
        client.interactions.create.assert_called_once()
        request = client.interactions.create.call_args.kwargs
        self.assertEqual(request["model"], "gemini-omni-1.1-flash")
        self.assertEqual(request["input"][0]["uri"], "https://example.invalid/source")
        self.assertIn("two fictional adults", request["input"][1]["text"])
        self.assertEqual(progress[-1][1], 90)

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
    @patch("google.genai.Client")
    def test_rejects_missing_generated_video(self, client_factory):
        client = client_factory.return_value
        client.files.upload.return_value = SimpleNamespace(
            name="files/source",
            state="ACTIVE",
            uri="https://example.invalid/source",
        )
        client.interactions.create.return_value = SimpleNamespace(output_video=None)

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.mp4"
            source.write_bytes(b"source")
            with self.assertRaisesRegex(RuntimeError, "without returning an edited video"):
                edit_video(
                    str(source),
                    str(Path(directory) / "output.mp4"),
                    "Edit this video.",
                    lambda _message, _pct: None,
                )


if __name__ == "__main__":
    unittest.main()
