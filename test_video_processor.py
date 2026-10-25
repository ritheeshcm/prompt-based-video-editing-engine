import unittest
from pathlib import Path
import subprocess
import tempfile

from app.prompt_parser import parse_prompt
from app.video_processor import (
    FFMPEG_BIN,
    FFPROBE_BIN,
    build_ffmpeg_command,
    probe_video,
    process_video,
)


PROJECT_DIR = Path(__file__).resolve().parents[2]


class VideoProcessorTests(unittest.TestCase):
    def test_ffmpeg_and_ffprobe_are_discoverable(self):
        self.assertTrue(Path(FFMPEG_BIN).is_file(), FFMPEG_BIN)
        self.assertTrue(Path(FFPROBE_BIN).is_file(), FFPROBE_BIN)

    def test_probe_reports_video_metadata_and_audio(self):
        metadata = probe_video(str(PROJECT_DIR / "test_sample.mp4"))

        self.assertAlmostEqual(metadata["duration"], 30.0, places=1)
        self.assertEqual((metadata["width"], metadata["height"]), (1280, 720))
        self.assertTrue(metadata["has_audio"])

    def test_builds_trim_mute_portrait_command(self):
        result = parse_prompt(
            "Trim from 5 to 15 seconds, mute the audio, and convert to 9:16 portrait."
        )
        command = build_ffmpeg_command(
            "input.mp4",
            "output.mp4",
            result.operations,
            video_duration=30,
            has_audio=True,
        )

        self.assertLess(command.index("-ss"), command.index("-i"))
        self.assertEqual(command[command.index("-ss") + 1], "5.000000")
        self.assertEqual(command[command.index("-t") + 1], "10.000000")
        self.assertIn("-an", command)
        self.assertNotIn("-af", command)
        self.assertIn(
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
            command[command.index("-vf") + 1],
        )

    def test_portrait_resolution_preserves_requested_aspect_ratio(self):
        result = parse_prompt("Convert to portrait 9:16 and scale to 720p")
        command = build_ffmpeg_command(
            "input.mp4",
            "output.mp4",
            result.operations,
            video_duration=30,
            has_audio=False,
        )

        self.assertTrue(result.understood, result.warnings)
        self.assertIn(
            "scale=720:1280:force_original_aspect_ratio=decrease,"
            "pad=720:1280:(ow-iw)/2:(oh-ih)/2:black",
            command[command.index("-vf") + 1],
        )
        self.assertNotIn("-af", command)
        self.assertIn("-an", command)

    def test_rejects_trim_start_past_video_duration(self):
        result = parse_prompt("Trim from 35 to 40 seconds")

        with self.assertRaisesRegex(ValueError, "beyond the end"):
            build_ffmpeg_command(
                "input.mp4",
                "output.mp4",
                result.operations,
                video_duration=30,
            )

    def test_processes_speed_grayscale_rotation_and_volume(self):
        result = parse_prompt(
            "Trim from 0 to 2 seconds, speed up to 2x, make it grayscale, "
            "rotate 90 degrees, and increase volume by 50%."
        )
        progress_updates = []

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "processed.mp4"
            processed = process_video(
                str(PROJECT_DIR / "test_sample.mp4"),
                str(output_path),
                result,
                lambda message, progress: progress_updates.append((message, progress)),
            )

            self.assertTrue(processed["success"], processed.get("error"))
            self.assertTrue(output_path.is_file())
            self.assertTrue(progress_updates)
            metadata = probe_video(str(output_path))
            self.assertAlmostEqual(metadata["duration"], 1.0, delta=0.2)
            self.assertEqual((metadata["width"], metadata["height"]), (720, 1280))
            self.assertTrue(metadata["has_audio"])

    def test_volume_request_fails_for_video_without_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "silent.mp4"
            output_path = Path(directory) / "output.mp4"
            subprocess.run(
                [
                    FFMPEG_BIN, "-y",
                    "-f", "lavfi", "-i", "color=c=black:s=160x120:r=25:d=1",
                    "-c:v", "libx264", "-an", str(input_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = process_video(
                str(input_path),
                str(output_path),
                parse_prompt("Increase volume by 50%"),
            )

            self.assertFalse(result["success"])
            self.assertIn("no audio track", result["error"])
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
