import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  chatApi,
  type CatalogInfo,
  type ConversationInfo,
  type RunInfo,
  type RunStart,
  type SessionInfo,
  type UsageInfo,
} from "../../lib/api";
import { copy } from "../../lib/copy";
import Markdown from "./Markdown";

const terminal = (run: RunInfo) =>
  ["succeeded", "failed", "cancelled", "interrupted"].includes(run.status);
const price = (value: string) =>
  (Number(value) * 1_000_000).toLocaleString(undefined, {
    maximumFractionDigits: 6,
  });
const usd = (micro: number) => `$${(micro / 1_000_000).toFixed(6)}`;

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
  const [systemPrompt, setSystemPrompt] = useState("");
  const [maximum, setMaximum] = useState(2048);
  const [temperature, setTemperature] = useState("");
  const [usage, setUsage] = useState<UsageInfo | null>(null);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const focused = useRef<string | null>(null);
  const submitting = useRef(false);
  const pending = useRef<{ fingerprint: string; body: RunStart } | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const active = answers.find((run) => !terminal(run));
  const selected = catalog?.models.find((model) => model.id === modelId);

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
  async function refreshUsage() {
    setUsage(await chatApi.usage());
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
        setUsage(spend);
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
          void refreshUsage().catch(failed);
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
          update(run);
          if (terminal(run)) {
            source.close();
            void refreshUsage().catch(failed);
          }
        })
        .catch(failed);
    };
    return () => {
      mounted = false;
      source.close();
    };
  }, [active?.id]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [answers.at(-1)?.output]);

  async function open(item: ConversationInfo) {
    setError("");
    try {
      const saved = await chatApi.conversation(item.id);
      focused.current = saved.id;
      setConversation(saved);
      setAnswers(saved.runs);
      setNavigationOpen(false);
      const last = saved.runs.at(-1);
      if (last && typeof last.settings.system_prompt === "string")
        setSystemPrompt(last.settings.system_prompt);
    } catch (error) {
      failed(error);
    }
  }

  async function submit(
    event?: FormEvent,
    retryOf?: RunInfo,
    editedPrompt?: string,
  ) {
    event?.preventDefault();
    if (
      submitting.current ||
      active ||
      !selected ||
      (!retryOf && !draft.trim())
    )
      return;
    submitting.current = true;
    setBusy(true);
    setError("");
    setWarning("");
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
        system_prompt: systemPrompt,
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
      update(run);
      pending.current = null;
      if (!retryOf) setDraft("");
      setHistory(await chatApi.history(search));
      await refreshUsage();
    } catch (error) {
      failed(error);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  async function stop() {
    if (!active) return;
    try {
      update(await chatApi.cancel(active.id));
      setWarning(copy.stopNotice);
      await refreshUsage();
    } catch (error) {
      failed(error);
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
          onClick={() => {
            focused.current = null;
            setConversation(null);
            setAnswers([]);
            setNavigationOpen(false);
          }}
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
            <p>
              {copy.daily}: {usd(usage.daily_actual_microusd)}
            </p>
            <p>
              {copy.outstanding}: {usd(usage.outstanding_microusd)}
            </p>
            <p>
              {copy.uncertain}: {usage.uncertain_count}
            </p>
          </section>
        )}
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
            {ownerSession.environment === "production"
              ? copy.production
              : copy.development}
          </span>
          <span className="version">{copy.version}</span>
          <button className="sign-out" onClick={signOut}>
            {copy.signOut}
          </button>
        </header>
        <div className="model-bar">
          <span className="mode-label">{copy.chat}</span>
          <label className="sr-only" htmlFor="model">
            {copy.model}
          </label>
          <select
            id="model"
            value={modelId}
            onChange={(event) => setModelId(event.target.value)}
          >
            {catalog?.models.map((model) => (
              <option key={model.id} value={model.id}>
                {favorites.includes(model.id) ? `${copy.favorites}: ` : ""}
                {model.name}
              </option>
            ))}
          </select>
        </div>
        <div className="chat-scroll">
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
              <div className="user-message">{run.prompt}</div>
              <article className="answer">
                <div className="answer-heading">
                  <strong>{run.model_name}</strong>
                  <span>{run.provider ?? copy.providerUnknown}</span>
                  <span role="status">
                    {copy.status[run.status as keyof typeof copy.status] ??
                      run.status}
                  </span>
                </div>
                {typeof run.settings.retry_of === "string" && (
                  <p className="eyebrow">{copy.savedInput}</p>
                )}
                <Markdown text={run.output} />
                {Array.isArray(run.usage?.providers_seen) &&
                  run.usage.providers_seen.length > 1 && (
                    <p className="notice">
                      {copy.routingChanged}{" "}
                      {run.usage.providers_seen.join(", ")}
                    </p>
                  )}
                <div className="answer-meta">
                  <span>
                    {run.actual_microusd === null
                      ? copy.unknownCost
                      : `${copy.actualCost}: ${usd(run.actual_microusd)}`}
                  </span>
                  <span>
                    {copy.reservation}: {usd(run.reserved_microusd)}
                  </span>
                  <span>
                    {copy.maxTokens}: {String(run.settings.max_tokens ?? "")}
                  </span>
                  {run.settings.temperature !== null &&
                    run.settings.temperature !== undefined && (
                      <span>
                        {copy.temperature}: {String(run.settings.temperature)}
                      </span>
                    )}
                  {run.first_token_ms !== null &&
                    run.first_token_ms !== undefined && (
                      <span>
                        {copy.firstToken}:{" "}
                        {(run.first_token_ms / 1000).toFixed(2)} s
                      </span>
                    )}
                  {run.elapsed_ms !== null && (
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
                    {copy.chatFailure} ({run.error_code})
                  </p>
                )}
                <div className="answer-actions">
                  <button
                    className="plain-button"
                    onClick={() => {
                      void navigator.clipboard
                        .writeText(run.output)
                        .catch(failed);
                    }}
                  >
                    {copy.copyResponse}
                  </button>
                  <button
                    className="plain-button"
                    disabled={busy || !!active}
                    onClick={() => void submit(undefined, run)}
                  >
                    {copy.repeat}
                  </button>
                  <button
                    className="plain-button"
                    disabled={busy || !!active}
                    onClick={() => {
                      const edited = window.prompt(copy.editPrompt, run.prompt);
                      if (edited?.trim()) void submit(undefined, run, edited);
                    }}
                  >
                    {copy.edit}
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
                </div>
              </article>
            </section>
          ))}
          <div ref={endRef} />
        </div>
        <div className="chat-composer">
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
          <details>
            <summary>{copy.advanced}</summary>
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
                  void chatApi.refreshCatalog().then(setCatalog).catch(failed);
                }}
              >
                {copy.refreshModels}
              </button>
            </div>
            <div className="advanced-grid">
              <label>
                {copy.systemPrompt}
                <textarea
                  value={systemPrompt}
                  maxLength={12000}
                  rows={2}
                  onChange={(event) => setSystemPrompt(event.target.value)}
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
                    onChange={(event) => setMaximum(Number(event.target.value))}
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
                    onChange={(event) => setTemperature(event.target.value)}
                  />
                </label>
              )}
            </div>
          </details>
          <section className="preview-panel">
            <div className="notice">
              {ownerSession.provider_mode === "mock"
                ? copy.mockNotice
                : copy.privacy}
            </div>
            <form onSubmit={(event) => void submit(event)}>
              <label className="sr-only" htmlFor="message">
                {copy.message}
              </label>
              <textarea
                id="message"
                rows={2}
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
              <div className="composer-footer">
                <span>
                  {selected
                    ? `${copy.context}: ${selected.context_length.toLocaleString()}`
                    : copy.loading}
                </span>
                {active ? (
                  <button type="button" onClick={() => void stop()}>
                    {copy.stop}
                  </button>
                ) : (
                  <button
                    type="submit"
                    disabled={busy || !draft.trim() || !selected}
                  >
                    {busy ? copy.sending : copy.send}
                  </button>
                )}
              </div>
            </form>
          </section>
          {selected && (
            <p className="model-detail">
              {price(selected.pricing.prompt)} /{" "}
              {price(selected.pricing.completion)} {copy.priceUnit}
            </p>
          )}
          <p className="privacy">
            {copy.retryNotice}
            {catalog &&
              ` · ${catalog.ranking} · ${copy.refreshed}: ${new Date(catalog.fetched_at * 1000).toLocaleString()}`}
          </p>
        </div>
      </main>
    </div>
  );
}
