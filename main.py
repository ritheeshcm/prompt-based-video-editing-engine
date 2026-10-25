"""
PS2 – Prompt-Based Video Editing Engine
FastAPI Backend — Main Application
"""

import uuid
import asyncio
import logging
import os
from pathlib import Path
from typing import Literal, Optional
from datetime import datetime, timezone

import aiofiles
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.gemini_editor import (
    GeminiEditorError,
    GeminiEditorNotConfigured,
    interpret_edit,
)
from app.gemini_video_editor import (
    GEMINI_VIDEO_MODEL,
    GeminiVideoEditError,
    edit_video,
)
from app.prompt_parser import parse_prompt
from app.video_processor import VideoProbeError, check_ffmpeg, probe_video, process_video

# ─── Directories ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
logger = logging.getLogger(__name__)

# ─── In-memory job store (good enough for a student project) ──────────────────
jobs: dict[str, dict] = {}

# ─── FastAPI App ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="PS2 – Prompt-Based Video Editing Engine",
    description="Edit videos using plain-English prompts. Powered by FFmpeg.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve processed output files
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")


# ─── Pydantic Models ──────────────────────────────────────────────────────────
class ProcessRequest(BaseModel):
    job_id: str
    prompt: str
    mode: Literal["standard", "generative"] = "standard"


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class ChatPreviewRequest(BaseModel):
    prompt: str
    history: list[ChatTurn] = Field(default_factory=list)


class VideoMetadata(BaseModel):
    duration: float
    width: int
    height: int
    has_audio: bool
    video_codec: Optional[str] = None


class JobStatus(BaseModel):
    job_id: str
    status: str           # "uploaded" | "parsing" | "processing" | "done" | "failed"
    progress: int         # 0–100
    message: str
    filename: Optional[str] = None
    output_url: Optional[str] = None
    operations: Optional[list] = None
    warnings: Optional[list] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    file_size_mb: Optional[float] = None
    metadata: Optional[VideoMetadata] = None


# ─── Background Processing ────────────────────────────────────────────────────
async def run_processing(job_id: str, prompt: str):
    """Runs in background: parse prompt → FFmpeg → update job status."""
    job = jobs.get(job_id)
    if job is None:
        logger.error("Cannot process missing job %s", job_id)
        return

    try:
        if job.get("mode") == "generative":
            job["status"] = "processing"
            job["progress"] = 20
            job["message"] = "Preparing AI video edit..."
            input_path = str(UPLOAD_DIR / job["filename"])
            output_filename = f"output_{job_id}.mp4"
            output_path = str(OUTPUT_DIR / output_filename)

            def update_ai_progress(message: str, progress: int) -> None:
                job["message"] = message
                job["progress"] = progress

            await asyncio.to_thread(
                edit_video,
                input_path,
                output_path,
                prompt,
                update_ai_progress,
            )
            metadata = await asyncio.to_thread(probe_video, output_path)
            job["status"] = "done"
            job["progress"] = 100
            job["message"] = "AI-edited video generated and validated."
            job["operations"] = [{
                "operation": "generative",
                "description": f"AI video edit: {prompt}",
                "params": {},
            }]
            job["output_url"] = f"/outputs/{output_filename}"
            job["output_filename"] = output_filename
            job["file_size_mb"] = round(Path(output_path).stat().st_size / (1024 * 1024), 2)
            job["metadata"] = metadata
            return

        # Stage 1: Parse
        job["status"] = "parsing"
        job["progress"] = 20
        job["message"] = "Parsing your prompt..."

        parse_result = parse_prompt(prompt)
        job["operations"] = [
            {"operation": op.operation, "description": op.description, "params": op.params}
            for op in parse_result.operations
        ]
        job["warnings"] = parse_result.warnings

        if not parse_result.understood:
            job["status"] = "failed"
            job["progress"] = 0
            job["error"] = parse_result.warnings[0] if parse_result.warnings else "Could not understand prompt."
            job["message"] = "Failed to parse prompt."
            return

        job["progress"] = 35
        job["message"] = f"Understood {len(parse_result.operations)} operation(s). Preparing FFmpeg..."

        # Stage 2: Process
        job["status"] = "processing"
        input_path = str(UPLOAD_DIR / job["filename"])
        output_filename = f"output_{job_id}.mp4"
        output_path = str(OUTPUT_DIR / output_filename)
        job["progress"] = 40
        job["message"] = "FFmpeg is processing the video..."

        def update_progress(message: str, progress: int) -> None:
            job["message"] = message
            job["progress"] = progress

        result = await asyncio.to_thread(
            process_video, input_path, output_path, parse_result, update_progress
        )

        if result["success"]:
            job["status"] = "done"
            job["progress"] = 100
            job["message"] = "Video processed successfully!"
            job["output_url"] = f"/outputs/{output_filename}"
            job["output_filename"] = output_filename
            job["file_size_mb"] = result.get("file_size_mb", 0)
            job["metadata"] = result["metadata"]
        else:
            job["status"] = "failed"
            job["error"] = result.get("error", "Unknown FFmpeg error.")
            job["message"] = "Video processing failed."
            job["ffmpeg_stderr"] = result.get("stderr", "")

    except Exception as e:
        logger.exception("Unexpected processing error for job %s", job_id)
        job["status"] = "failed"
        job["error"] = str(e)
        job["message"] = "An unexpected error occurred."


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check — also reports FFmpeg status."""
    ffmpeg = check_ffmpeg()
    return {
        "status": "ok",
        "ffmpeg": ffmpeg,
        "ffprobe": {
            "available": ffmpeg.get("ffprobe_available", False),
            "path": ffmpeg.get("ffprobe_path"),
        },
        "chat_model": {
            "configured": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
            "model": "gemini-3.8-flash",
        },
        "video_edit_model": {
            "configured": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
            "model": GEMINI_VIDEO_MODEL,
        },
        "upload_dir": str(UPLOAD_DIR),
        "output_dir": str(OUTPUT_DIR),
    }


@app.post("/upload", response_model=JobStatus)
async def upload_video(file: UploadFile = File(...)):
    """
    Upload a video file.
    Returns a job_id to track processing.
    Accepts: mp4, mov, avi, mkv, webm
    Max recommended size: 500MB
    """
    allowed_extensions = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(allowed_extensions))}"
        )

    job_id = str(uuid.uuid4())
    safe_filename = f"{job_id}{ext}"
    upload_path = UPLOAD_DIR / safe_filename

    try:
        async with aiofiles.open(upload_path, "wb") as destination:
            size = 0
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Video exceeds the 500 MB upload limit.")
                await destination.write(chunk)

        metadata = await asyncio.to_thread(probe_video, str(upload_path))
    except HTTPException:
        upload_path.unlink(missing_ok=True)
        raise
    except VideoProbeError as e:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Invalid video file: {e}") from e
    except OSError as e:
        upload_path.unlink(missing_ok=True)
        logger.exception("Could not save uploaded video")
        raise HTTPException(status_code=500, detail="Could not save uploaded video.") from e

    jobs[job_id] = {
        "job_id": job_id,
        "status": "uploaded",
        "progress": 10,
        "message": "Video uploaded and inspected successfully. Ready to process.",
        "filename": safe_filename,
        "original_name": filename,
        "file_size_mb": round(size / (1024 * 1024), 2),
        "metadata": metadata,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "output_url": None,
        "operations": None,
        "warnings": None,
        "error": None,
    }

    return jobs[job_id]


@app.post("/process", response_model=JobStatus)
async def process(req: ProcessRequest, background_tasks: BackgroundTasks):
    """
    Start processing a previously uploaded video with a natural-language prompt.
    Processing runs in the background — poll /status/{job_id} for updates.
    """
    if req.job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job '{req.job_id}' not found.")
    if not req.prompt.strip():
        raise HTTPException(status_code=422, detail="Enter an editing prompt.")
    if len(req.prompt) > 2000:
        raise HTTPException(status_code=422, detail="Prompt must be 2,000 characters or fewer.")

    job = jobs[req.job_id]
    if job["status"] in ("processing", "parsing"):
        raise HTTPException(status_code=409, detail="Job is already being processed.")

    # Reset for re-processing (user can refine and retry)
    job["status"] = "parsing"
    job["progress"] = 10
    job["message"] = "Starting..."
    job["prompt"] = req.prompt
    job["mode"] = req.mode
    job["output_url"] = None
    job["error"] = None
    job["ffmpeg_stderr"] = None

    background_tasks.add_task(run_processing, req.job_id, req.prompt)
    return job


@app.get("/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    """Poll this endpoint to get real-time processing status."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return jobs[job_id]


@app.get("/download/{job_id}")
async def download(job_id: str):
    """Download the processed video."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found.")
    job = jobs[job_id]
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Video is not ready yet.")

    output_path = OUTPUT_DIR / f"output_{job_id}.mp4"
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Output file not found.")

    return FileResponse(
        path=str(output_path),
        media_type="video/mp4",
        filename=f"ps2_edited_{job_id[:8]}.mp4"
    )


@app.get("/parse-preview")
async def parse_preview(prompt: str = Query(max_length=2000)):
    """
    Preview what operations would be applied for a given prompt.
    Useful for showing users what will happen before they commit.
    """
    result = parse_prompt(prompt)
    return {
        "understood": result.understood,
        "operations": [
            {"operation": op.operation, "description": op.description, "params": op.params}
            for op in result.operations
        ],
        "warnings": result.warnings,
        "prompt": prompt,
    }


@app.post("/chat-preview")
async def chat_preview(req: ChatPreviewRequest):
    """Interpret a conversational edit request and validate its operation plan."""
    if not req.prompt.strip():
        raise HTTPException(status_code=422, detail="Enter an editing instruction.")
    if len(req.prompt) > 2000:
        raise HTTPException(status_code=422, detail="Prompt must be 2,000 characters or fewer.")
    if len(req.history) > 20:
        raise HTTPException(status_code=422, detail="Chat history is too long. Start a new chat.")
    if any(turn.role not in ("user", "assistant") for turn in req.history):
        raise HTTPException(status_code=422, detail="Chat history contains an invalid role.")

    try:
        return await asyncio.to_thread(
            interpret_edit,
            req.prompt,
            [{"role": "user" if turn.role == "user" else "model", "text": turn.text}
             for turn in req.history],
        )
    except GeminiEditorError as error:
        logger.warning("Gemini could not interpret an editing request: %s", error)
        result = parse_prompt(req.prompt)
        operations = [
            {"operation": op.operation, "description": op.description, "params": op.params}
            for op in result.operations
        ]
        fallback_warning = (
            "Gemini is unavailable; using the local parser, which supports standard edits only."
        )
        return {
            "understood": result.understood,
            "operations": operations,
            "warnings": [*result.warnings, fallback_warning],
            "prompt": req.prompt if result.understood else "",
            "reply": (
                "I interpreted this with the local editor. Review the supported edits below."
                if result.understood
                else "Gemini is unavailable, and the local editor could not match this request. "
                     "Try a supported standard edit or configure GEMINI_API_KEY."
            ),
            "mode": "standard",
        }


@app.get("/jobs")
async def list_jobs():
    """List all jobs (for debugging)."""
    return {"total": len(jobs), "jobs": list(jobs.values())}


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Clean up job files."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found.")
    if jobs[job_id]["status"] in ("parsing", "processing"):
        raise HTTPException(status_code=409, detail="Cannot delete a job while it is processing.")
    job = jobs.pop(job_id)
    # Delete files
    for fname in [job.get("filename"), f"output_{job_id}.mp4"]:
        if fname:
            for d in [UPLOAD_DIR, OUTPUT_DIR]:
                p = d / fname
                if p.exists():
                    p.unlink()
    return {"deleted": job_id}
