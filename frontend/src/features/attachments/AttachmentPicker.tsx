import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import {
  ApiError,
  attachmentApi,
  type AttachmentInfo,
  type UploadLimits,
} from "../../lib/api";
import { copy } from "../../lib/copy";

export function AttachmentPreview({ items }: { items: AttachmentInfo[] }) {
  return (
    <div className="attachment-list">
      {items.map((item) => (
        <div className="attachment-item" key={item.id}>
          {item.kind === "image" && (
            <img src={`/api/attachments/${item.id}`} alt={item.display_name} />
          )}
          <div>
            <strong>{item.display_name}</strong>
            <small>
              {item.kind === "image"
                ? `${item.width} × ${item.height}`
                : `${item.extracted_characters.toLocaleString()} ${copy.characters}`}
            </small>
            {item.warnings.map((warning) => (
              <small key={warning}>{warning}</small>
            ))}
            {item.kind === "document" && (
              <details>
                <summary>{copy.extractedPreview}</summary>
                <pre>{item.preview}</pre>
                {item.preview_truncated && (
                  <small>{copy.previewTruncated}</small>
                )}
              </details>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function AttachmentPicker({
  items,
  onChange,
  label,
  disabled = false,
  onFailure,
  onBusyChange,
  imageOnly = false,
  compact = false,
  children,
  options,
  actions,
  pasteTarget,
}: {
  items: AttachmentInfo[];
  onChange: (items: AttachmentInfo[]) => void;
  label: string;
  disabled?: boolean;
  onFailure: (error: unknown) => void;
  onBusyChange?: (busy: boolean) => void;
  imageOnly?: boolean;
  compact?: boolean;
  children?: ReactNode;
  options?: ReactNode;
  actions?: ReactNode;
  pasteTarget?: RefObject<HTMLTextAreaElement | null>;
}) {
  const [limits, setLimits] = useState<UploadLimits | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const optionsRef = useRef<HTMLDetailsElement>(null);
  const uploadPending = useRef(false);
  const mounted = useRef(false);
  const busyCallback = useRef(onBusyChange);
  useEffect(() => {
    busyCallback.current = onBusyChange;
  }, [onBusyChange]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (uploadPending.current) busyCallback.current?.(false);
    };
  }, []);
  useEffect(() => {
    let mounted = true;
    void attachmentApi
      .limits()
      .then((value) => {
        if (mounted) setLimits(value);
      })
      .catch((error) => {
        if (mounted) onFailure(error);
      });
    return () => {
      mounted = false;
    };
  }, []);
  useEffect(() => {
    setError("");
  }, [items]);
  useEffect(() => {
    if (!compact) return;
    const dismiss = (event: Event) => {
      const panel = optionsRef.current;
      if (panel?.open && !panel.contains(event.target as Node))
        panel.open = false;
    };
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("focusin", dismiss);
    return () => {
      document.removeEventListener("pointerdown", dismiss);
      document.removeEventListener("focusin", dismiss);
    };
  }, [compact]);
  const upload = useCallback(
    async (files: File[]) => {
      if (!files.length) return;
      if (disabled || uploadPending.current) {
        setError(
          disabled ? copy.attachmentsUnavailable : copy.uploadInProgress,
        );
        return;
      }
      if (files.length + items.length > (limits?.files ?? 5)) {
        setError(copy.tooManyFiles);
        return;
      }
      if (
        limits &&
        (files.some((file) => file.size > limits.file_bytes) ||
          files.reduce((total, file) => total + file.size, 0) >
            limits.total_bytes)
      ) {
        setError(copy.uploadTooLarge);
        return;
      }
      uploadPending.current = true;
      setBusy(true);
      onBusyChange?.(true);
      setError("");
      try {
        const result = await attachmentApi.upload(files);
        if (mounted.current) onChange([...items, ...result]);
      } catch (error) {
        if (!mounted.current) return;
        setError(error instanceof ApiError ? error.message : copy.uploadFailed);
        if (error instanceof ApiError && error.status === 401) onFailure(error);
      } finally {
        uploadPending.current = false;
        if (mounted.current) {
          setBusy(false);
          onBusyChange?.(false);
        }
      }
    },
    [disabled, items, limits, onBusyChange, onChange, onFailure],
  );
  useEffect(() => {
    const target = pasteTarget?.current;
    if (!target) return;
    const paste = (event: ClipboardEvent) => {
      const clipboard = event.clipboardData;
      if (!clipboard || target.disabled || target.readOnly) return;
      const imageItems = Array.from(clipboard.items ?? [])
        .filter(
          (item) => item.kind === "file" && item.type.startsWith("image/"),
        )
        .map((item) => item.getAsFile())
        .filter((file): file is File => file !== null);
      const files = imageItems.length
        ? imageItems
        : Array.from(clipboard.files ?? []).filter((file) =>
            file.type.startsWith("image/"),
          );
      if (!files.length) return;
      event.preventDefault();
      const extensions: Record<string, string> = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
      };
      if (files.some((file) => !extensions[file.type])) {
        setError(copy.clipboardImageUnsupported);
        return;
      }
      const stamp = new Date().toISOString().replace(/[:.]/g, "-");
      void upload(
        files.map(
          (file, index) =>
            new File(
              [file],
              `pasted-image-${stamp}-${index + 1}.${extensions[file.type]}`,
              { type: file.type },
            ),
        ),
      );
    };
    target.addEventListener("paste", paste);
    return () => target.removeEventListener("paste", paste);
  }, [pasteTarget, upload]);
  const control = (
    <label className="file-button" title={copy.pasteImagesHint}>
      {busy ? copy.uploading : compact ? copy.attachShort : copy.attachFiles}
      <input
        type="file"
        aria-label={label}
        multiple
        accept={
          imageOnly
            ? ".png,.jpg,.jpeg,.webp"
            : (limits?.allowed_extensions.join(",") ??
              ".png,.jpg,.jpeg,.webp,.pdf,.txt,.md,.csv,.docx")
        }
        disabled={disabled || busy}
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          event.target.value = "";
          void upload(files);
        }}
      />
    </label>
  );
  const limitNotice = limits && (
    <span className="upload-limits">
      {copy.uploadLimits(
        limits.files,
        limits.file_bytes / 1048576,
        limits.total_bytes / 1048576,
      )}
    </span>
  );
  const feedback = (
    <>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <AttachmentPreview items={items} />
      {items.map((item) => (
        <button
          className="plain-button"
          type="button"
          key={item.id}
          aria-label={`${copy.removeFromDraft}: ${item.display_name}`}
          onClick={() =>
            onChange(items.filter((value) => value.id !== item.id))
          }
          disabled={disabled || busy}
        >
          {copy.removeFromDraft}: {item.display_name}
        </button>
      ))}
      {items.length > 0 && (
        <small className="extraction-notice">
          {imageOnly ? copy.imageReferenceNotice : copy.extractionNotice}
        </small>
      )}
      {!imageOnly && items.some((item) => item.kind === "image") && limits && (
        <small className="extraction-notice">
          {limits.spend_control === "provider"
            ? copy.providerVision
            : limits.vision_allowance_microusd > 0
              ? `${copy.visionAllowance}: $${(limits.vision_allowance_microusd / 1000000).toFixed(6)}`
              : copy.visionUnconfigured}
        </small>
      )}
    </>
  );
  if (compact)
    return (
      <div className="attachment-picker compact-picker">
        {(items.length > 0 || error) && (
          <div className="attachment-feedback">{feedback}</div>
        )}
        {children}
        <div className="composer-toolbar">
          {control}
          <details
            ref={optionsRef}
            className="composer-options"
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.currentTarget.open = false;
                event.currentTarget
                  .querySelector<HTMLElement>("summary")
                  ?.focus();
              }
            }}
          >
            <summary>{copy.composerOptions}</summary>
            <div className="composer-options-content">
              <p>{limitNotice}</p>
              {options}
            </div>
          </details>
          <div className="composer-actions">{actions}</div>
        </div>
      </div>
    );
  return (
    <div className="attachment-picker">
      {control}
      {limitNotice}
      {feedback}
    </div>
  );
}
