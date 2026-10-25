import { useState, useEffect, useRef, useCallback } from 'react';
import { UploadZone } from './components/UploadZone';
import { ChatEditor } from './components/ChatEditor';
import { StatusPanel } from './components/StatusPanel';
import { uploadVideo, processVideo, getStatus, checkHealth } from './api';
import type { HealthStatus, JobStatus } from './api';
import './index.css';

type AppStep = 'idle' | 'uploading' | 'ready' | 'processing' | 'done' | 'failed';

export default function App() {
  const [step, setStep] = useState<AppStep>('idle');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [healthError, setHealthError] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Check backend health on mount
  useEffect(() => {
    checkHealth()
      .then(setHealth)
      .catch((error: unknown) => {
        const detail = error instanceof Error ? error.message : 'Connection failed.';
        setHealthError(`Backend not reachable (${detail}). Start it with: .\\venv\\Scripts\\uvicorn.exe main:app --reload --port 8000`);
      });
  }, []);

  // Poll job status while processing
  const startPolling = useCallback((jobId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const status = await getStatus(jobId);
        setJob(status);
        if (status.status === 'done' || status.status === 'failed') {
          clearInterval(pollRef.current!);
          setStep(status.status === 'done' ? 'done' : 'failed');
        }
      } catch (e) {
        if (pollRef.current) clearInterval(pollRef.current);
        const message = e instanceof Error ? e.message : 'Could not retrieve job status.';
        setJob(current => current ? {
          ...current,
          status: 'failed',
          message: 'Lost connection while checking the job status.',
          error: message,
        } : current);
        setStep('failed');
      }
    }, 1000);
  }, []);

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const handleFileSelected = async (file: File) => {
    setSelectedFile(file);
    setStep('uploading');
    setUploadProgress(0);
    setJob(null);

    try {
      const result = await uploadVideo(file, setUploadProgress);
      setJob(result);
      setStep('ready');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Upload failed';
      setJob({ job_id: '', status: 'failed', progress: 0, message: msg, error: msg });
      setStep('failed');
    }
  };

  const handleProcess = async (prompt: string, mode: 'standard' | 'generative') => {
    if (!job?.job_id) return;
    setStep('processing');
    try {
      const result = await processVideo(job.job_id, prompt, mode);
      setJob(result);
      startPolling(result.job_id);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Processing failed';
      setJob(prev => prev ? { ...prev, status: 'failed', error: msg, message: msg } : null);
      setStep('failed');
    }
  };

  const handleReset = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    setStep('idle');
    setJob(null);
    setSelectedFile(null);
    setUploadProgress(0);
  };

  const isProcessing = step === 'processing';
  const isUploading = step === 'uploading';
  const showStatus = step !== 'idle' && step !== 'uploading' && job;

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>

      {/* Background decoration */}
      <div style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, pointerEvents: 'none', overflow: 'hidden', zIndex: 0,
      }}>
        <div style={{
          position: 'absolute', top: '-20%', left: '30%',
          width: 600, height: 600,
          background: 'radial-gradient(circle, rgba(124,58,237,0.08) 0%, transparent 70%)',
          borderRadius: '50%',
        }} />
        <div style={{
          position: 'absolute', bottom: '-10%', right: '20%',
          width: 400, height: 400,
          background: 'radial-gradient(circle, rgba(99,102,241,0.06) 0%, transparent 70%)',
          borderRadius: '50%',
        }} />
      </div>

      <div style={{ position: 'relative', zIndex: 1, maxWidth: 860, margin: '0 auto', padding: '40px 24px 80px' }}>

        {/* Header */}
        <header style={{ textAlign: 'center', marginBottom: 48 }}>
          <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: '0.12em', color: 'var(--accent-light)', textTransform: 'uppercase', marginBottom: 12 }}>
            Google Antigravity · Student Project
          </div>
          <h1 style={{ fontSize: 'clamp(32px, 5vw, 52px)', fontWeight: 800, lineHeight: 1.15, marginBottom: 16 }}>
            <span className="gradient-text">PS2</span>
            <br />
            <span style={{ color: 'var(--text-primary)', fontSize: '0.65em', fontWeight: 600 }}>
              Prompt-Based Video Editing Engine
            </span>
          </h1>
          <p style={{ fontSize: 16, color: 'var(--text-secondary)', maxWidth: 540, margin: '0 auto', lineHeight: 1.7 }}>
            Upload a video, describe your edits in chat, review what the engine understood, and let FFmpeg handle the rest.
          </p>

          {/* Backend health indicator */}
          <div style={{ marginTop: 20, display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
            {healthError ? (
              <div className="warning-box" style={{ padding: '6px 14px' }}>⚠️ {healthError}</div>
            ) : health ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--success)', display: 'inline-block' }} />
                <span style={{ color: 'var(--text-muted)' }}>Backend connected</span>
                {health.ffmpeg.available ? (
                  <span className="chip">FFmpeg {health.ffmpeg.version?.split(' ')[2] || 'ready'}</span>
                ) : (
                  <span className="chip" style={{ color: 'var(--danger)' }}>FFmpeg missing</span>
                )}
                {!health.ffprobe.available && (
                  <span className="chip" style={{ color: 'var(--danger)' }}>FFprobe missing</span>
                )}
                {health.chat_model?.configured ? (
                  <span className="chip">Gemini chat ready</span>
                ) : (
                  <span className="chip" style={{ color: 'var(--warning)' }}>Gemini API key needed</span>
                )}
              </div>
            ) : (
              <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Checking backend...</span>
            )}
          </div>
        </header>

        {/* Main content */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

          {/* Step 1: Upload */}
          <div className="glass-card" style={{ padding: 28 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: 8,
                  background: step !== 'idle' ? 'linear-gradient(135deg, var(--accent), #6366f1)' : 'rgba(255,255,255,0.06)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 14, fontWeight: 700, color: 'white',
                }}>
                  {step !== 'idle' ? '✓' : '1'}
                </div>
                <div>
                  <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>Upload Video</h2>
                  {selectedFile && (
                    <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: 0 }}>
                      {selectedFile.name} · {(selectedFile.size / 1024 / 1024).toFixed(1)} MB
                    </p>
                  )}
                </div>
              </div>
              {step !== 'idle' && (
                <button id="reset-btn" className="btn-secondary" onClick={handleReset} style={{ fontSize: 12, padding: '6px 14px' }}>
                  Start Over
                </button>
              )}
            </div>

            {step === 'idle' && (
              <UploadZone onFileSelected={handleFileSelected} />
            )}

            {isUploading && (
              <div style={{ padding: '24px 0' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: 'var(--text-secondary)', marginBottom: 10 }}>
                  <span>Uploading {selectedFile?.name}...</span>
                  <span>{uploadProgress}%</span>
                </div>
                <div className="progress-track">
                  <div className="progress-fill" style={{ width: `${uploadProgress}%` }} />
                </div>
              </div>
            )}

            {step !== 'idle' && !isUploading && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px', background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.2)', borderRadius: 10 }}>
                <span style={{ fontSize: 18 }}>✅</span>
                <div>
                  <p style={{ fontSize: 14, fontWeight: 600, color: 'var(--success)', margin: 0 }}>Video uploaded</p>
                  <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: 0 }}>{selectedFile?.name} · Ready to edit</p>
                </div>
              </div>
            )}
          </div>

          {/* Step 2: Describe the edit in chat */}
          <div className="glass-card animate-fade-in" style={{ padding: 28 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: 8,
                  background: step === 'done' ? 'linear-gradient(135deg, var(--accent), #6366f1)' : 'linear-gradient(135deg, var(--accent), #6366f1)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 14, fontWeight: 700, color: 'white',
                }}>
                  2
                </div>
                <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
                  Chat About Your Edit
                </h2>
              </div>
              <ChatEditor
                onSubmit={handleProcess}
                canApply={Boolean(job?.job_id)}
                disabled={isProcessing || isUploading}
                loading={isProcessing}
              />
          </div>

          {/* Step 3: Status & Result */}
          {showStatus && (
            <div className="glass-card animate-fade-in" style={{ padding: 28 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: 8,
                  background: step === 'done' ? 'linear-gradient(135deg, #059669, #10b981)' : 'rgba(255,255,255,0.06)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 14, fontWeight: 700, color: 'white',
                }}>
                  3
                </div>
                <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
                  {step === 'done' ? 'Download Result' : 'Processing Status'}
                </h2>
              </div>
              <StatusPanel job={job} />
            </div>
          )}

          {/* Supported commands reference */}
          {step === 'idle' && (
            <div className="glass-card animate-fade-in" style={{ padding: 28 }}>
              <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 16, color: 'var(--text-primary)' }}>
                🧠 What Can You Say?
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
                {[
                  { icon: '✂️', label: 'Trim / Cut', example: '"Trim from 5 to 30 seconds"' },
                  { icon: '🔇', label: 'Mute Audio', example: '"Mute the audio"' },
                  { icon: '📐', label: 'Aspect Ratio', example: '"Convert to 9:16 portrait"' },
                  { icon: '⚡', label: 'Speed', example: '"Speed up to 2x"' },
                  { icon: '🎞️', label: 'Black & White', example: '"Make it grayscale"' },
                  { icon: '📺', label: 'Resolution', example: '"Scale to 1080p"' },
                  { icon: '🔄', label: 'Rotate / Flip', example: '"Flip horizontal"' },
                  { icon: '🔊', label: 'Volume', example: '"Increase volume by 50%"' },
                ].map(({ icon, label, example }) => (
                  <div key={label} style={{ padding: '12px 14px', background: 'rgba(255,255,255,0.03)', borderRadius: 10, border: '1px solid var(--border)' }}>
                    <div style={{ fontSize: 20, marginBottom: 6 }}>{icon}</div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>{label}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', fontStyle: 'italic' }}>{example}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <footer style={{ textAlign: 'center', marginTop: 60, color: 'var(--text-muted)', fontSize: 12 }}>
          PS2 · Prompt-Based Video Editing Engine · Built with React + FastAPI + FFmpeg
        </footer>
      </div>
    </div>
  );
}
