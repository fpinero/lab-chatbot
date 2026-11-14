import { useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { AttachmentInfo } from "../../lib/api";
import { copy } from "../../lib/copy";

export default function ImagePreviewDialog({
  attachment,
  onDismiss,
  restoreFocus,
}: {
  attachment: AttachmentInfo;
  onDismiss: () => void;
  restoreFocus: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const backdropPressed = useRef(false);
  const anchor = useRef<{ x: number; y: number } | null>(null);
  const title = useId();
  const [bounds, setBounds] = useState({ width: 0, height: 0 });
  const [size, setSize] = useState<{ width: number; height: number } | null>(
    null,
  );
  const [failed, setFailed] = useState(false);
  const [zoom, setZoom] = useState<number | null>(null);
  const fit = size
    ? Math.min(
        1,
        Math.max(1, bounds.width) / size.width,
        Math.max(1, bounds.height) / size.height,
      )
    : 1;
  const scale = Math.max(fit, zoom ?? fit);
  const width = size ? Math.round(size.width * scale) : 0;
  const height = size ? Math.round(size.height * scale) : 0;

  useLayoutEffect(() => {
    const element = dialog.current!;
    const previousOverflow = document.body.style.overflow;
    const previousPriority =
      document.body.style.getPropertyPriority("overflow");
    document.body.style.overflow = "hidden";
    element.showModal();
    return () => {
      element.close();
      if (previousOverflow)
        document.body.style.setProperty(
          "overflow",
          previousOverflow,
          previousPriority,
        );
      else document.body.style.removeProperty("overflow");
      restoreFocus();
    };
  }, [restoreFocus]);

  useLayoutEffect(() => {
    const element = viewport.current!;
    const resize = () =>
      setBounds({ width: element.clientWidth, height: element.clientHeight });
    resize();
    if (typeof ResizeObserver !== "undefined") {
      const observer = new ResizeObserver(resize);
      observer.observe(element);
      return () => observer.disconnect();
    }
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  useLayoutEffect(() => {
    const element = viewport.current;
    const point = anchor.current;
    if (!element || !point) return;
    element.scrollLeft =
      Math.max(0, (bounds.width - width) / 2) +
      point.x * scale -
      bounds.width / 2;
    element.scrollTop =
      Math.max(0, (bounds.height - height) / 2) +
      point.y * scale -
      bounds.height / 2;
    anchor.current = null;
  }, [width, height, scale, bounds]);

  function changeZoom(next: number | null) {
    const element = viewport.current;
    if (element && size)
      anchor.current = {
        x:
          (element.scrollLeft +
            bounds.width / 2 -
            Math.max(0, (bounds.width - width) / 2)) /
          scale,
        y:
          (element.scrollTop +
            bounds.height / 2 -
            Math.max(0, (bounds.height - height) / 2)) /
          scale,
      };
    setZoom(next);
  }
  function dismiss() {
    dialog.current?.close();
    onDismiss();
  }
  return createPortal(
    <dialog
      ref={dialog}
      className="image-preview-dialog"
      aria-labelledby={title}
      onCancel={(event) => {
        event.preventDefault();
        dismiss();
      }}
      onKeyDown={(event) => {
        if (event.key === "Tab") {
          const controls = event.currentTarget.querySelectorAll<HTMLElement>(
            "button:not([disabled]), [tabindex='0']",
          );
          const first = controls[0],
            last = controls[controls.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
          }
        }
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          dismiss();
        }
      }}
      onPointerDown={(event) => {
        backdropPressed.current = event.target === event.currentTarget;
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget && backdropPressed.current)
          dismiss();
      }}
    >
      <div className="image-preview-panel">
        <div className="image-preview-heading">
          <h2 id={title}>{attachment.display_name}</h2>
          <button
            type="button"
            autoFocus
            aria-label={copy.closeImagePreview}
            title={copy.closeImagePreview}
            onClick={dismiss}
          >
            ×
          </button>
        </div>
        <div
          className="image-preview-toolbar"
          role="group"
          aria-label={copy.previewZoomControls}
        >
          <button
            type="button"
            aria-label={copy.previewZoomOut}
            title={copy.previewZoomOut}
            disabled={!size || scale <= fit}
            onClick={() => changeZoom(scale / 1.5 <= fit ? null : scale / 1.5)}
          >
            −
          </button>
          <button
            type="button"
            aria-label={copy.previewZoomIn}
            title={copy.previewZoomIn}
            disabled={!size || scale >= 4}
            onClick={() => changeZoom(Math.min(4, scale * 1.5))}
          >
            +
          </button>
          <button
            type="button"
            disabled={!size || zoom === null}
            onClick={() => changeZoom(null)}
          >
            {copy.previewFit}
          </button>
          <button
            type="button"
            disabled={!size || scale === 1}
            onClick={() => changeZoom(1)}
          >
            {copy.previewActualSize}
          </button>
          {size && (
            <output aria-label={copy.previewZoomLevel}>
              {Math.round(scale * 100)}%
            </output>
          )}
        </div>
        <div
          className="image-preview-viewport"
          ref={viewport}
          role="region"
          aria-label={copy.previewImageArea}
          tabIndex={0}
        >
          {!size && !failed && <p role="status">{copy.previewLoading}</p>}
          {failed && (
            <p className="error" role="alert">
              {copy.previewUnavailable}
            </p>
          )}
          <div
            className="image-preview-canvas"
            hidden={!size || failed}
            style={{
              width: Math.max(bounds.width, width),
              height: Math.max(bounds.height, height),
            }}
          >
            <img
              src={`/api/attachments/${encodeURIComponent(attachment.id)}`}
              alt={attachment.display_name}
              draggable={false}
              style={{ width, height }}
              onLoad={(event) => {
                const image = event.currentTarget;
                if (image.naturalWidth && image.naturalHeight) {
                  setSize({
                    width: image.naturalWidth,
                    height: image.naturalHeight,
                  });
                  setFailed(false);
                }
              }}
              onError={() => {
                setFailed(true);
                setSize(null);
              }}
            />
          </div>
        </div>
      </div>
    </dialog>,
    document.body,
  );
}
