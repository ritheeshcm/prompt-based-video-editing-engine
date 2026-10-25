import unittest

from app.prompt_parser import parse_prompt


class PromptParserTests(unittest.TestCase):
    def test_parses_combined_trim_mute_and_portrait_request(self):
        result = parse_prompt(
            "Trim from 5 to 15 seconds, mute the audio, and convert to 9:16 portrait."
        )

        self.assertTrue(result.understood, result.warnings)
        self.assertEqual(
            [operation.operation for operation in result.operations],
            ["trim", "mute", "aspect_ratio"],
        )
        self.assertEqual(result.operations[0].params, {"start": 5.0, "end": 15.0})
        self.assertEqual(result.operations[2].params["ratio"], "9:16")

    def test_parses_first_and_last_duration(self):
        first = parse_prompt("Keep the first 10 seconds")
        last = parse_prompt("Keep only the last 20 seconds")

        self.assertTrue(first.understood, first.warnings)
        self.assertEqual(first.operations[0].params, {"start": 0.0, "end": 10.0})
        self.assertTrue(last.understood, last.warnings)
        self.assertEqual(last.operations[0].params, {"from_end": 20.0})

    def test_parses_speed_rotation_resolution_grayscale_and_volume(self):
        cases = {
            "Speed up to 2x": ("speed", {"factor": 2.0}),
            "Rotate 90 degrees": ("rotate", {"angle": 90}),
            "Scale to 720p": ("resolution", {"width": 1280, "height": 720}),
            "Make it grayscale": ("grayscale", {}),
            "Increase volume by 50%": ("volume", {"factor": 1.5}),
            "Increase volume by 1.5x": ("volume", {"factor": 1.5}),
        }

        for prompt, expected in cases.items():
            with self.subTest(prompt=prompt):
                result = parse_prompt(prompt)
                self.assertTrue(result.understood, result.warnings)
                self.assertEqual(result.operations[0].operation, expected[0])
                self.assertEqual(result.operations[0].params, expected[1])

    def test_rejects_invalid_or_unsupported_requests(self):
        prompts = [
            "Trim from 15 to 5 seconds",
            "Decrease volume by 150%",
            "Rotate 45 degrees",
            "Combine the compatible clips",
            "Convert to 4:5 aspect ratio",
            "Mute the audio and increase volume by 50%",
        ]

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                result = parse_prompt(prompt)
                self.assertFalse(result.understood)
                self.assertTrue(result.warnings)

    def test_empty_prompt_has_clear_error(self):
        result = parse_prompt("  ")

        self.assertFalse(result.understood)
        self.assertIn("Enter an editing instruction", result.warnings[0])


if __name__ == "__main__":
    unittest.main()
