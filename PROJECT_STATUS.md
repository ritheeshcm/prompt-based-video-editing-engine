# PS2 Project Status

## Verified starting state

- The project is an existing React/TypeScript/Vite frontend and FastAPI backend; the active frontend entry point is `frontend/src/main.tsx`.
- The frontend already uploads files, previews parsed operations, polls job status, and offers output preview/download controls.
- The backend already exposes `/health`, `/upload`, `/parse-preview`, `/process`, `/status/{job_id}`, and `/download/{job_id}`.
- Python 3.13.3, the backend virtual environment, Node.js 24.16.0, npm 11.13.0, and frontend dependencies are present.
- FFmpeg 9.0.2 and FFprobe are installed under the current user's WinGet package directory. They are not on the shell PATH, but the backend's existing discovery logic finds FFmpeg there.
- `test_sample.mp4` is a valid 30-second 1280x720 video with an audio stream.
- There is no Git repository metadata in the project directory, so changes cannot be compared to a Git baseline.
- The existing end-to-end script depends on a local server and bundled sample, but no focused backend unit tests are present.

## Prioritized implementation plan

1. **Done:** Validate uploaded media with FFprobe, return media metadata, enforce the 500 MB limit, and remove rejected/partial uploads.
2. **Done:** Reject malformed, invalid, incompatible, and unsupported prompt operations with visible explanations.
3. **Done:** Apply edits with FFmpeg, preserve requested speed/timing, handle audio-less media, report measured encoding progress, and validate output metadata before success.
4. **Done:** Align API/UI responses and URLs, surface preview and polling failures, and show media metadata in the existing workflow.
5. **Done:** Add standard-library backend tests and run the combined trim/mute/portrait workflow through both the API test script and browser UI.
6. **Done:** Update setup, API, test, and troubleshooting documentation.

## Known limits to retain or document

- Job state is in memory and is lost when the backend restarts.
- Combining multiple input clips is not implemented; combining multiple edits on one uploaded clip is supported.
- FFmpeg processing is limited to five minutes per job.

## Implementation and test results

### Completed work

- Uploads are streamed with a 500 MB cap, checked for a valid video stream, and report duration, dimensions, codec, and audio availability.
- Prompt parsing validates trim ranges, speed and volume factors, rotations, and aspect ratios; unsupported clip joining and contradictory mute/volume prompts return actionable errors.
- FFmpeg command construction uses input seeking and output durations correctly, preserves the requested aspect ratio when resolution is also specified, supports missing audio, and applies speed changes to both video and audio.
- FFmpeg progress output drives actual progress updates. A result is only marked complete after FFprobe confirms the generated file is valid.
- The UI exposes preview/network failures, shows probed media details, polls with explicit failure handling, and uses a stable IPv4 Vite proxy target.
- Fixed TypeScript JSX and type-only import configuration so the frontend production build succeeds. Updated README setup/API/troubleshooting instructions.

### Validation results

- Backend unit and FFmpeg integration tests: **12 passed** using `python -m unittest discover -s tests -v`.
- End-to-end API test: **passed**. Uploaded the 30-second sample, trimmed 5–15 seconds, muted audio, converted to 1080×1920, downloaded the MP4, and verified 10-second duration and no audio with FFprobe.
- Browser workflow: **passed**. Uploaded the sample, previewed the same operations, processed it, and confirmed the video element loaded metadata (10-second duration) and the download link was present.
- Frontend production build: **passed** using `npm run build`.
- Backend source and test syntax compilation: **passed** using `python -m py_compile`.
- No dependencies were installed or modified.

### Remaining limits

- The application only accepts one uploaded video per job; joining multiple clips is explicitly rejected.
- Job state remains in memory and is lost when the backend restarts.
- No Git metadata exists in the project folder, so a Git diff/status could not be used for verification.
