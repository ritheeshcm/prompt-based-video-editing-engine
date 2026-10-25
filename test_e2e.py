"""
PS2 End-to-End Test Script
Tests the full: upload → process → poll → verify output pipeline
Run with: python test_e2e.py
"""
import json
import time
import sys
import urllib.request
import urllib.parse
import io
import os
from pathlib import Path
import tempfile

# Force UTF-8 output on Windows (avoids CP1252 emoji errors)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = os.environ.get("PS2_API_URL", "http://127.0.0.1:8000")
PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR / "backend"))

from app.video_processor import probe_video

def post_json(url, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def get_json(url):
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())

def upload_file(path):
    boundary = "----PS2TestBoundary"
    with open(path, "rb") as f:
        file_data = f.read()
    filename = Path(path).name
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: video/mp4\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{BASE}/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def run_test():
    print("=" * 60)
    print("PS2 – End-to-End Test")
    print("=" * 60)

    # 1. Health check
    print("\n[1] Checking backend health...")
    health = get_json(f"{BASE}/health")
    print(f"    Status: {health['status']}")
    print(f"    FFmpeg: {health['ffmpeg']['available']} – {health['ffmpeg'].get('version','?')[:40]}")
    assert health["status"] == "ok", "Backend not healthy!"
    assert health["ffmpeg"]["available"], "FFmpeg not available!"
    print("    ✅ Health check PASSED")

    # 2. Parse preview
    print("\n[2] Testing prompt parser...")
    prompt = "Trim from 5 to 15 seconds, mute the audio, and convert to 9:16 portrait."
    preview_url = f"{BASE}/parse-preview?prompt={urllib.parse.quote(prompt)}"
    preview = get_json(preview_url)
    print(f"    Understood: {preview['understood']}")
    for op in preview["operations"]:
        print(f"    → {op['operation']}: {op['description']}")
    assert preview["understood"], "Parser didn't understand the prompt!"
    assert [op["operation"] for op in preview["operations"]] == [
        "trim", "mute", "aspect_ratio"
    ], f"Unexpected operation plan: {preview['operations']}"
    print("    ✅ Prompt parser PASSED")

    # 3. Upload
    print("\n[3] Uploading test video...")
    video_path = PROJECT_DIR / "test_sample.mp4"
    upload = upload_file(video_path)
    job_id = upload["job_id"]
    print(f"    Job ID: {job_id}")
    print(f"    Status: {upload['status']}")
    print(f"    Metadata: {upload.get('metadata')}")
    assert upload["status"] == "uploaded", "Upload failed!"
    assert upload["metadata"]["duration"] > 15, "Sample video is too short for the trim test."
    print("    ✅ Upload PASSED")

    # 4. Process
    print("\n[4] Starting video processing...")
    process = post_json(f"{BASE}/process", {"job_id": job_id, "prompt": prompt})
    print(f"    Status: {process['status']}")
    print("    ✅ Process started")

    # 5. Poll until done
    print("\n[5] Polling for completion...")
    for i in range(60):  # poll up to 60 seconds
        time.sleep(1)
        status = get_json(f"{BASE}/status/{job_id}")
        print(f"    [{i+1:02d}s] {status['status']} – {status['progress']}% – {status['message']}")
        if status["status"] == "done":
            print(f"\n    ✅ Processing DONE!")
            print(f"    Output URL: {status['output_url']}")
            print(f"    File size: {status.get('file_size_mb', '?')} MB")
            print(f"    Operations applied:")
            for op in (status.get("operations") or []):
                print(f"      → {op['description']}")
            with urllib.request.urlopen(f"{BASE}/download/{job_id}") as response:
                assert response.status == 200, "Download endpoint returned an error."
                assert response.headers.get_content_type() == "video/mp4", "Download is not an MP4."
                output_bytes = response.read()
            assert output_bytes, "Downloaded output is empty."
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as output_file:
                output_file.write(output_bytes)
                output_path = Path(output_file.name)
            try:
                metadata = probe_video(str(output_path))
            finally:
                output_path.unlink(missing_ok=True)
            print(f"    Downloaded output metadata: {metadata}")
            assert abs(metadata["duration"] - 10) < 0.5, "Output duration is not approximately 10 seconds."
            assert (metadata["width"], metadata["height"]) == (1080, 1920), "Output is not 9:16 portrait."
            assert not metadata["has_audio"], "Muted output still contains an audio stream."
            assert status["metadata"]["has_audio"] is False, "API output metadata reports an audio stream."
            print("    ✅ Download and output validation PASSED")
            return True
        elif status["status"] == "failed":
            print(f"\n    ❌ Processing FAILED: {status.get('error', 'unknown')}")
            if status.get("ffmpeg_stderr"):
                print(f"    FFmpeg stderr: {status['ffmpeg_stderr'][-500:]}")
            return False

    print("\n    ❌ TIMEOUT — processing took too long")
    return False

if __name__ == "__main__":
    try:
        success = run_test()
        print("\n" + "=" * 60)
        print("RESULT:", "✅ ALL TESTS PASSED" if success else "❌ TESTS FAILED")
        print("=" * 60)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
