import { useState } from 'react';
import { chatPreview } from '../api';
import type { ChatTurn, ParsePreview } from '../api';

const EXAMPLE_PROMPTS = [
  'Trim from 5 to 30 seconds and mute the audio',
  'Convert to 9:16 portrait for TikTok',
  'Speed up to 2x and convert to square 1:1',
  'Make it black and white and slow down to 0.5x',
];

interface ChatMessage {
  role: 'assistant' | 'user';
  text: string;
  operations?: string[];
  mode?: 'standard' | 'generative';
}

interface ChatEditorProps {
  onSubmit: (prompt: string, mode: 'standard' | 'generative') => void;
  canApply?: boolean;
  disabled?: boolean;
  loading?: boolean;
}

export function ChatEditor({ onSubmit, canApply = true, disabled, loading }: ChatEditorProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([{
    role: 'assistant',
    text: 'Hi! Tell me how you want to edit your video. I’ll show you the changes I understood before processing it.',
  }]);
  const [prompt, setPrompt] = useState('');
  const [activePrompt, setActivePrompt] = useState('');
  const [activeMode, setActiveMode] = useState<'standard' | 'generative'>('standard');
  const [preview, setPreview] = useState<ParsePreview | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  const sendPrompt = async (text: string) => {
    const request = text.trim();
    if (!request || disabled || loading || analyzing) return;

    setMessages(current => [...current, { role: 'user', text: request }]);
    setPrompt('');
    setPreview(null);
    setActivePrompt('');
    setAnalyzing(true);

    try {
      const history: ChatTurn[] = messages.slice(-8).map(message => ({
        role: message.role,
        text: message.operations?.length
          ? `${message.text}\nPlanned operations: ${message.operations.join('; ')}`
          : message.text,
      }));
      const result = await chatPreview(request, history);
      setPreview(result);
      if (result.understood) {
        setActivePrompt(result.prompt);
        const mode = result.mode || 'standard';
        setActiveMode(mode);
        setMessages(current => [...current, {
          role: 'assistant',
          text: result.reply || 'I understood this edit. Review the plan, then apply it.',
          operations: result.operations.map(operation => operation.description),
          mode,
        }]);
      } else {
        setMessages(current => [...current, {
          role: 'assistant',
          text: result.reply || result.warnings[0] || 'I couldn’t understand that edit.',
        }]);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not analyze this edit. Please try again.';
      setMessages(current => [...current, { role: 'assistant', text: message }]);
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <section className="chat-editor" aria-label="Video editing chat">
      <div className="chat-messages" aria-live="polite">
        {messages.map((message, index) => (
          <div key={index} className={`chat-message chat-message-${message.role}`}>
            <div className="chat-avatar" aria-hidden="true">{message.role === 'assistant' ? '✦' : 'You'}</div>
            <div className="chat-bubble">
              {message.mode === 'generative' && <span className="chip">Gemini AI video edit</span>}
              <p>{message.text}</p>
              {message.operations && (
                <ul className="chat-operations">
                  {message.operations.map((operation, operationIndex) => (
                    <li key={`${operation}-${operationIndex}`}>{operation}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        ))}
        {analyzing && (
          <div className="chat-message chat-message-assistant" role="status">
            <div className="chat-avatar" aria-hidden="true">✦</div>
            <div className="chat-bubble chat-thinking">Checking the edit request…</div>
          </div>
        )}
      </div>

      {preview?.warnings.length ? (
        <div className="warning-box">{preview.warnings.join(' ')}</div>
      ) : null}
      <div className="chat-examples" aria-label="Example edit requests">
        {EXAMPLE_PROMPTS.map(example => (
          <button
            key={example}
            className="chip"
            type="button"
            onClick={() => void sendPrompt(example)}
            disabled={disabled || loading || analyzing}
          >
            {example}
          </button>
        ))}
      </div>

      <form
        className="chat-composer"
        onSubmit={event => {
          event.preventDefault();
          void sendPrompt(prompt);
        }}
      >
        <label className="sr-only" htmlFor="chat-prompt">Describe how to edit the video</label>
        <textarea
          id="chat-prompt"
          className="prompt-input chat-input"
          rows={2}
          maxLength={2000}
          placeholder="Describe how you want to edit the video…"
          value={prompt}
          onChange={event => setPrompt(event.target.value)}
          disabled={disabled || loading || analyzing}
          onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              void sendPrompt(prompt);
            }
          }}
        />
        <button
          className="btn-primary chat-send"
          type="submit"
          disabled={!prompt.trim() || disabled || loading || analyzing}
          aria-label="Send edit request"
        >
          Send
        </button>
      </form>
      <p className="chat-hint">Enter to send · Shift+Enter for a new line</p>
      <p className="chat-hint">
        AI video edits upload your video to Google Gemini. Provider usage charges may apply.
      </p>

      {activePrompt && (
        <button
          className="btn-primary chat-apply"
          type="button"
          onClick={() => onSubmit(activePrompt, activeMode)}
          disabled={!canApply || disabled || loading}
        >
          {loading
            ? activeMode === 'generative' ? 'Generating AI video edit…' : 'Processing video…'
            : canApply
              ? activeMode === 'generative' ? 'Generate edited video' : 'Apply these edits'
              : 'Upload a video to apply edits'}
        </button>
      )}
    </section>
  );
}
