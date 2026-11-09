import { useId, useRef, useState, type ReactNode } from "react";
import { copy } from "../../lib/copy";

export default function SidebarInfo({
  label,
  summary,
  children,
}: {
  label: string;
  summary?: string;
  children: ReactNode;
}) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);
  function dismiss() {
    panel.current?.hidePopover();
    trigger.current?.focus();
  }
  return (
    <>
      <button
        type="button"
        ref={trigger}
        className="sidebar-info-trigger"
        popoverTarget={id}
        aria-label={label}
        aria-controls={id}
        aria-expanded={expanded}
        aria-haspopup="dialog"
        aria-describedby={summary ? `${id}-summary` : undefined}
      >
        <span className="eyebrow">{label}</span>
        {summary && <span id={`${id}-summary`}>{summary}</span>}
      </button>
      <div
        ref={panel}
        id={id}
        popover="auto"
        role="dialog"
        aria-label={label}
        className="sidebar-info-popover"
        onToggle={(event) => {
          const open = event.currentTarget.matches(":popover-open");
          setExpanded(open);
          if (open) close.current?.focus({ preventScroll: true });
        }}
        onKeyDown={(event) => {
          if (event.key !== "Escape") return;
          event.preventDefault();
          event.stopPropagation();
          dismiss();
        }}
      >
        <div className="sidebar-info-heading">
          <strong>{label}</strong>
          <button
            type="button"
            className="plain-button"
            ref={close}
            aria-label={`${copy.closeInfo} ${label}`}
            onClick={dismiss}
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </>
  );
}
