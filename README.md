# 🎬 PS2 – Prompt-Based Video Editing Engine

> Edit videos using plain-English commands. No editing software needed.
> Built with React + TypeScript + FastAPI + FFmpeg.

---

## 📸 What It Does

You describe your edits in the chat:
> "Trim from 5 to 30 seconds, mute the audio, and convert to 9:16 portrait"

The chat uses Gemini to understand natural phrasing and follow-up requests. It
previews the requested changes before you apply them, then validates the plan
against the edits supported by the engine. Gemini can interpret requests flexibly,
but unsupported operations such as adding subtitles are reported instead of
silently ignored.

---

## 🏗️ Project Structure

```
prompt-based-video-editing-engine/
├── app/                         ← Python editing and AI modules
├── main.py                      ← FastAPI app (all API routes)
├── requirements.txt
├── test_*.py                    ← Backend unit tests
├── src/                         ← React + TypeScript frontend
│   ├── components/
│   ├── App.tsx
│   ├── api.ts
│   └── main.tsx
├── index.html
├── package.json
└── vite.config.ts
```

---

## 🚀 How to Run Locally (Windows / PowerShell)

### Prerequisites
- Node.js 18+ and npm
- Python 3.10+
- FFmpeg and FFprobe (both executables are required)

From the repository root, create a Python virtual environment and install both
backend and frontend dependencies:

```powershell
Set-Location 'D:\incubrix\prompt-based-video-editing-engine'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm install
```

### Step 1 — Start the Backend

Create a Gemini API key in [Google AI Studio](https://aistudio.google.com/apikey).
Generative edits use Gemini Omni Flash and may incur separate model usage costs.
When you choose a generative edit, the source video is uploaded to Google's Gemini
API. Review Google's current [pricing](https://ai.google.dev/gemini-api/docs/pricing)
and data-use terms before using this feature.
In the same PowerShell terminal used to start the backend, set the key before
launching the server. Keep the key private; it is read only by the backend and
must not be added to frontend code or committed:

```powershell
$env:GEMINI_API_KEY = "your-gemini-api-key"
```

Open **Terminal 1** and run:

```powershell
Set-Location 'D:\incubrix\prompt-based-video-editing-engine'
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

The backend API will be at: http://127.0.0.1:8000
Swagger docs: http://127.0.0.1:8000/docs
The app shows whether Gemini is configured. If you open a new terminal, set
`GEMINI_API_KEY` in that terminal before starting the backend again.

### Step 2 — Start the Frontend

Open **Terminal 2** and run:

```powershell
Set-Location 'D:\incubrix\prompt-based-video-editing-engine'
npm run dev -- --host 127.0.0.1
```

The app will open at: http://127.0.0.1:5173

If the backend uses a different port than 8000, set `BACKEND_TARGET` in the frontend
terminal before starting Vite (for example, `$env:BACKEND_TARGET = "http://127.0.0.1:8100"`).
The backend checks standard WinGet install folders for FFmpeg. Otherwise, ensure both
`ffmpeg.exe` and `ffprobe.exe` are available on `PATH`. Check their availability at
`http://127.0.0.1:8000/health`.

## ☁️ Deploy to Render

This repository includes a Render Blueprint and a Dockerfile for deploying the
frontend and backend as one web service. The container builds the React frontend,
installs FFmpeg, and serves the production frontend and FastAPI routes on the same
HTTPS origin.

1. Push the repository to GitHub.
2. In Render, choose **New + → Blueprint**, select the repository, and apply the
   `render.yaml` configuration. This creates a new Docker web service named
   `prompt-video-engine-app`; it does not convert an existing Static Site service.
   Use the new web service URL after deployment.
3. If you want Gemini chat and generative edits, add `GEMINI_API_KEY` in the
   service's Render environment settings. Standard supported edits work without it.
4. Wait for the deployment to finish, then open the `onrender.com` URL. Check
   `<your-service-url>/health`; it should return `"status": "ok"` and report FFmpeg
   and FFprobe as available.

The service uses Render's ephemeral filesystem and keeps jobs in memory. Uploaded
videos, generated outputs, and jobs will not survive a service restart or instance
replacement. Configure persistent storage and durable job storage before using this
for data that must be retained. Free instances may sleep when idle, so the first
request after inactivity can take longer.

---

## 🧠 Supported Prompts

| What you want | Example prompt |
|---|---|
| **Trim** | "Trim from 5 to 30 seconds" |
| **Keep first N seconds** | "Keep only the first 10 seconds" |
| **Keep last N seconds** | "Keep the last 20 seconds" |
| **Mute audio** | "Mute the audio" / "Remove sound" |
| **Aspect ratio** | "Convert to 9:16 portrait" / "Make it square 1:1" |
| **Speed up** | "Speed up to 2x" / "Make it 1.5x faster" |
| **Slow down** | "Slow down to 0.5x" / "Slow motion" |
| **Resolution** | "Scale to 1080p" / "Convert to 720p" |
| **Black & white** | "Make it grayscale" / "Black and white" |
| **Rotate** | "Rotate 90 degrees" / "Flip horizontal" |
| **Volume** | "Increase volume by 50%" |
| **Combine edits** | "Trim from 5 to 30 seconds, mute, and convert to 9:16" |

Multiple edits can be combined in one prompt. Joining multiple uploaded video clips
is not implemented; prompts requesting clip joining are rejected instead of ignored.
The uploaded file must contain a readable video stream and have a supported extension
(MP4, MOV, AVI, MKV, WebM, or M4V); uploads are limited to 500 MB.

---

## 🔌 API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Check backend + FFmpeg status |
| POST | `/upload` | Upload a video file |
| POST | `/chat-preview` | Interpret a conversational edit request with Gemini |
| POST | `/process` | Start editing with a prompt |
| GET | `/status/{job_id}` | Poll job progress |
| GET | `/download/{job_id}` | Download output MP4 |
| GET | `/parse-preview?prompt=...` | Preview what a prompt will do |
| GET | `/outputs/{filename}` | Stream a generated preview video |

Full interactive docs: http://127.0.0.1:8000/docs

Typical API workflow:

1. `POST /upload` with multipart form field `file`. The response returns a unique `job_id` and FFprobe metadata (`duration`, `width`, `height`, `has_audio`, and `video_codec`).
2. `POST /chat-preview` with JSON `{"prompt":"make this clip shorter and get rid of the sound","history":[]}`. The response contains a friendly reply and a validated edit plan. Send returned `prompt` to process only when `understood` is true.
3. `POST /process` with JSON `{"job_id":"...","prompt":"keep the first 10 seconds and mute the audio"}`.
4. Poll `GET /status/{job_id}` until the status is `done` or `failed`.
5. When complete, use the returned `output_url` for playback or `GET /download/{job_id}` to download the MP4.

---

## 🛠️ How It Works

1. **Upload** — Video is saved to `uploads/` with a unique job ID and inspected by FFprobe
2. **Chat and preview** — Gemini interprets the request and recent conversation; the local parser validates the proposed plan against supported operations before showing it
3. **Process** — FFmpeg is called off the API event loop with a single command covering all operations; output is checked with FFprobe before success is reported
4. **Download** — The output MP4 is saved to `outputs/` and served for preview + download

### Chat behavior
- Gemini understands varied wording and follow-up requests using the recent chat history.
- The Gemini API key stays in the backend environment; it is never sent to the browser. Without a key, chat falls back to the offline parser for supported standard edits; generative edits still require Gemini.
- Standard edits are validated by the local parser before they can be applied. Generative edits use Gemini Omni Flash on the uploaded source video.
- AI video edits can alter visual details beyond the requested change; review the generated output before using it.
- This is not a promise to execute every possible editing command. Unsupported requests and provider limitations can still result in a refusal or generation failure.

---

## ⚠️ Known Limitations

- Jobs are stored **in memory** — restart the server and all jobs are lost
- Maximum upload size: **500MB**
- Processing time depends on video length and operations chosen
- Job state is in memory, so restart the backend if an old job ID is no longer found
- Clip-to-clip joining is not supported

## 🧪 Tests and Build

Run the focused backend unit tests:

```powershell
Set-Location 'D:\incubrix\prompt-based-video-editing-engine'
.\.venv\Scripts\python.exe -m unittest discover -s . -p 'test*.py' -v
```

Run the upload → edit → download end-to-end check while both servers are running:

```powershell
Set-Location 'D:\incubrix\prompt-based-video-editing-engine'
.\.venv\Scripts\python.exe .\test_e2e.py
```

Check the production frontend build:

```powershell
Set-Location 'D:\incubrix\prompt-based-video-editing-engine'
npm run build
```

## 🛠️ Troubleshooting

- **Backend connection refused:** start the backend command above and check `/health`.
- **FFmpeg/FFprobe missing:** verify `ffmpeg -version` and `ffprobe -version`, then add their `bin` directory to `PATH` or install them in the standard WinGet location.
- **Upload rejected:** use a supported video container under 500 MB; files must contain a readable video stream.
- **Chat says Gemini is unavailable:** standard supported edits can still be previewed with the local parser. Configure `GEMINI_API_KEY` for broader natural-language interpretation and generative edits.
- **Prompt preview unavailable:** check that the Vite proxy can reach `http://127.0.0.1:8000`; `/chat-preview` and `/parse-preview` must be proxied to the backend. Unsupported or invalid operations are shown before processing.
- **Render homepage or API returns 404:** deploy the repository as a Docker web service using its `render.yaml` Blueprint, not as a static site. Check the deployment logs and `/health`.
- **Job not found after a restart:** jobs are held in memory; upload the source again to create a new job.

---

## 📚 Student Notes

### What is FFmpeg?
FFmpeg is a free, open-source program that can read, convert, and edit almost any video format. We control it by running it as a subprocess from Python — like clicking buttons in a video editor, but with code.

### What is FastAPI?
FastAPI is a modern Python web framework. It handles HTTP requests from the frontend, runs our Python code, and sends back responses. It's like the "brain" that connects the UI to FFmpeg.

### What is Vite + React?
Vite is a fast build tool for web apps. React is a JavaScript library for building UIs. Together, they let us create a dynamic, interactive web interface.

### What is a Virtual Environment (venv)?
A venv is an isolated Python installation just for this project. It keeps your dependencies separate from other Python projects on your computer.
