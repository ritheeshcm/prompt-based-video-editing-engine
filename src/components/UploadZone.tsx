import React, { useCallback, useState } from 'react';

interface UploadZoneProps {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
}

const ACCEPTED = ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska', 'video/webm'];
const MAX_SIZE_MB = 500;

export function UploadZone({ onFileSelected, disabled }: UploadZoneProps) {
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState('');

  const validate = (file: File): string => {
    if (!ACCEPTED.includes(file.type) && !file.name.match(/\.(mp4|mov|avi|mkv|webm|m4v)$/i)) {
      return `Unsupported format. Please upload MP4, MOV, AVI, MKV, or WebM.`;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      return `File too large (${(file.size / 1024 / 1024).toFixed(0)}MB). Max ${MAX_SIZE_MB}MB.`;
    }
    return '';
  };

  const handleFile = useCallback((file: File) => {
    const err = validate(file);
    if (err) { setError(err); return; }
    setError('');
    onFileSelected(file);
  }, [onFileSelected]);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (disabled) return;
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = ''; // reset so same file can be reselected
  };

  return (
    <div>
      <label
        id="upload-zone"
        className={`upload-zone flex flex-col items-center justify-center gap-4 p-10 select-none ${dragging ? 'dragging' : ''} ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
        onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        style={{ minHeight: '200px' }}
      >
        <input
          type="file"
          accept="video/*"
          className="hidden"
          onChange={onInputChange}
          disabled={disabled}
          id="file-input"
        />

        {/* Icon */}
        <div style={{
          width: 64, height: 64,
          background: 'linear-gradient(135deg, rgba(124,58,237,0.2), rgba(99,102,241,0.1))',
          border: '1px solid rgba(124,58,237,0.3)',
          borderRadius: 16,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 28,
          transition: 'transform 0.2s',
          transform: dragging ? 'scale(1.15)' : 'scale(1)',
        }}>
          🎬
        </div>

        <div style={{ textAlign: 'center' }}>
          <p style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>
            {dragging ? 'Drop it here!' : 'Drop your video here'}
          </p>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
            or <span style={{ color: 'var(--accent-light)', fontWeight: 500 }}>click to browse</span>
          </p>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>
            MP4 · MOV · AVI · MKV · WebM · M4V &nbsp;·&nbsp; Max {MAX_SIZE_MB}MB
          </p>
        </div>
      </label>

      {error && (
        <div className="error-box" style={{ marginTop: 12 }}>⚠️ {error}</div>
      )}
    </div>
  );
}
