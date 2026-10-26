import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  chatApi,
  comparisonApi,
  type AttachmentInfo,
  type CatalogInfo,
  type ComparisonInfo,
  type ComparisonStart,
  type ComparisonSummary,
  type ConversationDetail,
  type ConversationInfo,
  type RunInfo,
} from "../../lib/api";
import { copy } from "../../lib/copy";
import AttachmentPicker, {
  AttachmentPreview,
} from "../attachments/AttachmentPicker";
import RunCard from "../chat/RunCard";

export default function ComparisonPanel({
  hidden,
  catalog,
  conversation,
  replay,
  clearReplay,
  onConversation,
  onContinue,
  expired,
  onUsageChange,
}: {
  hidden: boolean;
  catalog: CatalogInfo;
  conversation: ConversationInfo | null;
  replay: RunInfo | null;
  clearReplay: () => void;
  onConversation: (conversation: ConversationInfo) => void;
  onContinue: (conversation: ConversationDetail) => void;
  expired: () => void;
  onUsageChange: () => void;
}) {
  const [selected, setSelected] = useState(
    catalog.models.slice(0, 2).map((model) => model.id),
  );
  const [draft, setDraft] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [maximum, setMaximum] = useState(2048);
  const [temperature, setTemperature] = useState("");
  const [files, setFiles] = useState<AttachmentInfo[]>([]);
  const [group, setGroup] = useState<ComparisonInfo | null>(null);
  const [history, setHistory] = useState<ComparisonSummary[]>([]);
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const resultsRef = useRef<HTMLDivElement>(null);
  const submitting = useRef(false);
  const pending = useRef<{ fingerprint: string; key: string } | null>(null);
  const retryKeys = useRef(new Map<string, string>());
  const acting = useRef(new Set<string>());
  const selectedModels = catalog.models.filter((model) =>
    selected.includes(model.id),
  );
  const replayFiles = replay?.attachments ?? [];
  const inputFiles = replay ? replayFiles : files;
  const incompatible =
    inputFiles.some((item) => item.kind === "image") &&
    selectedModels.some((model) => !model.input_modalities.includes("image"));
  const supportsTemperature =
    selectedModels.length > 0 &&
    selectedModels.every((model) =>
      model.supported_parameters.includes("temperature"),
    );
  const available = selectedModels.length === selected.length;

  function failed(error: unknown) {
    if (error instanceof ApiError && error.status === 401) expired();
    else setError(error instanceof ApiError ? error.message : copy.chatFailure);
  }
  useEffect(() => {
    let mounted = true;
    if (!conversation) {
      setHistory([]);
      setGroup(null);
      return;
    }
    void comparisonApi
      .history(conversation.id)
      .then(async (list) => {
        if (!mounted) return;
        setHistory(list);
        if (list[0]) {
          const latest = await comparisonApi.get(list[0].id);
          if (mounted)
            setGroup((previous) =>
              previous?.conversation_id === conversation.id ? previous : latest,
            );
        } else
          setGroup((previous) =>
            previous?.conversation_id === conversation.id ? previous : null,
          );
      })
      .catch((error) => {
        if (mounted) failed(error);
      });
    return () => {
      mounted = false;
    };
  }, [conversation?.id]);

  useEffect(() => {
    if (!group || group.status !== "running") return;
    let mounted = true;
    const timer = setInterval(() => {
      void comparisonApi
        .get(group.id)
        .then((value) => {
          if (mounted)
            setGroup((current) => (current?.id === value.id ? value : current));
        })
        .catch((error) => {
          if (mounted) failed(error);
        });
    }, 400);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [group?.id, group?.status]);

  useEffect(() => {
    if (!hidden) resultsRef.current?.scrollIntoView({ block: "start" });
  }, [group?.id, hidden]);

  const accounting = group?.candidates
    .map((run) => `${run.id}:${run.accounting_state}:${run.actual_microusd}`)
    .join("|");
  useEffect(() => {
    if (accounting) onUsageChange();
  }, [accounting]);

  async function reconcile(run: RunInfo) {
    try {
      await chatApi.reconcile(run.id);
      setGroup(await comparisonApi.get(run.comparison_id!));
      onUsageChange();
    } catch (error) {
      failed(error);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (
      submitting.current ||
      uploading ||
      selected.length < 2 ||
      selected.length > 4 ||
      !available ||
      incompatible ||
      (!replay && !draft.trim())
    )
      return;
    submitting.current = true;
    setBusy(true);
    setError("");
    setWarning("");
    try {
      const saved =
        conversation ??
        (await chatApi.create((replay?.prompt || draft).slice(0, 80)));
      onConversation(saved);
      const body: ComparisonStart = {
        conversation_id: saved.id,
        model_ids: selected,
        idempotency_key: crypto.randomUUID().replaceAll("-", ""),
        prompt: replay ? "" : draft.trim(),
        system_prompt: replay ? "" : systemPrompt,
        max_tokens: maximum,
        verification_run: false,
        attachment_ids: replay ? [] : files.map((item) => item.id),
        ...(replay ? { retry_of: replay.id } : {}),
        ...(supportsTemperature && temperature !== ""
          ? { temperature: Number(temperature) }
          : {}),
      };
      const fingerprint = JSON.stringify({ ...body, idempotency_key: "" });
      if (pending.current?.fingerprint === fingerprint)
        body.idempotency_key = pending.current.key;
      pending.current = { fingerprint, key: body.idempotency_key };
      const result = await comparisonApi.start(body);
      setGroup(result);
      pending.current = null;
      if (!replay) {
        setDraft((previous) => (previous === draft ? "" : previous));
        setFiles((previous) =>
          previous.filter((item) => !body.attachment_ids?.includes(item.id)),
        );
      }
      setHistory(await comparisonApi.history(saved.id));
    } catch (error) {
      failed(error);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  async function retry(run: RunInfo) {
    if (acting.current.has(run.id)) return;
    acting.current.add(run.id);
    setError("");
    try {
      const key =
        retryKeys.current.get(run.id) ??
        crypto.randomUUID().replaceAll("-", "");
      retryKeys.current.set(run.id, key);
      await chatApi.submit({
        conversation_id: run.conversation_id,
        model_id: run.model_id,
        idempotency_key: key,
        prompt: "",
        retry_of: run.id,
        system_prompt: "",
        verification_run: false,
        attachment_ids: [],
        max_tokens: Number(run.settings.max_tokens),
        ...(typeof run.settings.temperature === "number"
          ? { temperature: run.settings.temperature }
          : {}),
      });
      retryKeys.current.delete(run.id);
      setGroup(await comparisonApi.get(run.comparison_id!));
    } catch (error) {
      failed(error);
    } finally {
      acting.current.delete(run.id);
    }
  }

  async function stop(run: RunInfo) {
    try {
      await chatApi.cancel(run.id);
      setWarning(copy.stopNotice);
      setGroup(await comparisonApi.get(run.comparison_id!));
    } catch (error) {
      failed(error);
    }
  }
  async function continueAnswer(run: RunInfo) {
    if (acting.current.has(run.id)) return;
    acting.current.add(run.id);
    try {
      onContinue(await comparisonApi.fork(run.id));
    } catch (error) {
      failed(error);
    } finally {
      acting.current.delete(run.id);
    }
  }

  return (
    <section
      hidden={hidden}
      className="comparison-workspace"
      aria-label={copy.compare}
    >
      <div className="comparison-scroll">
        <fieldset className="candidate-picker">
          <legend>{copy.compareModels}</legend>
          {catalog.models.map((model) => (
            <label key={model.id}>
              <input
                type="checkbox"
                checked={selected.includes(model.id)}
                onChange={() =>
                  setSelected((values) =>
                    values.includes(model.id)
                      ? values.filter((id) => id !== model.id)
                      : values.length < 4
                        ? [...values, model.id]
                        : values,
                  )
                }
              />
              {model.name}
            </label>
          ))}
          {selected
            .filter((id) => !catalog.models.some((model) => model.id === id))
            .map((id) => (
              <label key={id}>
                <input
                  type="checkbox"
                  checked
                  onChange={() =>
                    setSelected((values) =>
                      values.filter((value) => value !== id),
                    )
                  }
                />
                {copy.modelUnavailable}: {id}
              </label>
            ))}
        </fieldset>
        <p className="comparison-notice">{copy.comparisonNotice}</p>
        {history.length > 0 && (
          <label className="saved-comparison">
            {copy.savedComparisons}
            <select
              value={group?.id ?? ""}
              onChange={(event) => {
                if (event.target.value)
                  void comparisonApi
                    .get(event.target.value)
                    .then(setGroup)
                    .catch(failed);
              }}
            >
              <option value="">{copy.noComparisons}</option>
              {history.map((item) => (
                <option value={item.id} key={item.id}>
                  {new Date(item.created_at * 1000).toLocaleString()} ·{" "}
                  {item.id.slice(0, 6)}
                </option>
              ))}
            </select>
          </label>
        )}
        {group && (
          <>
            <div className="snapshot-heading">
              <span>
                {copy.snapshot}: {group.snapshot_hash.slice(0, 12)}
              </span>
              <span role="status">
                {copy.status[group.status as keyof typeof copy.status] ??
                  group.status}
              </span>
            </div>
            <div className="user-message">{group.candidates[0]?.prompt}</div>
            <AttachmentPreview items={group.candidates[0]?.attachments ?? []} />
            <div className="comparison-results" ref={resultsRef}>
              {group.candidates.map((run) => (
                <RunCard
                  key={run.id}
                  run={run}
                  showAttachments={false}
                  actions={
                    <>
                      {["queued", "running", "cancel_requested"].includes(
                        run.status,
                      ) ? (
                        <button
                          className="plain-button"
                          onClick={() => void stop(run)}
                        >
                          {copy.stop}
                        </button>
                      ) : (
                        <button
                          className="plain-button"
                          onClick={() => void retry(run)}
                        >
                          {copy.retryCandidate}
                        </button>
                      )}
                      {run.accounting_state === "uncertain" && (
                        <button
                          className="plain-button"
                          onClick={() => void reconcile(run)}
                        >
                          {copy.reconcile}
                        </button>
                      )}
                      {run.status === "succeeded" && (
                        <button
                          className="plain-button"
                          onClick={() => void continueAnswer(run)}
                        >
                          {copy.continueAnswer}
                        </button>
                      )}
                    </>
                  }
                />
              ))}
            </div>
            {group.previous_runs_count > 0 && (
              <p className="comparison-notice">
                {copy.previousAttempts}: {group.previous_runs_count}
              </p>
            )}
          </>
        )}
      </div>
      <form
        className="chat-composer comparison-composer"
        onSubmit={(event) => void submit(event)}
      >
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {warning && (
          <p role="status" className="notice">
            {warning}
          </p>
        )}
        {incompatible && (
          <p role="alert" className="error">
            {copy.incompatibleFiles}
          </p>
        )}
        {replay ? (
          <div className="notice">
            {copy.savedInputNotice}
            <button
              type="button"
              className="plain-button"
              onClick={clearReplay}
            >
              {copy.newInput}
            </button>
          </div>
        ) : (
          <AttachmentPicker
            items={files}
            onChange={setFiles}
            label={copy.attachCompare}
            disabled={busy}
            onFailure={failed}
            onBusyChange={setUploading}
          />
        )}
        <details>
          <summary>{copy.advanced}</summary>
          <div className="advanced-grid">
            {!replay && (
              <label>
                {copy.systemPrompt}
                <textarea
                  rows={2}
                  value={systemPrompt}
                  maxLength={12000}
                  onChange={(event) => setSystemPrompt(event.target.value)}
                />
              </label>
            )}
            <label>
              {copy.maxTokens}
              <input
                type="number"
                min={1}
                max={2048}
                value={maximum}
                onChange={(event) => setMaximum(Number(event.target.value))}
              />
            </label>
            {supportsTemperature && (
              <label>
                {copy.temperature}
                <input
                  type="number"
                  min={0}
                  max={2}
                  step={0.1}
                  value={temperature}
                  onChange={(event) => setTemperature(event.target.value)}
                />
              </label>
            )}
          </div>
        </details>
        <section className="preview-panel">
          <div className="notice">
            {selectedModels.every((model) => model.simulated)
              ? copy.mockNotice
              : copy.privacy}
          </div>
          <label className="sr-only" htmlFor="comparison-prompt">
            {copy.comparePrompt}
          </label>
          <textarea
            id="comparison-prompt"
            rows={2}
            maxLength={24000}
            value={replay?.prompt ?? draft}
            disabled={!!replay}
            placeholder={copy.comparePlaceholder}
            onChange={(event) => setDraft(event.target.value)}
          />
          <div className="composer-footer">
            <span>{selected.length} / 4</span>
            <button
              type="submit"
              disabled={
                busy ||
                uploading ||
                selected.length < 2 ||
                !available ||
                incompatible ||
                (!replay && !draft.trim())
              }
            >
              {busy ? copy.sending : copy.runComparison}
            </button>
          </div>
        </section>
        <p className="privacy">{copy.retryNotice}</p>
      </form>
    </section>
  );
}
