import { getDownloadUrl } from '../api';
import type { JobStatus } from '../api';

interface StatusPanelProps {
  job: JobStatus;
}

const STATUS_LABELS: Record<string, string> = {
  uploaded: 'Uploaded',
  parsing: 'Parsing Prompt',
  processing: 'Processing',
  done: 'Complete',
  failed: 'Failed',
};

const STATUS_DOTS: Record<string, string> = {
  uploaded: '●', parsing: '●', processing: '●', done: '✓', failed: '✕',
};

function OperationIcon({ op }: { op: string }) {
  const icons: Record<string, string> = {
    trim: '✂️', mute: '🔇', volume: '🔊', aspect_ratio: '📐',
    speed: '⚡', rotate: '🔄', resolution: '📺', grayscale: '🎞️',
  };
  return <span>{icons[op] || '🎬'}</span>;
}

export function StatusPanel({ job }: StatusPanelProps) {
  const isProcessing = job.status === 'parsing' || job.status === 'processing';
  const isDone = job.status === 'done';
  const isFailed = job.status === 'failed';

  return (
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Status + Progress */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div className={`status-badge status-${job.status}`}>
            {isProcessing && (
              <span className="animate-spin" style={{ display: 'inline-block', width: 10, height: 10, border: '2px solid currentColor', borderTopColor: 'transparent', borderRadius: '50%' }} />
            )}
            {!isProcessing && <span>{STATUS_DOTS[job.status]}</span>}
            {STATUS_LABELS[job.status] || job.status}
          </div>
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{job.progress}%</span>
        </div>

        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${job.progress}%` }} />
        </div>

        <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>{job.message}</p>
      </div>

      {job.metadata && (
        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
          Video details: {job.metadata.width} × {job.metadata.height} · {job.metadata.duration.toFixed(1)}s ·{' '}
          {job.metadata.has_audio ? 'audio present' : 'no audio'}
        </div>
      )}

      {/* Operations applied */}
      {job.operations && job.operations.length > 0 && (
        <div>
          <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
            Operations Applied
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {job.operations.map((op, i) => (
              <div key={i} className="op-tag" style={{ width: 'fit-content' }}>
                <OperationIcon op={op.operation} />
                {op.description}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Warnings */}
      {job.warnings && job.warnings.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {job.warnings.map((w, i) => (
            <div key={i} className="warning-box">⚠️ {w}</div>
          ))}
        </div>
      )}

      {/* Error */}
      {isFailed && job.error && (
        <div>
          <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--danger)', marginBottom: 8 }}>Error Details</p>
          <div className="error-box">{job.error}</div>
        </div>
      )}

      {/* Download section */}
      {isDone && job.output_url && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <hr className="divider" style={{ margin: '4px 0' }} />

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <p style={{ fontSize: 15, fontWeight: 600, color: 'var(--success)', marginBottom: 4 }}>
                ✅ Video Ready!
              </p>
              {job.file_size_mb !== undefined && (
                <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  Output size: {job.file_size_mb} MB
                </p>
              )}
            </div>
            <a
              id="download-btn"
              href={getDownloadUrl(job.job_id)}
              download={`ps2_edited_${job.job_id.slice(0, 8)}.mp4`}
              className="btn-success"
              style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 8 }}
            >
              ⬇️ Download MP4
            </a>
          </div>

          {/* Video Preview */}
          <video
            id="output-preview"
            className="video-preview"
            controls
            src={job.output_url}
            style={{ width: '100%', marginTop: 8 }}
          >
            Your browser does not support video preview.
          </video>
        </div>
      )}
    </div>
  );
}
