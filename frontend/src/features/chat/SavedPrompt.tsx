import { copy } from "../../lib/copy";
import CopyButton from "./CopyButton";

export default function SavedPrompt({
  text,
  className = "user-message",
}: {
  text: string;
  className?: string;
}) {
  return (
    <div className="saved-prompt">
      <div className={className}>{text}</div>
      {text && (
        <div className="prompt-actions">
          <CopyButton
            text={text}
            label={copy.copyPrompt}
            successMessage={copy.promptCopied}
            failureMessage={copy.promptCopyFailed}
            className="plain-button prompt-copy"
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
          </CopyButton>
        </div>
      )}
    </div>
  );
}
