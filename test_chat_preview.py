import asyncio
import unittest
from unittest.mock import patch

from app.gemini_editor import GeminiEditorNotConfigured
from main import ChatPreviewRequest, chat_preview


class ChatPreviewTests(unittest.TestCase):
    @patch(
        "main.interpret_edit",
        side_effect=GeminiEditorNotConfigured("Gemini is not configured."),
    )
    def test_uses_local_parser_when_gemini_is_not_configured(self, _interpret_edit):
        result = asyncio.run(
            chat_preview(ChatPreviewRequest(prompt="Trim from 5 to 15 seconds and mute the audio"))
        )

        self.assertTrue(result["understood"])
        self.assertEqual(
            [operation["operation"] for operation in result["operations"]],
            ["trim", "mute"],
        )
        self.assertIn("local parser", result["warnings"][0])
        self.assertEqual(
            result["prompt"],
            "Trim from 5 to 15 seconds and mute the audio",
        )

    @patch(
        "main.interpret_edit",
        side_effect=GeminiEditorNotConfigured("Gemini is not configured."),
    )
    def test_explains_local_parser_limit_for_unrecognized_requests(self, _interpret_edit):
        result = asyncio.run(chat_preview(ChatPreviewRequest(prompt="Make it sparkle")))

        self.assertFalse(result["understood"])
        self.assertEqual(result["prompt"], "")
        self.assertIn("could not match", result["reply"])
        self.assertTrue(result["warnings"])


if __name__ == "__main__":
    unittest.main()
