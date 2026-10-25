// API client for PS2 backend

const BASE_URL = '';  // Uses Vite proxy in dev → '' means same origin

export interface JobStatus {
  job_id: string;
  status: 'uploaded' | 'parsing' | 'processing' | 'done' | 'failed';
  progress: number;
  message: string;
  filename?: string;
  output_url?: string;
  operations?: Array<{
    operation: string;
    description: string;
    params: Record<string, unknown>;
  }>;
  warnings?: string[];
  error?: string;
  created_at?: string;
  file_size_mb?: number;
  metadata?: VideoMetadata;
}

export interface VideoMetadata {
  duration: number;
  width: number;
  height: number;
  has_audio: boolean;
  video_codec?: string;
}

export interface ParsePreview {
  understood: boolean;
  operations: Array<{
    operation: string;
    description: string;
    params: Record<string, unknown>;
  }>;
  warnings: string[];
  prompt: string;
  reply?: string;
  mode?: 'standard' | 'generative';
}

export interface ChatTurn {
  role: 'user' | 'assistant';
  text: string;
}

export interface HealthStatus {
  status: string;
  ffmpeg: {
    available: boolean;
    version?: string;
    path?: string;
    error?: string;
  };
  ffprobe: {
    available: boolean;
    path?: string;
  };
  chat_model?: {
    configured: boolean;
    model: string;
  };
}

/** Upload a video file, returns initial job status */
export async function uploadVideo(file: File, onProgress?: (pct: number) => void): Promise<JobStatus> {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${BASE_URL}/upload`);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          reject(new Error('The server returned an invalid upload response.'));
        }
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || `Upload failed with status ${xhr.status}`));
        } catch {
          reject(new Error(`Upload failed with status ${xhr.status}`));
        }
      }
    };

    xhr.onerror = () => reject(new Error('Network error during upload.'));
    xhr.send(formData);
  });
}

/** Start processing a job with a natural-language prompt */
export async function processVideo(
  jobId: string,
  prompt: string,
  mode: 'standard' | 'generative' = 'standard',
): Promise<JobStatus> {
  const res = await fetch(`${BASE_URL}/process`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id: jobId, prompt, mode }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Process failed: ${res.status}`);
  }
  return res.json();
}

/** Poll job status */
export async function getStatus(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${BASE_URL}/status/${jobId}`);
  if (!res.ok) throw new Error(`Status check failed: ${res.status}`);
  return res.json();
}

/** Preview what a prompt would do (before processing) */
export async function parsePreview(prompt: string): Promise<ParsePreview> {
  const res = await fetch(`${BASE_URL}/parse-preview?prompt=${encodeURIComponent(prompt)}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Could not preview this prompt.' }));
    throw new Error(err.detail || `Preview failed: ${res.status}`);
  }
  return res.json();
}

/** Ask Gemini to interpret an edit request using the current conversation. */
export async function chatPreview(prompt: string, history: ChatTurn[]): Promise<ParsePreview> {
  const res = await fetch(`${BASE_URL}/chat-preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, history }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Could not understand this edit request.' }));
    throw new Error(err.detail || `Chat preview failed: ${res.status}`);
  }
  return res.json();
}

/** Check backend health + FFmpeg status */
export async function checkHealth(): Promise<HealthStatus> {
  const res = await fetch(`${BASE_URL}/health`);
  if (!res.ok) throw new Error('Backend not reachable');
  return res.json();
}

/** Get download URL for a completed job */
export function getDownloadUrl(jobId: string): string {
  return `${BASE_URL}/download/${jobId}`;
}
