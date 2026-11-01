import { useEffect, useRef, useState, type ReactNode } from "react";
import { copy } from "../../lib/copy";

type CopySource = string | (() => string);

export default function CopyButton({
  text,
  label,
  successMessage,
  failureMessage,
  className = "plain-button",
  children,
}: {
  text: CopySource;
  label: string;
  successMessage: string;
  failureMessage: string;
  className?: string;
  children?: ReactNode;
}) {
  const [result, setResult] = useState<{
    source: CopySource;
    status: "copied" | "failed";
  } | null>(null);
  const status = result?.source === text ? result.status : null;
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const version = useRef(0);
  const pending = useRef(false);
  useEffect(() => {
    setResult(null);
    return () => {
      version.current++;
      pending.current = false;
      clearTimeout(timer.current);
    };
  }, [text]);

  async function performCopy() {
    if (pending.current) return;
    pending.current = true;
    const current = ++version.current;
    clearTimeout(timer.current);
    setResult(null);
    try {
      await navigator.clipboard.writeText(
        typeof text === "function" ? text() : text,
      );
      if (current !== version.current) return;
      setResult({ source: text, status: "copied" });
      timer.current = setTimeout(() => {
        if (current === version.current) setResult(null);
      }, 2000);
    } catch {
      if (current === version.current)
        setResult({ source: text, status: "failed" });
    } finally {
      if (current === version.current) pending.current = false;
    }
  }

  return (
    <>
      <button
        type="button"
        className={`copy-control ${className}`}
        aria-label={label}
        onClick={() => void performCopy()}
      >
        {children}
        <span className="copy-label" data-label={label}>
          <span>{status === "copied" ? copy.copied : label}</span>
        </span>
      </button>
      {status === "copied" && (
        <span className="sr-only" role="status">
          {successMessage}
        </span>
      )}
      {status === "failed" && (
        <span className="error copy-error" role="alert">
          {failureMessage}
        </span>
      )}
    </>
  );
}
