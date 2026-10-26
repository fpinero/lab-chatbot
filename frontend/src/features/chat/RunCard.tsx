import type { ReactNode } from "react";
import type { RunInfo } from "../../lib/api";
import { copy } from "../../lib/copy";
import { AttachmentPreview } from "../attachments/AttachmentPicker";
import Markdown from "./Markdown";

export const usd = (micro: number) => `$${(micro / 1000000).toFixed(6)}`;
export default function RunCard({
  run,
  actions,
  showAttachments = true,
}: {
  run: RunInfo;
  actions?: ReactNode;
  showAttachments?: boolean;
}) {
  const inherited = run.accounting_state === "inherited";
  return (
    <article className="answer" aria-label={run.model_name}>
      <div className="answer-heading">
        <strong>{run.model_name}</strong>
        <span>{run.provider ?? copy.providerUnknown}</span>
        <span role="status">
          {copy.status[run.status as keyof typeof copy.status] ?? run.status}
        </span>
      </div>
      {inherited && <p className="notice">{copy.imported}</p>}
      {typeof run.settings.retry_of === "string" && (
        <p className="eyebrow">{copy.savedInput}</p>
      )}
      {showAttachments && <AttachmentPreview items={run.attachments ?? []} />}
      <Markdown text={run.output} />
      {Array.isArray(run.usage?.providers_seen) &&
        run.usage.providers_seen.length > 1 && (
          <p className="notice">
            {copy.routingChanged} {run.usage.providers_seen.join(", ")}
          </p>
        )}
      <div className="answer-meta">
        <span>
          {run.actual_microusd === null
            ? copy.unknownCost
            : `${inherited ? copy.originalCost : copy.actualCost}: ${usd(run.actual_microusd)}`}
        </span>
        {!inherited && (
          <span>
            {run.settings.estimate_kind === "vision_allowance"
              ? copy.visionAllowance
              : copy.reservation}
            : {usd(run.reserved_microusd)}
          </span>
        )}
        <span>
          {copy.maxTokens}: {String(run.settings.max_tokens ?? "")}
        </span>
        {run.settings.temperature !== null &&
          run.settings.temperature !== undefined && (
            <span>
              {copy.temperature}: {String(run.settings.temperature)}
            </span>
          )}
        {typeof run.queue_delay_ms === "number" && (
          <span>
            {copy.queuedFor}: {(run.queue_delay_ms / 1000).toFixed(2)} s
          </span>
        )}
        {run.started_at != null && (
          <span>
            {copy.startedAt}:{" "}
            {new Date(run.started_at * 1000).toLocaleTimeString()}
          </span>
        )}
        {run.first_token_ms != null && (
          <span>
            {copy.firstToken}: {(run.first_token_ms / 1000).toFixed(2)} s
          </span>
        )}
        {run.elapsed_ms != null && (
          <span>{(run.elapsed_ms / 1000).toFixed(2)} s</span>
        )}
        {typeof run.usage?.reasoning_tokens === "number" && (
          <span>
            {copy.reasoningTokens}: {run.usage.reasoning_tokens}
          </span>
        )}
        {run.usage?.prompt_tokens !== undefined && (
          <span>
            {String(run.usage.prompt_tokens)} /{" "}
            {String(run.usage.completion_tokens ?? "?")} tokens
          </span>
        )}
      </div>
      {run.error_code && (
        <p className="error">
          {copy.runFailed} ({run.error_code})
        </p>
      )}
      <div className="answer-actions">
        <button
          className="plain-button"
          onClick={() => {
            void navigator.clipboard
              .writeText(run.output)
              .catch(() => undefined);
          }}
        >
          {copy.copyResponse}
        </button>
        {actions}
      </div>
    </article>
  );
}
