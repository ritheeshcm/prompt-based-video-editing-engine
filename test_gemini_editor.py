import json
import os
import unittest
from unittest.mock import patch

from app.gemini_editor import (
    GeminiEditorNotConfigured,
    interpret_edit,
)


class GeminiEditorTests(unittest.TestCase):
    def test_requires_backend_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(GeminiEditorNotConfigured):
                interpret_edit("make this clip shorter")

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
    @patch("app.gemini_editor.urlopen")
    def test_normalizes_natural_language_and_preserves_history(self, urlopen):
        model_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "understood": True,
                            "reply": "I’ll keep the first 10 seconds and mute the audio.",
                            "normalizedPrompt": "keep the first 10 seconds and mute the audio",
                            "mode": "standard",
                        })
                    }]
                }
            }]
        }
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = json.dumps(model_response).encode()

        result = interpret_edit(
            "make it shorter and get rid of the sound",
            [
                {"role": "assistant", "text": "Hi, what edits do you need?"},
                {"role": "user", "text": "Keep the first ten seconds."},
            ],
        )

        self.assertTrue(result["understood"])
        self.assertEqual(result["prompt"], "keep the first 10 seconds and mute the audio")
        self.assertEqual(
            [operation["operation"] for operation in result["operations"]],
            ["trim", "mute"],
        )
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("X-goog-api-key"), "test-key")
        body = json.loads(request.data)
        self.assertEqual(body["contents"][0]["role"], "user")
        self.assertEqual(len(body["contents"]), 2)

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
    @patch("app.gemini_editor.urlopen")
    def test_does_not_apply_unsupported_requests(self, urlopen):
        model_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "understood": False,
                            "reply": "Adding subtitles is not supported yet.",
                            "normalizedPrompt": "",
                            "mode": "generative",
                        })
                    }]
                }
            }]
        }
        urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(
            model_response
        ).encode()

        result = interpret_edit("add subtitles to the video")

        self.assertFalse(result["understood"])
        self.assertEqual(result["operations"], [])
        self.assertEqual(result["prompt"], "")
        self.assertIn("not supported", result["reply"])

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
    @patch("app.gemini_editor.urlopen")
    def test_rejects_a_model_plan_outside_supported_parser(self, urlopen):
        model_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "understood": True,
                            "reply": "I’ll add subtitles.",
                            "normalizedPrompt": "add subtitles",
                            "mode": "standard",
                        })
                    }]
                }
            }]
        }
        urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(
            model_response
        ).encode()

        result = interpret_edit("add subtitles")

        self.assertFalse(result["understood"])
        self.assertEqual(result["operations"], [])
        self.assertEqual(result["prompt"], "")


if __name__ == "__main__":
    unittest.main()
