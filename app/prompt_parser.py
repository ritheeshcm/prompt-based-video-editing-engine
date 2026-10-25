"""
PS2 Prompt Parser — Rule-based NLP engine
Converts plain-English prompts → structured FFmpeg edit instructions.
No AI API key required. Works 100% offline.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EditOperation:
    """A single video edit instruction parsed from a prompt."""
    operation: str          # e.g. "trim", "mute", "aspect_ratio", "speed", "volume"
    params: dict = field(default_factory=dict)
    description: str = ""   # Human-readable explanation shown to user


@dataclass
class ParseResult:
    """Full result of parsing a user prompt."""
    operations: list[EditOperation]
    raw_prompt: str
    understood: bool = True
    warnings: list[str] = field(default_factory=list)


def _parse_time(value: str) -> Optional[float]:
    """
    Convert a time string to seconds.
    Handles: "10", "10s", "1:30", "1m30s", "90 seconds"
    """
    value = value.strip().lower()

    # Format: mm:ss
    m = re.match(r"^(\d+):(\d{2})$", value)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))

    # Format: Xm Ys or XmYs
    m = re.match(r"^(?:(\d+)m)?(?:(\d+)s?)?$", value)
    if m:
        minutes = int(m.group(1) or 0)
        seconds = int(m.group(2) or 0)
        return minutes * 60 + seconds

    # Format: "90 seconds" / "10 sec"
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|s)$", value)
    if m:
        return float(m.group(1))

    # Plain number
    m = re.match(r"^(\d+(?:\.\d+)?)$", value)
    if m:
        return float(m.group(1))

    return None


def _extract_times(text: str):
    """
    Extract one or two time values from text.
    Returns (start, end) both as floats in seconds, or None if not found.
    Examples:
      "from 5 to 30 seconds" → (5.0, 30.0)
      "between 1:00 and 2:00" → (60.0, 120.0)
      "first 10 seconds"      → (0.0, 10.0)
      "last 20 seconds"       → needs duration — returns ("last", 20.0)
      "at 5 seconds"          → (5.0, None)
    """
    text = text.lower()

    # "first N seconds/minutes"
    m = re.search(r"first\s+(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|minutes?|mins?)?", text)
    if m:
        val = _parse_time(m.group(1) + ("m" if "min" in m.group(0) else "s"))
        return (0.0, val)

    # "last N seconds/minutes"
    m = re.search(r"last\s+(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|minutes?|mins?)?", text)
    if m:
        val = _parse_time(m.group(1) + ("m" if "min" in m.group(0) else "s"))
        return ("last", val)

    # "from X to Y" / "between X and Y"
    patterns = [
        r"from\s+([\d:ms]+)\s+to\s+([\d:ms]+)",
        r"between\s+([\d:ms]+)\s+and\s+([\d:ms]+)",
        r"([\d:ms]+)\s+(?:to|-)\s+([\d:ms]+)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            t1 = _parse_time(m.group(1))
            t2 = _parse_time(m.group(2))
            if t1 is not None and t2 is not None:
                return (t1, t2)

    # Single time: "at X" or "after X"
    m = re.search(r"(?:at|after)\s+([\d:ms]+)", text)
    if m:
        t = _parse_time(m.group(1))
        return (t, None)

    return (None, None)


def parse_prompt(prompt: str) -> ParseResult:
    """
    Main entry point: parse a user prompt into a list of EditOperations.
    """
    text = prompt.lower().strip()
    operations = []
    warnings = []
    if not text:
        return ParseResult(
            operations=[],
            raw_prompt=prompt,
            understood=False,
            warnings=["Enter an editing instruction before processing."],
        )

    if re.search(r"\b(?:combine|join|merge)\s+(?:the\s+)?(?:compatible\s+)?(?:clips?|videos?)\b", text):
        warnings.append(
            "Combining multiple clips is not supported yet. Upload one video and combine multiple edits in a prompt."
        )

    # ── TRIM ────────────────────────────────────────────────────────────────
    trim_keywords = ["trim", "cut", "keep", "clip", "extract", "start at", "end at",
                     "beginning", "first", "last", "shorten", "remove beginning",
                     "remove end", "crop to"]
    if any(kw in text for kw in trim_keywords):
        start, end = _extract_times(text)
        if start is not None or end is not None:
            params = {}
            if start == "last":
                params["from_end"] = end
                desc = f"Keep last {end}s of video"
            else:
                if start is not None:
                    params["start"] = start
                if end is not None:
                    params["end"] = end
                parts = []
                if start is not None:
                    parts.append(f"from {start}s")
                if end is not None:
                    parts.append(f"to {end}s")
                desc = "Trim video " + " ".join(parts)
            operations.append(EditOperation("trim", params, desc))
        else:
            warnings.append("Trim/cut detected but no time range found. Please specify e.g. 'trim from 5 to 30 seconds'.")

    # ── MUTE / AUDIO ────────────────────────────────────────────────────────
    mute_keywords = ["mute", "silence", "no audio", "no sound", "remove audio",
                     "remove sound", "strip audio", "without sound"]
    if any(kw in text for kw in mute_keywords):
        operations.append(EditOperation("mute", {}, "Remove all audio from video"))

    # ── VOLUME ──────────────────────────────────────────────────────────────
    m = re.search(
        r"(increase|boost|raise|decrease|lower|reduce)\s+(?:the\s+)?"
        r"(?:audio|volume|sound)\s+(?:by\s+)?(\d+(?:\.\d+)?)\s*(%|percent|db|x)?",
        text,
    )
    if m:
        direction = m.group(1)
        amount = float(m.group(2))
        suffix = (m.group(3) or "%").lower()
        
        if direction in ["increase", "boost", "raise"]:
            if "db" in suffix:
                factor = round(10 ** (amount / 20), 2)
            elif "x" in suffix:
                factor = amount
            else:
                factor = round(1 + amount / 100, 2)
            operations.append(EditOperation("volume", {"factor": factor}, f"Increase volume by {amount}{suffix}"))
        else:
            if "db" in suffix:
                factor = round(10 ** (-amount / 20), 2)
            elif "x" in suffix:
                factor = 1 / amount if amount > 0 else 0
            else:
                factor = round(1 - amount / 100, 2)
            operations.append(EditOperation("volume", {"factor": factor}, f"Decrease volume by {amount}{suffix}"))

    # ── ASPECT RATIO ────────────────────────────────────────────────────────
    ar_map = {
        "16:9": ("16:9", 1920, 1080, "landscape"),
        "9:16": ("9:16", 1080, 1920, "portrait"),
        "1:1": ("1:1", 1080, 1080, "square"),
        "4:3": ("4:3", 1440, 1080, "classic"),
        "21:9": ("21:9", 2560, 1080, "cinematic ultrawide"),
    }
    label_map = {
        "portrait": "9:16", "vertical": "9:16", "tiktok": "9:16",
        "instagram reel": "9:16", "reel": "9:16", "shorts": "9:16",
        "landscape": "16:9", "horizontal": "16:9", "youtube": "16:9",
        "widescreen": "16:9", "hd": "16:9",
        "square": "1:1", "instagram": "1:1",
        "cinematic": "21:9", "ultrawide": "21:9",
    }

    detected_ar = None
    for label, ar in label_map.items():
        if label in text:
            detected_ar = ar
            break
    if not detected_ar:
        m = re.search(r"(\d+)\s*:\s*(\d+)\s*(?:ratio|aspect)?", text)
        if m:
            detected_ar = f"{m.group(1)}:{m.group(2)}"

    if detected_ar and detected_ar in ar_map:
        ar, w, h, label = ar_map[detected_ar]
        operations.append(EditOperation(
            "aspect_ratio",
            {"ratio": ar, "width": w, "height": h},
            f"Convert to {ar} ({label}, {w}x{h})"
        ))
    elif detected_ar:
        warnings.append(f"Aspect ratio '{detected_ar}' is not a standard supported ratio.")

    # ── SPEED ────────────────────────────────────────────────────────────────
    speed_kw = ["speed up", "faster", "fast forward", "2x", "1.5x", "slow down",
                "slow motion", "slowmo", "half speed", "0.5x", "timelapse", "time-lapse"]
    if any(kw in text for kw in speed_kw):
        m = re.search(r"(\d+(?:\.\d+)?)\s*x\s*(?:speed)?", text)
        if m:
            factor = float(m.group(1))
        elif "slow" in text or "half" in text:
            factor = 0.5
        elif "timelapse" in text or "time-lapse" in text:
            factor = 4.0
        else:
            factor = 2.0

        operations.append(EditOperation(
            "speed",
            {"factor": factor},
            f"{'Speed up' if factor >= 1 else 'Slow down'} video to {factor}x"
        ))
        if factor <= 0 or factor > 16:
            warnings.append("Speed must be greater than 0 and no more than 16x.")

    # ── ROTATE ───────────────────────────────────────────────────────────────
    rotate_map = {
        r"rotate\s*(?:by\s*)?90": 90,
        r"rotate\s*(?:by\s*)?180": 180,
        r"rotate\s*(?:by\s*)?270": 270,
        r"flip\s*horizontal": "hflip",
        r"flip\s*vertical": "vflip",
    }
    for pattern, val in rotate_map.items():
        if re.search(pattern, text):
            operations.append(EditOperation(
                "rotate",
                {"angle": val},
                f"Rotate/flip: {val}"
            ))
            break
    rotate_request = re.search(r"\brotate\b(?:\s+by)?(?:\s+(\d+))?", text)
    if rotate_request and not any(op.operation == "rotate" for op in operations):
        requested_angle = rotate_request.group(1)
        warnings.append(
            f"Rotation{f' by {requested_angle} degrees' if requested_angle else ''} is unsupported. "
            "Use 90, 180, or 270 degrees, or request a horizontal/vertical flip."
        )

    # ── RESOLUTION ───────────────────────────────────────────────────────────
    res_map = {
        "4k": (3840, 2160), "2160p": (3840, 2160),
        "1080p": (1920, 1080), "full hd": (1920, 1080),
        "720p": (1280, 720), "hd ready": (1280, 720),
        "480p": (854, 480), "360p": (640, 360),
    }
    for label, (w, h) in res_map.items():
        if label in text:
            operations.append(EditOperation(
                "resolution",
                {"width": w, "height": h},
                f"Scale video to {label} ({w}x{h})"
            ))
            break
    resolution_request = re.search(r"\b(?:scale|resize|resolution)\b.{0,20}\b(\d{3,4})\s*p\b", text)
    if resolution_request and not any(op.operation == "resolution" for op in operations):
        warnings.append(
            f"Resolution {resolution_request.group(1)}p is unsupported. Use 720p, 1080p, or another listed resolution."
        )

    # ── GRAYSCALE ────────────────────────────────────────────────────────────
    if any(kw in text for kw in ["grayscale", "black and white", "black & white", "b&w", "greyscale", "monochrome"]):
        operations.append(EditOperation("grayscale", {}, "Convert video to black & white"))

    for operation in operations:
        params = operation.params
        if operation.operation == "trim":
            if "from_end" in params:
                valid = params["from_end"] is not None and params["from_end"] > 0
            else:
                start = params.get("start", 0)
                end = params.get("end")
                valid = start >= 0 and end is not None and end > start
            if not valid:
                warnings.append("Trim range must have a non-negative start and an end after the start.")
        elif operation.operation == "volume":
            factor = params.get("factor")
            if factor is None or not 0 <= factor <= 10:
                warnings.append("Volume adjustment must result in a factor between 0x and 10x.")

    if any(op.operation == "mute" for op in operations) and any(
        op.operation == "volume" for op in operations
    ):
        warnings.append("A volume change cannot be combined with muting the audio.")

    # ── NOTHING UNDERSTOOD ───────────────────────────────────────────────────
    if not operations:
        warnings.append("Could not understand the prompt. Supported commands: trim, mute, aspect ratio, speed, rotate, grayscale, resolution, volume.")
        return ParseResult(operations=[], raw_prompt=prompt, understood=False, warnings=warnings)

    return ParseResult(
        operations=operations,
        raw_prompt=prompt,
        understood=not warnings,
        warnings=warnings,
    )
