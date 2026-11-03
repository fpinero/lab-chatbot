import { useEffect, useId, useRef, useState } from "react";
import { ApiError } from "../../lib/api";
import { copy } from "../../lib/copy";

type CatalogRefreshState = {
  pending: boolean;
  remaining: number;
  feedback: "" | "updated" | "limited" | "failed";
  failure: string;
  reload: () => Promise<void>;
};

export function useCatalogRefresh<
  T extends { refresh_after_seconds?: number },
>({
  catalog,
  refresh,
  onRefresh,
  expired,
}: {
  catalog: T | null;
  refresh: () => Promise<T>;
  onRefresh: (catalog: T) => void;
  expired: () => void;
}): CatalogRefreshState {
  const [pending, setPending] = useState(false);
  const [remaining, setRemaining] = useState(0);
  const [until, setUntil] = useState(0);
  const [feedback, setFeedback] = useState<
    "" | "updated" | "limited" | "failed"
  >("");
  const [failure, setFailure] = useState("");
  const deadline = useRef(0);
  const inFlight = useRef(false);
  const mounted = useRef(false);
  function wait(seconds: number) {
    const delay = Number.isFinite(seconds)
      ? Math.max(0, Math.min(3600, seconds))
      : 0;
    deadline.current = performance.now() + delay * 1000;
    setUntil(deadline.current);
    setRemaining(Math.ceil(delay));
  }
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    wait(catalog?.refresh_after_seconds ?? 0);
  }, [catalog]);
  useEffect(() => {
    if (until <= performance.now()) return;
    const timer = window.setInterval(() => {
      const seconds = Math.max(
        0,
        Math.ceil((until - performance.now()) / 1000),
      );
      setRemaining(seconds);
      if (!seconds) {
        window.clearInterval(timer);
        setFeedback((previous) => (previous === "limited" ? "" : previous));
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [until]);
  async function reload() {
    if (inFlight.current || deadline.current > performance.now()) return;
    inFlight.current = true;
    setPending(true);
    setFeedback("");
    setFailure("");
    try {
      const next = await refresh();
      if (!mounted.current) return;
      wait(next.refresh_after_seconds ?? 0);
      onRefresh(next);
      setFeedback("updated");
    } catch (error) {
      if (!mounted.current) return;
      if (error instanceof ApiError && error.status === 401) expired();
      else if (error instanceof ApiError && error.status === 429) {
        wait(error.retryAfterSeconds ?? 60);
        setFeedback("limited");
      } else {
        if (
          error instanceof ApiError &&
          (error.retryAfterSeconds || error.status === 503)
        )
          wait(error.retryAfterSeconds ?? 60);
        setFailure(
          error instanceof ApiError ? error.message : copy.catalogRefreshFailed,
        );
        setFeedback("failed");
      }
    } finally {
      inFlight.current = false;
      if (mounted.current) setPending(false);
    }
  }
  return { pending, remaining, feedback, failure, reload };
}

export default function CatalogRefresh({
  control,
}: {
  control: CatalogRefreshState;
}) {
  const { pending, remaining, feedback, failure, reload } = control;
  const waitId = useId();
  return (
    <div className="catalog-refresh">
      <button
        type="button"
        className="plain-button"
        aria-label={copy.refreshModels}
        aria-describedby={remaining ? waitId : undefined}
        aria-busy={pending}
        disabled={pending || remaining > 0}
        onClick={() => void reload()}
      >
        {pending
          ? copy.refreshingModels
          : remaining
            ? copy.refreshModelsWait(remaining)
            : copy.refreshModels}
      </button>
      {remaining > 0 && (
        <span id={waitId} className="sr-only">
          {copy.refreshModelsWait(remaining)}
        </span>
      )}
      {feedback === "failed" && (
        <p role="alert" className="error">
          {failure}
        </p>
      )}
      {(feedback === "updated" || feedback === "limited") && (
        <p role="status">
          {feedback === "updated"
            ? copy.modelsUpdated
            : copy.modelsRecentlyRefreshed}
        </p>
      )}
    </div>
  );
}
