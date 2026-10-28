import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  imageApi,
  type AttachmentInfo,
  type ImageCatalogInfo,
  type ImageEndpointInfo,
  type ImageInput,
  type ImageQuote,
  type ImageStart,
  type MediaJobInfo,
} from "../../lib/api";
import { copy } from "../../lib/copy";
import AttachmentPicker, {
  AttachmentPreview,
} from "../attachments/AttachmentPicker";
import SavedPrompt from "../chat/SavedPrompt";

const active = (job: MediaJobInfo) =>
  ["queued", "submitting", "running", "cancel_requested"].includes(job.status);
const usd = (value: number) => `$${(value / 1000000).toFixed(6)}`;
const keys = [
  "resolution",
  "aspect_ratio",
  "quality",
  "output_format",
] as const;
const labels = {
  resolution: copy.imageResolution,
  aspect_ratio: copy.imageRatio,
  quality: copy.imageQuality,
  output_format: copy.imageFormat,
};
const preferred = {
  resolution: ["512", "768", "1K", "1.5K", "2K", "4K"],
  aspect_ratio: ["1:1"],
  quality: ["low", "medium", "auto", "high"],
  output_format: ["png", "webp", "jpeg"],
};

export default function ImagePanel({
  hidden,
  expired,
  onUsageChange,
}: {
  hidden: boolean;
  expired: () => void;
  onUsageChange: () => void;
}) {
  const [catalog, setCatalog] = useState<ImageCatalogInfo | null>(null);
  const [modelId, setModelId] = useState("");
  const [details, setDetails] = useState<ImageEndpointInfo | null>(null);
  const [provider, setProvider] = useState("");
  const [options, setOptions] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState("");
  const [count, setCount] = useState(1);
  const [files, setFiles] = useState<AttachmentInfo[]>([]);
  const [jobs, setJobs] = useState<MediaJobInfo[]>([]);
  const [quoted, setQuoted] = useState<{
    fingerprint: string;
    value: ImageQuote;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [retryOf, setRetryOf] = useState<MediaJobInfo | null>(null);
  const pending = useRef<{ fingerprint: string; body: ImageStart } | null>(
    null,
  );
  const submitting = useRef(false);
  const resultRef = useRef<HTMLElement>(null);
  const endpoint =
    details?.model.id === modelId
      ? details.endpoints.find((item) => item.provider_tag === provider)
      : undefined;
  const supportsReferences =
    details?.model.input_modalities.includes("image") &&
    ["boolean", "range"].includes(
      endpoint?.parameters.input_references?.type ?? "",
    );
  const incompatible =
    files.some((file) => file.kind !== "image") ||
    (files.length > 0 && !supportsReferences);
  const input: ImageInput = {
    model_id: modelId,
    provider_tag: provider,
    prompt: draft.trim(),
    options,
    count,
    attachment_ids: files.map((file) => file.id),
    verification_run: false,
  };
  const fingerprint = JSON.stringify(input);
  const quote = quoted?.fingerprint === fingerprint ? quoted.value : null;

  function failed(error: unknown) {
    if (error instanceof ApiError && error.status === 401) expired();
    else
      setError(error instanceof ApiError ? error.message : copy.imageFailure);
  }
  useEffect(() => {
    let mounted = true;
    void imageApi
      .catalog()
      .then((value) => {
        if (mounted) {
          setCatalog(value);
          setModelId((previous) => previous || value.models[0]?.id || "");
        }
      })
      .catch((error) => {
        if (mounted) failed(error);
      });
    void imageApi
      .history()
      .then((value) => {
        if (mounted) setJobs(value);
      })
      .catch((error) => {
        if (mounted) failed(error);
      });
    return () => {
      mounted = false;
    };
  }, []);
  useEffect(() => {
    if (!modelId) return;
    let mounted = true;
    setDetails(null);
    void imageApi
      .capabilities(modelId)
      .then((value) => {
        if (mounted) {
          setDetails(value);
          setProvider((previous) =>
            retryOf?.model_id === value.model.id
              ? retryOf.provider_tag
              : value.endpoints.some((item) => item.provider_tag === previous)
                ? previous
                : (value.endpoints[0]?.provider_tag ?? ""),
          );
        }
      })
      .catch((error) => {
        if (mounted) failed(error);
      });
    return () => {
      mounted = false;
    };
  }, [modelId]);
  useEffect(() => {
    if (!endpoint) return;
    const defaults: Record<string, string> = {};
    for (const key of keys) {
      const values = endpoint.parameters[key]?.values ?? [];
      const allowed =
        key === "output_format"
          ? values.filter((value) => ["png", "jpeg", "webp"].includes(value))
          : values;
      if (endpoint.parameters[key]?.type === "enum" && allowed.length)
        defaults[key] =
          preferred[key].find((value) => allowed.includes(value)) ?? allowed[0];
    }
    const saved =
      retryOf?.model_id === modelId && retryOf.provider_tag === provider
        ? retryOf
        : null;
    setOptions(saved?.options ?? defaults);
    setCount(saved?.count ?? 1);
  }, [endpoint, retryOf?.id]);
  useEffect(() => {
    if (!endpoint || !input.prompt || incompatible || uploading) return;
    let mounted = true;
    const timer = setTimeout(() => {
      void imageApi
        .quote(input)
        .then((value) => {
          if (mounted) {
            setQuoted({ fingerprint, value });
            setError("");
          }
        })
        .catch((error) => {
          if (mounted) failed(error);
        });
    }, 350);
    return () => {
      mounted = false;
      clearTimeout(timer);
    };
  }, [fingerprint, endpoint, incompatible, uploading]);
  const running = jobs.some(active);
  useEffect(() => {
    if (!running) return;
    let mounted = true;
    const timer = setInterval(() => {
      void imageApi
        .history()
        .then((value) => {
          if (mounted) setJobs(value);
        })
        .catch((error) => {
          if (mounted) failed(error);
        });
    }, 1000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [running]);
  const accounting = jobs
    .map((job) => `${job.id}:${job.accounting_state}:${job.actual_microusd}`)
    .join("|");
  useEffect(() => {
    if (accounting) onUsageChange();
  }, [accounting]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (
      submitting.current ||
      uploading ||
      incompatible ||
      !quote?.ready ||
      !endpoint
    )
      return;
    if (
      retryOf?.accounting_state === "uncertain" &&
      !window.confirm(copy.imageDuplicateConfirmation)
    )
      return;
    submitting.current = true;
    setBusy(true);
    setError("");
    setWarning("");
    try {
      const body: ImageStart = {
        ...input,
        idempotency_key: crypto.randomUUID().replaceAll("-", ""),
        acknowledge_duplicate_risk: false,
        ...(retryOf
          ? {
              retry_of: retryOf.id,
              acknowledge_duplicate_risk:
                retryOf.accounting_state === "uncertain",
            }
          : {}),
      };
      const completeFingerprint = JSON.stringify({
        ...body,
        idempotency_key: "",
      });
      const request =
        pending.current?.fingerprint === completeFingerprint
          ? pending.current.body
          : body;
      pending.current = { fingerprint: completeFingerprint, body: request };
      const result = await imageApi.start(request);
      pending.current = null;
      setJobs((previous) => [
        result,
        ...previous.filter((job) => job.id !== result.id),
      ]);
      setRetryOf(null);
      onUsageChange();
      requestAnimationFrame(() =>
        resultRef.current?.scrollIntoView({ block: "start" }),
      );
    } catch (error) {
      failed(error);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  function reuse(job: MediaJobInfo) {
    setModelId(job.model_id);
    setProvider(job.provider_tag);
    setDraft(job.prompt);
    setFiles(job.attachments);
    setRetryOf(job);
    setWarning(copy.imageRetryReady);
    if (details?.model.id === job.model_id && provider === job.provider_tag) {
      setOptions(job.options);
      setCount(job.count);
    }
    document.getElementById("image-prompt")?.focus();
  }
  async function remove(job: MediaJobInfo) {
    if (!window.confirm(copy.imageDeleteConfirmation)) return;
    try {
      await imageApi.remove(job.id);
      setJobs((previous) => previous.filter((item) => item.id !== job.id));
      onUsageChange();
    } catch (error) {
      failed(error);
    }
  }

  return (
    <section
      className="image-workspace"
      hidden={hidden}
      aria-label={copy.images}
    >
      <div className="image-form">
        <div className="image-settings">
          <label>
            {copy.imageModel}
            <select
              value={modelId}
              onChange={(event) => {
                setModelId(event.target.value);
                setRetryOf(null);
              }}
            >
              {modelId &&
                !catalog?.models.some((item) => item.id === modelId) && (
                  <option value={modelId}>
                    {copy.modelUnavailable}: {modelId}
                  </option>
                )}
              {catalog?.models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            {copy.imageProvider}
            <select
              value={provider}
              onChange={(event) => {
                setProvider(event.target.value);
                setRetryOf(null);
              }}
            >
              {provider &&
                !details?.endpoints.some(
                  (item) => item.provider_tag === provider,
                ) && (
                  <option value={provider}>
                    {copy.modelUnavailable}: {provider}
                  </option>
                )}
              {details?.endpoints.map((item) => (
                <option key={item.provider_tag} value={item.provider_tag}>
                  {item.provider_name}
                </option>
              ))}
            </select>
          </label>
          {keys.map(
            (key) =>
              endpoint?.parameters[key]?.type === "enum" &&
              (endpoint.parameters[key]?.values ?? []).some(
                (value) =>
                  key !== "output_format" ||
                  ["png", "jpeg", "webp"].includes(value),
              ) && (
                <label key={key}>
                  {labels[key]}
                  <select
                    value={options[key] ?? ""}
                    onChange={(event) =>
                      setOptions({ ...options, [key]: event.target.value })
                    }
                  >
                    {(endpoint.parameters[key]?.values ?? [])
                      .filter(
                        (value) =>
                          key !== "output_format" ||
                          ["png", "jpeg", "webp"].includes(value),
                      )
                      .map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                  </select>
                </label>
              ),
          )}
          {endpoint?.parameters.n?.type === "range" && (
            <label>
              {copy.imageCount}
              <input
                type="number"
                min={endpoint.parameters.n.min ?? 1}
                max={Math.min(
                  endpoint.parameters.n.max ?? 1,
                  details?.max_images ?? 1,
                )}
                value={count}
                onChange={(event) => setCount(Number(event.target.value))}
              />
            </label>
          )}
        </div>
        <button
          className="plain-button"
          type="button"
          onClick={() => {
            void imageApi.refresh().then(setCatalog).catch(failed);
          }}
        >
          {copy.refreshModels}
        </button>
        {details && !details.endpoints.length && (
          <p role="alert">{copy.imageNoProviders}</p>
        )}
        {(catalog?.stale || details?.stale) && (
          <p role="status">{copy.stale}</p>
        )}
        <AttachmentPicker
          imageOnly
          label={copy.imageReferences}
          items={files}
          onChange={setFiles}
          onBusyChange={setUploading}
          onFailure={failed}
          disabled={busy}
        />
        {incompatible && (
          <p role="alert" className="error">
            {copy.imageReferenceUnsupported}
          </p>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {warning && <p role="status">{warning}</p>}
        <form onSubmit={(event) => void submit(event)}>
          <label htmlFor="image-prompt">{copy.imagePrompt}</label>
          <textarea
            id="image-prompt"
            rows={3}
            maxLength={12000}
            placeholder={copy.imagePlaceholder}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          <div className="image-quote" aria-live="polite">
            {draft.trim() && !quote && <p>{copy.imagePreparing}</p>}
            {quote && (
              <>
                <p>
                  {quote.uncertain
                    ? quote.spend_control === "provider"
                      ? copy.providerReservation
                      : copy.imageAllowance
                    : copy.approximate}
                  :{" "}
                  {quote.reservation_microusd === null
                    ? copy.imageUnknownEstimate
                    : usd(quote.reservation_microusd!)}
                </p>
                {quote.reason && <p role="alert">{quote.reason}</p>}
              </>
            )}
          </div>
          <button
            type="submit"
            disabled={
              busy || uploading || incompatible || !quote?.ready || !endpoint
            }
          >
            {busy ? copy.sending : copy.generateImage}
          </button>
        </form>
        <p className="privacy">{copy.imageEstimateNotice}</p>
        <p className="privacy">{copy.imageUnsupportedAdapters}</p>
        {catalog && (
          <p className="privacy">
            {catalog.ranking} · {copy.refreshed}:{" "}
            {new Date(catalog.fetched_at * 1000).toLocaleString()}
          </p>
        )}
        {details && (
          <p className="privacy">
            {copy.imageProvider} · {copy.refreshed}:{" "}
            {new Date(details.fetched_at * 1000).toLocaleString()}
          </p>
        )}
      </div>
      <section
        className="image-history"
        aria-label={copy.imageHistory}
        ref={resultRef}
      >
        <h2>{copy.imageHistory}</h2>
        {!jobs.length && <p>{copy.imageEmpty}</p>}
        {jobs.map((job) => (
          <article className="image-job" key={job.id}>
            <div className="answer-heading">
              <strong>{job.model_name}</strong>
              <span>{job.provider_name}</span>
              <span role="status">
                {job.status === "succeeded" ? copy.completed : job.status}
              </span>
            </div>
            <SavedPrompt text={job.prompt} className="image-saved-prompt" />
            <div className="answer-meta">
              <span>
                {Object.entries(job.options)
                  .map(
                    ([key, value]) =>
                      `${labels[key as keyof typeof labels] ?? key}: ${value}`,
                  )
                  .join(" · ")}{" "}
                · {copy.imageCount}: {job.count}
              </span>
              <span>
                {copy.reservation}: {usd(job.reserved_microusd)} ·{" "}
                {copy.actualCost}:{" "}
                {job.actual_microusd == null
                  ? copy.unknownCost
                  : usd(job.actual_microusd)}
              </span>
              {job.queue_delay_ms != null && (
                <span>
                  {copy.queuedFor}: {job.queue_delay_ms} ms
                </span>
              )}
              {job.started_at && (
                <span>
                  {copy.startedAt}:{" "}
                  {new Date(job.started_at * 1000).toLocaleTimeString()}
                </span>
              )}
              {job.elapsed_ms != null && (
                <span>
                  {copy.elapsed}: {job.elapsed_ms} ms
                </span>
              )}
              {job.usage?.prompt_tokens != null && (
                <span>
                  {copy.inputTokens}: {String(job.usage.prompt_tokens)} ·{" "}
                  {copy.outputTokens}:{" "}
                  {String(job.usage.completion_tokens ?? "?")}
                </span>
              )}
            </div>
            {job.status === "submission_unknown" && (
              <p role="alert" className="error">
                {copy.imageUnknownSubmission}
              </p>
            )}
            {job.status === "failed" && (
              <p role="alert" className="error">
                {(job.error_code && copy.imageErrors[job.error_code]) ||
                  copy.imageFailure}
              </p>
            )}
            <div className="image-output-grid">
              {job.assets.map((asset, index) => (
                <figure key={asset.id}>
                  <img
                    src={`/api/media/${asset.id}`}
                    alt={`${job.prompt} (${index + 1})`}
                    loading="lazy"
                  />
                  <figcaption>
                    {asset.width} × {asset.height} · {copy.expires}:{" "}
                    {new Date(asset.expires_at * 1000).toLocaleDateString()}{" "}
                    <a href={`/api/media/${asset.id}?download=true`}>
                      {copy.imageDownload}
                    </a>
                  </figcaption>
                </figure>
              ))}
            </div>
            {!active(job) && !job.assets.length && <p>{copy.imageNoAssets}</p>}
            {job.assets.length > 0 && <small>{copy.imageNormalization}</small>}
            <details>
              <summary>{copy.imageReferences}</summary>
              <AttachmentPreview items={job.attachments} />
            </details>
            <div className="answer-actions">
              <button
                type="button"
                className="plain-button"
                disabled={active(job)}
                onClick={() => reuse(job)}
              >
                {copy.imageReuse}
              </button>
              <button
                type="button"
                className="plain-button"
                disabled={active(job)}
                onClick={() => void remove(job)}
              >
                {copy.imageDelete}
              </button>
            </div>
          </article>
        ))}
      </section>
    </section>
  );
}
