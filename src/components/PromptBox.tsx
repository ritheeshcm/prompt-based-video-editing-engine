import { useState, useRef, useEffect } from 'react';
import { parsePreview } from '../api';
import type { ParsePreview } from '../api';

const EXAMPLE_PROMPTS = [
  "Trim from 5 to 30 seconds and mute the audio",
  "Convert to 9:16 portrait for TikTok",
  "Speed up to 2x and convert to square 1:1",
  "Remove the first 10 seconds",
  "Make it black and white and slow down to 0.5x",
  "Convert to 1080p and mute",
  "Keep only the last 20 seconds",
  "Flip horizontal and convert to YouTube 16:9",
];

interface PromptBoxProps {
  onSubmit: (prompt: string) => void;
  disabled?: boolean;
  loading?: boolean;
}

function OperationIcon({ op }: { op: string }) {
  const icons: Record<string, string> = {
    trim: '✂️', mute: '🔇', volume: '🔊', aspect_ratio: '📐',
    speed: '⚡', rotate: '🔄', resolution: '📺', grayscale: '🎞️',
  };
  return <span>{icons[op] || '🎬'}</span>;
}

export function PromptBox({ onSubmit, disabled, loading }: PromptBoxProps) {
  const [prompt, setPrompt] = useState('');
  const [preview, setPreview] = useState<ParsePreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState('');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-preview with debounce as user types
  useEffect(() => {
    let cancelled = false;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (prompt.trim().length < 5) {
      setPreview(null);
      setPreviewError('');
      setPreviewing(false);
      return () => { cancelled = true; };
    }
    debounceRef.current = setTimeout(async () => {
      setPreviewing(true);
      try {
        const result = await parsePreview(prompt);
        if (!cancelled) {
          setPreview(result);
          setPreviewError('');
        }
      } catch (error) {
        if (!cancelled) {
          setPreview(null);
          setPreviewError(error instanceof Error ? error.message : 'Could not preview this prompt.');
        }
      } finally {
        if (!cancelled) setPreviewing(false);
      }
    }, 600);
    return () => {
      cancelled = true;
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [prompt]);

  const handleSubmit = () => {
    if (!prompt.trim() || disabled || loading) return;
    onSubmit(prompt.trim());
  };

  const useExample = (ex: string) => {
    setPrompt(ex);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Example prompts */}
      <div>
        <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
          Try an example
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {EXAMPLE_PROMPTS.map((ex) => (
            <button
              key={ex}
              className="chip"
              onClick={() => useExample(ex)}
              disabled={disabled}
              style={{ cursor: disabled ? 'not-allowed' : 'pointer', transition: 'all 0.15s', border: '1px solid var(--border)' }}
            >
              {ex}
            </button>
          ))}
        </div>
      </div>

      {/* Textarea */}
      <div>
        <textarea
          id="prompt-input"
          className="prompt-input"
          rows={4}
          maxLength={2000}
          placeholder={'Type what you want to do with the video...\ne.g. "Trim from 10 to 60 seconds, mute the audio, and convert to 9:16 portrait"'}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={disabled}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleSubmit();
          }}
        />
        <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6, textAlign: 'right' }}>
          Press <kbd style={{ fontFamily: 'JetBrains Mono', background: 'rgba(255,255,255,0.07)', padding: '1px 5px', borderRadius: 4, fontSize: 11 }}>Ctrl+Enter</kbd> to process
        </p>
      </div>

      {/* Live parse preview */}
      {previewing && (
        <div style={{ fontSize: 13, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="animate-spin" style={{ display: 'inline-block', width: 12, height: 12, border: '2px solid var(--accent)', borderTopColor: 'transparent', borderRadius: '50%' }} />
          Analyzing prompt...
        </div>
      )}

      {previewError && (
        <div className="error-box">{previewError}</div>
      )}

      {preview && !previewing && (
        <div className="animate-fade-in" style={{ borderRadius: 12, border: '1px solid var(--border)', padding: 14, background: 'rgba(255,255,255,0.02)' }}>
          <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
            Preview — what will happen
          </p>
          {preview.understood ? (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {preview.operations.map((op, i) => (
                <div key={i} className="op-tag">
                  <OperationIcon op={op.operation} />
                  {op.description}
                </div>
              ))}
            </div>
          ) : (
            <div className="warning-box">
              ⚠️ {preview.warnings[0] || "Could not understand this prompt."}
            </div>
          )}
          {preview.warnings?.length > 0 && preview.understood && (
            <div className="warning-box" style={{ marginTop: 10 }}>
              ⚠️ {preview.warnings.join(' ')}
            </div>
          )}
        </div>
      )}

      {/* Submit */}
      <button
        id="process-btn"
        className="btn-primary"
        onClick={handleSubmit}
        disabled={!prompt.trim() || !preview?.understood || previewing || !!previewError || disabled || loading}
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10 }}
      >
        {loading ? (
          <>
            <span className="animate-spin" style={{ display: 'inline-block', width: 16, height: 16, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: 'white', borderRadius: '50%' }} />
            Processing...
          </>
        ) : (
          <>🚀 Process Video</>
        )}
      </button>
    </div>
  );
}
