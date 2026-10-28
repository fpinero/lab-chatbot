import {
  lazy,
  Suspense,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  ApiError,
  chatApi,
  type AttachmentInfo,
  type CatalogInfo,
  type ConversationInfo,
  type RunInfo,
  type RunStart,
  type SessionInfo,
  type UsageInfo,
} from "../../lib/api";
import { copy } from "../../lib/copy";
import { useMobile } from "../../lib/useMobile";
import RunCard from "./RunCard";
import SavedPrompt from "./SavedPrompt";
import ModelPicker from "./ModelPicker";
import AttachmentPicker, {
  AttachmentPreview,
} from "../attachments/AttachmentPicker";
import ComparisonPanel from "../compare/ComparisonPanel";

const ImagePanel = lazy(() => import("../images/ImagePanel"));

const terminal = (run: RunInfo) =>
  ["succeeded", "failed", "cancelled", "interrupted"].includes(run.status);
const price = (value: string) =>
  (Number(value) * 1_000_000).toLocaleString(undefined, {
    maximumFractionDigits: 6,
  });
const usd = (micro: number) => `$${(micro / 1_000_000).toFixed(6)}`;
const collapsePreferenceKey = "lab-chatbot.mobile-collapse";
function savedCollapsePreference() {
  try {
    return localStorage.getItem(collapsePreferenceKey) === "true";
  } catch {
    return false;
  }
}

export default function Workspace({
  ownerSession,
  signOut,
  expired,
  notice,
}: {
  ownerSession: SessionInfo;
  signOut: () => void;
  expired: () => void;
  notice: string;
}) {
  const [mode, setMode] = useState<"chat" | "compare" | "images">("chat");
  const [imagesVisited, setImagesVisited] = useState(false);
  const [draftVersion, setDraftVersion] = useState(0);
  const [files, setFiles] = useState<AttachmentInfo[]>([]);
  const [uploading, setUploading] = useState(false);
  const [compareReplay, setCompareReplay] = useState<RunInfo | null>(null);
  const [catalog, setCatalog] = useState<CatalogInfo | null>(null);
  const [history, setHistory] = useState<ConversationInfo[]>([]);
  const [conversation, setConversation] = useState<ConversationInfo | null>(
    null,
  );
  const [answers, setAnswers] = useState<RunInfo[]>([]);
  const [modelId, setModelId] = useState("");
  const [favorites, setFavorites] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState<{
    run: RunInfo;
    draft: string;
    files: AttachmentInfo[];
  } | null>(null);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [maximum, setMaximum] = useState(2048);
  const [temperature, setTemperature] = useState("");
  const [usage, setUsage] = useState<UsageInfo | null>(null);
  const [refreshingBalance, setRefreshingBalance] = useState(false);
  const [balanceFeedback, setBalanceFeedback] = useState<
    "updated" | "failed" | null
  >(null);
  const balanceRefreshPending = useRef(false);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const mobile = useMobile();
  const [collapseAfterSend, setCollapseAfterSend] = useState(
    savedCollapsePreference,
  );
  const [collapsed, setCollapsed] = useState(false);
  const folded = mobile && collapsed;
  const draftNow = useRef(draft);
  draftNow.current = draft;
  const writeRef = useRef<HTMLButtonElement>(null);
  const focusOnExpand = useRef(false);
  const focused = useRef<string | null>(null);
  const conversationEpoch = useRef(0);
  const submitting = useRef(false);
  const pending = useRef<{ fingerprint: string; body: RunStart } | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const followOutput = useRef(true);
  const messageRef = useRef<HTMLTextAreaElement>(null);
  const active = answers.find((run) => !terminal(run));
  const incompatible =
    (editing?.run.attachments ?? files).some((item) => item.kind === "image") &&
    !!catalog?.models.find(
      (model) =>
        model.id === modelId && !model.input_modalities.includes("image"),
    );
  const selected = catalog?.models.find((model) => model.id === modelId);

  useEffect(() => {
    if (folded) writeRef.current?.focus({ preventScroll: true });
    else if (focusOnExpand.current) {
      focusOnExpand.current = false;
      messageRef.current?.focus({ preventScroll: true });
    }
  }, [folded, draftVersion]);
  function expandComposer() {
    focusOnExpand.current = true;
    setCollapsed(false);
    if (!folded) messageRef.current?.focus({ preventScroll: true });
  }
  function hideComposer() {
    messageRef.current?.blur();
    setCollapsed(true);
  }
  function cancelEdit() {
    if (!editing) return;
    setDraft(editing.draft);
    setFiles(editing.files);
    setEditing(null);
  }

  function newConversation() {
    if (submitting.current || uploading) return;
    focused.current = null;
    conversationEpoch.current += 1;
    pending.current = null;
    setConversation(null);
    setAnswers([]);
    setCompareReplay(null);
    setEditing(null);
    setDraft("");
    setFiles([]);
    setSystemPrompt("");
    setMaximum(2048);
    setTemperature("");
    setError("");
    setWarning("");
    setMode("chat");
    setNavigationOpen(false);
    setDraftVersion(conversationEpoch.current);
    followOutput.current = true;
    expandComposer();
  }

  function failed(error: unknown) {
    if (error instanceof ApiError && error.status === 401) expired();
    else setError(error instanceof ApiError ? error.message : copy.chatFailure);
  }
  function update(run: RunInfo) {
    if (focused.current !== run.conversation_id) return;
    setAnswers((previous) =>
      previous.some((item) => item.id === run.id)
        ? previous.map((item) => (item.id === run.id ? run : item))
        : [...previous, run],
    );
  }
  function applyUsage(next: UsageInfo) {
    setUsage((previous) =>
      previous?.provider_key_budget &&
      next.provider_key_budget &&
      previous.provider_key_budget.checked_at >
        next.provider_key_budget.checked_at
        ? { ...next, provider_key_budget: previous.provider_key_budget }
        : next,
    );
  }
  async function refreshUsage() {
    applyUsage(await chatApi.usage());
  }
  async function refreshBalance() {
    if (balanceRefreshPending.current) return;
    balanceRefreshPending.current = true;
    setRefreshingBalance(true);
    setBalanceFeedback(null);
    try {
      applyUsage(await chatApi.usage(true));
      setBalanceFeedback("updated");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) expired();
      else setBalanceFeedback("failed");
    } finally {
      balanceRefreshPending.current = false;
      setRefreshingBalance(false);
    }
  }

  useEffect(() => {
    let mounted = true;
    void Promise.all([
      chatApi.catalog(),
      chatApi.history(),
      chatApi.favorites(),
      chatApi.usage(),
    ])
      .then(([models, conversations, preferences, spend]) => {
        if (!mounted) return;
        setCatalog(models);
        setModelId(models.models[0]?.id ?? "");
        setHistory(conversations);
        setFavorites(preferences.favorites);
        applyUsage(spend);
      })
      .catch((error) => {
        if (mounted) failed(error);
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      void chatApi.history(search).then(setHistory).catch(failed);
    }, 250);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    if (!active) return;
    let mounted = true;
    const source = new EventSource(`/api/runs/${active.id}/events`);
    const receive = (event: MessageEvent<string>) => {
      if (!mounted) return;
      try {
        const value = JSON.parse(event.data) as { run: RunInfo };
        update(value.run);
        if (terminal(value.run)) {
          source.close();
          void refreshUsage().catch((error) => {
            if (mounted) failed(error);
          });
        }
      } catch {
        setError(copy.chatFailure);
      }
    };
    for (const kind of [
      "run.snapshot",
      "run.started",
      "text.delta",
      "usage.updated",
      "run.completed",
      "run.failed",
      "run.cancelled",
    ])
      source.addEventListener(kind, receive as EventListener);
    source.addEventListener("session.expired", () => {
      source.close();
      expired();
    });
    source.onerror = () => {
      void chatApi
        .run(active.id)
        .then((run) => {
          if (!mounted) return;
          update(run);
          if (terminal(run)) {
            source.close();
            void refreshUsage().catch((error) => {
              if (mounted) failed(error);
            });
          }
        })
        .catch((error) => {
          if (mounted) failed(error);
        });
    };
    return () => {
      mounted = false;
      source.close();
    };
  }, [active?.id]);

  useEffect(() => {
    if (followOutput.current)
      endRef.current?.scrollIntoView({ block: "nearest" });
  }, [answers.at(-1)?.output, folded]);

  useLayoutEffect(() => {
    const resize = () => {
      const input = messageRef.current;
      if (!input) return;
      input.style.height = "auto";
      input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [draft, mode, folded]);

  async function open(item: ConversationInfo) {
    const epoch = conversationEpoch.current;
    setError("");
    try {
      const saved = await chatApi.conversation(item.id);
      if (epoch !== conversationEpoch.current) return;
      cancelEdit();
      focused.current = saved.id;
      setConversation(saved);
      followOutput.current = true;
      setAnswers(saved.runs.filter((run) => !run.comparison_id));
      setCompareReplay(null);
      setNavigationOpen(false);
      if (mobile && collapseAfterSend && !draft.trim() && !files.length)
        hideComposer();
      const last = saved.runs.at(-1);
      if (last && typeof last.settings.system_prompt === "string")
        setSystemPrompt(last.settings.system_prompt);
    } catch (error) {
      if (epoch === conversationEpoch.current) failed(error);
    }
  }

  async function submit(
    event?: FormEvent,
    retryOf?: RunInfo,
    editedPrompt?: string,
  ) {
    event?.preventDefault();
    const editSubmission = !retryOf ? editing : null;
    if (editSubmission) {
      retryOf = editSubmission.run;
      editedPrompt = draft;
    }
    if (
      submitting.current ||
      uploading ||
      incompatible ||
      active ||
      !selected ||
      ((!retryOf || editSubmission) && !draft.trim())
    )
      return;
    submitting.current = true;
    setBusy(true);
    setError("");
    setWarning("");
    let accepted = false;
    try {
      const item =
        conversation ??
        (await chatApi.create(
          (draft || retryOf?.prompt || copy.newConversation).slice(0, 80),
        ));
      focused.current = item.id;
      setConversation(item);
      const body: RunStart = {
        verification_run: false,
        conversation_id: item.id,
        model_id: modelId,
        idempotency_key: crypto.randomUUID().replaceAll("-", ""),
        prompt: retryOf ? (editedPrompt ?? "") : draft.trim(),
        system_prompt:
          retryOf && typeof retryOf.settings.system_prompt === "string"
            ? retryOf.settings.system_prompt
            : systemPrompt,
        attachment_ids: retryOf ? [] : files.map((item) => item.id),
        max_tokens: maximum,
        ...(selected.supported_parameters.includes("temperature") &&
        temperature !== ""
          ? { temperature: Number(temperature) }
          : {}),
        ...(retryOf ? { retry_of: retryOf.id } : {}),
      };
      const fingerprint = JSON.stringify({ ...body, idempotency_key: "" });
      if (pending.current?.fingerprint === fingerprint)
        body.idempotency_key = pending.current.body.idempotency_key;
      pending.current = { fingerprint, body };
      const run = await chatApi.submit(body);
      accepted = true;
      followOutput.current = true;
      update(run);
      pending.current = null;
      if (
        (!retryOf || editSubmission) &&
        mobile &&
        collapseAfterSend &&
        draftNow.current === draft
      )
        hideComposer();
      if (editSubmission) {
        setEditing(null);
        setDraft((previous) =>
          previous === draft ? editSubmission.draft : previous,
        );
        setFiles(editSubmission.files);
      } else if (!retryOf) {
        setDraft((previous) => (previous === draft ? "" : previous));
        setFiles((previous) =>
          previous.filter((item) => !body.attachment_ids?.includes(item.id)),
        );
      }
      setHistory(await chatApi.history(search));
      await refreshUsage();
    } catch (error) {
      if (!accepted) setCollapsed(false);
      failed(error);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  async function stop() {
    if (!active) return;
    const epoch = conversationEpoch.current;
    try {
      const saved = await chatApi.cancel(active.id);
      if (epoch !== conversationEpoch.current) return;
      update(saved);
      setWarning(copy.stopNotice);
      await refreshUsage();
    } catch (error) {
      if (epoch === conversationEpoch.current) failed(error);
    }
  }
  async function rename() {
    if (!conversation) return;
    const title = window.prompt(copy.rename, conversation.title)?.trim();
    if (!title) return;
    try {
      setConversation(await chatApi.rename(conversation.id, title));
      setHistory(await chatApi.history(search));
    } catch (error) {
      failed(error);
    }
  }
  async function remove() {
    if (!conversation || !window.confirm(copy.deleteConfirmation)) return;
    try {
      await chatApi.remove(conversation.id);
      cancelEdit();
      focused.current = null;
      setConversation(null);
      setAnswers([]);
      setHistory(await chatApi.history(search));
      await refreshUsage();
    } catch (error) {
      failed(error);
    }
  }
  async function favorite() {
    const next = favorites.includes(modelId)
      ? favorites.filter((id) => id !== modelId)
      : [...favorites, modelId];
    try {
      setFavorites((await chatApi.saveFavorites(next)).favorites);
    } catch (error) {
      failed(error);
    }
  }

  return (
    <div className="workspace chat-workspace">
      <aside
        className={`sidebar ${navigationOpen ? "is-open" : ""}`}
        aria-label={copy.navigation}
      >
        <button
          className="mobile-close"
          onClick={() => setNavigationOpen(false)}
        >
          {copy.closeNavigation}
        </button>
        <a className="brand" href="/">
          <span className="brand-mark" aria-hidden="true">
            L
          </span>
          <span>
            <strong>{copy.appName}</strong>
            <small>{copy.subtitle}</small>
          </span>
        </a>
        <button
          className="new-conversation"
          disabled={busy || uploading}
          onClick={newConversation}
        >
          {copy.newConversation}
        </button>
        <label className="sr-only" htmlFor="search">
          {copy.search}
        </label>
        <input
          id="search"
          className="history-search"
          placeholder={copy.search}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <nav className="history-list" aria-label={copy.search}>
          {history.length === 0 && <p>{copy.historyEmpty}</p>}
          {history.map((item) => (
            <button
              key={item.id}
              aria-current={conversation?.id === item.id ? "page" : undefined}
              onClick={() => void open(item)}
            >
              {item.title}
            </button>
          ))}
        </nav>
        {usage && (
          <section className="usage-summary" aria-label={copy.usage}>
            <span className="eyebrow">
              {usage.simulated ? copy.simulated : copy.usage}
            </span>
            {usage.spend_control === "provider" && !usage.simulated && (
              <>
                <p>{copy.providerSpending}</p>
                {usage.provider_key_budget ? (
                  <>
                    <p>
                      {copy.providerKeyLimit}: $
                      {Number(usage.provider_key_budget.limit_usd).toFixed(2)}
                    </p>
                    <p>
                      {copy.providerKeyRemaining}: $
                      {Number(usage.provider_key_budget.remaining_usd).toFixed(
                        6,
                      )}
                    </p>
                    <small>
                      {copy.budgetChecked}:{" "}
                      {new Date(
                        usage.provider_key_budget.checked_at * 1000,
                      ).toLocaleTimeString()}
                    </small>
                  </>
                ) : (
                  <p>{copy.providerBudgetUnavailable}</p>
                )}
                <button
                  type="button"
                  className="balance-refresh"
                  disabled={refreshingBalance}
                  aria-busy={refreshingBalance}
                  aria-label={copy.refreshUsage}
                  onClick={() => void refreshBalance()}
                >
                  {refreshingBalance
                    ? copy.refreshingBalance
                    : copy.refreshUsage}
                </button>
                {balanceFeedback && (
                  <p
                    className={
                      balanceFeedback === "failed"
                        ? "balance-error"
                        : "balance-feedback"
                    }
                    role={balanceFeedback === "failed" ? "alert" : "status"}
                  >
                    {balanceFeedback === "failed"
                      ? copy.balanceRefreshFailed
                      : copy.balanceUpdated}
                  </p>
                )}
              </>
            )}
            <p>
              {copy.daily}: {usd(usage.daily_actual_microusd)}
            </p>
            {usage.spend_control !== "provider" && (
              <p>
                {copy.outstanding}: {usd(usage.outstanding_microusd)}
              </p>
            )}
            <p>
              {copy.uncertain}: {usage.uncertain_count}
            </p>
            {usage.spend_control === "provider" &&
              usage.uncertain_count > 0 && (
                <p>{copy.providerPendingAccounting}</p>
              )}
          </section>
        )}
        <section className="sidebar-privacy" aria-label={copy.privacyHeading}>
          <span className="eyebrow">{copy.privacyHeading}</span>
          <p>
            {ownerSession.provider_mode === "mock"
              ? copy.mockNotice
              : copy.privacy}
          </p>
        </section>
      </aside>
      <main>
        <header>
          <button
            className="mobile-brand navigation-toggle"
            aria-label={copy.openNavigation}
            aria-expanded={navigationOpen}
            onClick={() => setNavigationOpen(!navigationOpen)}
          >
            {copy.appName}
          </button>
          <span className="badge">
            {ownerSession.provider_mode === "mock"
              ? copy.simulated
              : ownerSession.environment === "production"
                ? copy.production
                : copy.development}
          </span>
          <span className="version">{copy.version}</span>
          <button className="sign-out" onClick={signOut}>
            {copy.signOut}
          </button>
        </header>
        <div className="model-bar">
          <label className="sr-only" htmlFor="mode">
            {copy.mode}
          </label>
          <select
            className="mode-select"
            id="mode"
            value={mode}
            onChange={(event) => {
              const selectedMode = event.target.value as
                "chat" | "compare" | "images";
              setMode(selectedMode);
              if (selectedMode === "images") setImagesVisited(true);
            }}
          >
            <option value="chat">{copy.chat}</option>
            <option value="compare">{copy.compare}</option>
            <option value="images">{copy.images}</option>
          </select>
          <div hidden={mode !== "chat"} className="chat-model-picker">
            <ModelPicker
              models={catalog?.models ?? []}
              value={modelId}
              onChange={setModelId}
              favorites={favorites}
            />
          </div>
        </div>
        <div
          hidden={mode !== "chat"}
          className="chat-scroll"
          role="region"
          aria-label="Conversation"
          onScroll={(event) => {
            const area = event.currentTarget;
            followOutput.current =
              area.scrollHeight - area.scrollTop - area.clientHeight < 80;
          }}
        >
          {answers.length === 0 && (
            <section className="intro chat-intro">
              <span className="eyebrow">{copy.subtitle}</span>
              <h1>{copy.title}</h1>
              <p>{copy.description}</p>
            </section>
          )}
          {conversation && (
            <div className="conversation-actions">
              <strong>{conversation.title}</strong>
              <button className="plain-button" onClick={() => void rename()}>
                {copy.rename}
              </button>
              <button
                className="plain-button"
                disabled={!!active}
                onClick={() => void remove()}
              >
                {copy.delete}
              </button>
              <a
                href={`/api/conversations/${conversation.id}/export?format=markdown`}
              >
                {copy.exportMarkdown}
              </a>
              <a
                href={`/api/conversations/${conversation.id}/export?format=json`}
              >
                {copy.exportJson}
              </a>
            </div>
          )}
          {answers.map((run) => (
            <section
              className="turn"
              key={run.id}
              aria-label={`${run.model_name} ${run.turn}`}
            >
              <SavedPrompt text={run.prompt} />
              <RunCard
                run={run}
                actions={
                  <>
                    <button
                      className="plain-button"
                      disabled={busy || !!active || !!editing}
                      onClick={() => void submit(undefined, run)}
                    >
                      {copy.repeat}
                    </button>
                    <button
                      className="plain-button"
                      disabled={busy || !!active || !!editing}
                      onClick={() => {
                        setEditing((previous) => ({
                          run,
                          draft: previous?.draft ?? draft,
                          files: previous?.files ?? files,
                        }));
                        setDraft(run.prompt);
                        setFiles([]);
                        expandComposer();
                      }}
                    >
                      {copy.edit}
                    </button>
                    <button
                      className="plain-button"
                      disabled={busy || !!active || !!editing}
                      onClick={() => {
                        setCompareReplay(run);
                        setMode("compare");
                      }}
                    >
                      {copy.compareSaved}
                    </button>
                    {run.accounting_state === "uncertain" && (
                      <button
                        className="plain-button"
                        onClick={() => {
                          void chatApi
                            .reconcile(run.id)
                            .then(update)
                            .then(refreshUsage)
                            .catch(failed);
                        }}
                      >
                        {copy.reconcile}
                      </button>
                    )}
                  </>
                }
              />
            </section>
          ))}
          <div ref={endRef} />
        </div>
        <div hidden={mode !== "chat"} className="chat-composer">
          {(error || notice) && (
            <p role="alert" className="error">
              {error || notice}
            </p>
          )}
          {warning && (
            <p role="status" className="notice">
              {warning}
            </p>
          )}
          {catalog?.stale && <p className="notice">{copy.stale}</p>}
          {incompatible && (
            <p role="alert" className="error">
              {copy.incompatibleFiles}
            </p>
          )}
          {folded && (
            <div className="collapsed-composer">
              <button
                type="button"
                ref={writeRef}
                aria-expanded={false}
                aria-controls="composer-editor"
                onClick={expandComposer}
              >
                {uploading
                  ? copy.uploading
                  : draft.trim()
                    ? copy.resumeDraft
                    : copy.writeMessage}
              </button>
              {active && (
                <button
                  type="button"
                  aria-label={copy.stop}
                  onClick={() => void stop()}
                >
                  {copy.stopShort}
                </button>
              )}
            </div>
          )}
          <section
            id="composer-editor"
            hidden={folded}
            className="preview-panel compact-preview"
          >
            {editing && (
              <div className="editing-notice">
                <span>{copy.editPrompt}</span>
                <button
                  type="button"
                  className="plain-button"
                  disabled={busy}
                  onClick={cancelEdit}
                >
                  {copy.cancelEdit}
                </button>
              </div>
            )}
            <AttachmentPicker
              key={draftVersion}
              compact
              items={files}
              onChange={setFiles}
              label={copy.attachChat}
              pasteTarget={messageRef}
              disabled={busy || !!editing}
              onFailure={failed}
              onBusyChange={setUploading}
              options={
                <>
                  {mobile && (
                    <label className="collapse-preference">
                      <input
                        type="checkbox"
                        checked={collapseAfterSend}
                        onChange={(event) => {
                          setCollapseAfterSend(event.target.checked);
                          try {
                            localStorage.setItem(
                              collapsePreferenceKey,
                              String(event.target.checked),
                            );
                          } catch {
                            /* Preference storage is optional. */
                          }
                        }}
                      />
                      {copy.collapseAfterSend}
                    </label>
                  )}
                  {editing && (
                    <AttachmentPreview items={editing.run.attachments ?? []} />
                  )}
                  <div className="model-preferences">
                    {" "}
                    <button
                      className="plain-button"
                      aria-pressed={favorites.includes(modelId)}
                      onClick={() => void favorite()}
                      disabled={!selected}
                    >
                      {copy.favorite}
                    </button>
                    <button
                      className="plain-button"
                      onClick={() => {
                        void chatApi
                          .refreshCatalog()
                          .then(setCatalog)
                          .catch(failed);
                      }}
                    >
                      {copy.refreshModels}
                    </button>
                  </div>
                  <div className="advanced-grid">
                    <label>
                      {copy.systemPrompt}
                      <textarea
                        value={
                          editing &&
                          typeof editing.run.settings.system_prompt === "string"
                            ? editing.run.settings.system_prompt
                            : systemPrompt
                        }
                        disabled={!!editing}
                        maxLength={12000}
                        rows={2}
                        onChange={(event) =>
                          setSystemPrompt(event.target.value)
                        }
                      />
                    </label>
                    {selected?.supported_parameters.includes("max_tokens") && (
                      <label>
                        {copy.maxTokens}
                        <input
                          type="number"
                          min={1}
                          max={2048}
                          value={maximum}
                          onChange={(event) =>
                            setMaximum(Number(event.target.value))
                          }
                        />
                      </label>
                    )}
                    {selected?.supported_parameters.includes("temperature") && (
                      <label>
                        {copy.temperature}
                        <input
                          type="number"
                          min={0}
                          max={2}
                          step={0.1}
                          value={temperature}
                          onChange={(event) =>
                            setTemperature(event.target.value)
                          }
                        />
                      </label>
                    )}
                  </div>
                  <p>
                    {selected
                      ? `${copy.context}: ${selected.context_length.toLocaleString()}`
                      : copy.loading}
                  </p>
                  {selected && (
                    <p>
                      {price(selected.pricing.prompt)} /{" "}
                      {price(selected.pricing.completion)} {copy.priceUnit}
                    </p>
                  )}
                  <p>{copy.retryNotice}</p>
                  {catalog && (
                    <p>
                      {catalog.ranking} · {copy.refreshed}:{" "}
                      {new Date(catalog.fetched_at * 1000).toLocaleString()}
                    </p>
                  )}
                </>
              }
              actions={
                <>
                  {mobile && (
                    <button
                      type="button"
                      className="plain-button collapse-toggle"
                      disabled={uploading}
                      aria-label={copy.collapseComposer}
                      aria-controls="composer-editor"
                      aria-expanded={true}
                      onClick={hideComposer}
                    >
                      ⌄
                    </button>
                  )}
                  {active ? (
                    <button
                      type="button"
                      aria-label={copy.stop}
                      onClick={() => void stop()}
                    >
                      {copy.stopShort}
                    </button>
                  ) : (
                    <button
                      form="chat-message-form"
                      type="submit"
                      aria-label={copy.send}
                      disabled={
                        busy ||
                        uploading ||
                        incompatible ||
                        !draft.trim() ||
                        !selected
                      }
                    >
                      {busy ? copy.sending : copy.sendShort}
                    </button>
                  )}
                </>
              }
            >
              <form
                id="chat-message-form"
                onSubmit={(event) => void submit(event)}
              >
                <label className="sr-only" htmlFor="message">
                  {copy.message}
                </label>
                <textarea
                  id="message"
                  rows={1}
                  ref={messageRef}
                  maxLength={24000}
                  placeholder={copy.messagePlaceholder}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (
                      event.key === "Enter" &&
                      !event.shiftKey &&
                      !event.nativeEvent.isComposing
                    ) {
                      event.preventDefault();
                      void submit();
                    }
                  }}
                />
              </form>
            </AttachmentPicker>
          </section>
        </div>
        {catalog && (
          <ComparisonPanel
            key={`comparison-${draftVersion}`}
            hidden={mode !== "compare"}
            catalog={catalog}
            conversation={conversation}
            replay={compareReplay}
            clearReplay={() => setCompareReplay(null)}
            onConversation={(saved) => {
              if (draftVersion !== conversationEpoch.current) return;
              if (saved.id !== conversation?.id) cancelEdit();
              setConversation(saved);
            }}
            expired={expired}
            onUsageChange={() => {
              if (draftVersion !== conversationEpoch.current) return;
              void refreshUsage().catch(failed);
            }}
            onContinue={(saved) => {
              if (draftVersion !== conversationEpoch.current) return;
              cancelEdit();
              focused.current = saved.id;
              setConversation(saved);
              setAnswers(saved.runs.filter((run) => !run.comparison_id));
              setMode("chat");
              setCompareReplay(null);
              const last = saved.runs.at(-1);
              if (
                last &&
                catalog.models.some((model) => model.id === last.model_id)
              )
                setModelId(last.model_id);
              void chatApi.history(search).then(setHistory).catch(failed);
            }}
          />
        )}
        {imagesVisited && (
          <Suspense fallback={<p>{copy.loading}</p>}>
            <ImagePanel
              key={`images-${draftVersion}`}
              hidden={mode !== "images"}
              expired={expired}
              onUsageChange={() => {
                if (draftVersion !== conversationEpoch.current) return;
                void refreshUsage().catch(failed);
              }}
            />
          </Suspense>
        )}
      </main>
    </div>
  );
}
