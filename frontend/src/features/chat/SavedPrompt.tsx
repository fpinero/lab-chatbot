import { useState } from "react";
import { copy } from "../../lib/copy";

export default function SavedPrompt({
  text,
  className = "user-message",
}: {
  text: string;
  className?: string;
}) {
  const [result, setResult] = useState<{
    text: string;
    status: "copied" | "failed";
  } | null>(null);
  const status = result?.text === text ? result.status : null;

  async function copyPrompt() {
    try {
      await navigator.clipboard.writeText(text);
      setResult({ text, status: "copied" });
    } catch {
      setResult({ text, status: "failed" });
    }
  }

  return (
    <div className="saved-prompt">
      <div className={className}>{text}</div>
      {text && (
        <div className="prompt-actions">
          <button
            type="button"
            className="plain-button prompt-copy"
            aria-label={copy.copyPrompt}
            onClick={() => void copyPrompt()}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
              aria-hidden="true"
            >
              <rect x="8" y="3" width="12" height="15" rx="3" />
              <path d="M5 7H4a1 1 0 0 0-1 1v11a3 3 0 0 0 3 3h9a1 1 0 0 0 1-1v-1" />
            </svg>
            {status === "copied" ? copy.copied : copy.copyPrompt}
          </button>
          {status === "copied" && (
            <span className="sr-only" role="status">
              {copy.promptCopied}
            </span>
          )}
          {status === "failed" && (
            <span className="error" role="alert">
              {copy.promptCopyFailed}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
