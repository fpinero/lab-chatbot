import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  loginInfo,
  login,
  logout,
  session,
  preview,
  type LoginInfo,
  type SessionInfo,
} from "./lib/api";
import { copy } from "./lib/copy";

export default function App() {
  const [info, setInfo] = useState<LoginInfo | null>(null);
  const [ownerSession, setOwnerSession] = useState<SessionInfo | null>(null);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void Promise.all([
      loginInfo(),
      session().catch((error) => {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }),
    ])
      .then(([config, current]) => {
        if (active) {
          setInfo(config);
          setOwnerSession(current);
        }
      })
      .catch(() => {
        if (active) setError(copy.unavailable);
      });
    return () => {
      active = false;
    };
  }, []);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setOwnerSession(await login(password, code));
      setPassword("");
      setCode("");
    } catch (error) {
      setError(
        error instanceof ApiError && error.status === 429
          ? copy.throttled
          : copy.signInFailed,
      );
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    try {
      await logout();
      setOwnerSession(null);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401)
        setOwnerSession(null);
      else setError(copy.failed);
    }
  }

  if (ownerSession)
    return (
      <Workspace
        notice={error}
        ownerSession={ownerSession}
        signOut={() => void signOut()}
        expired={() => {
          setOwnerSession(null);
          setError(copy.expired);
        }}
      />
    );
  return (
    <main className="login-page">
      <section className="login-card">
        <a className="brand" href="/">
          <span className="brand-mark" aria-hidden="true">
            L
          </span>
          <strong>{copy.appName}</strong>
        </a>
        {info && info.environment !== "production" && (
          <span className="badge">{copy.development}</span>
        )}
        <h1>{copy.loginTitle}</h1>
        <p>{copy.loginDescription}</p>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {!info ? (
          <p role="status">{copy.loading}</p>
        ) : (
          <form onSubmit={(event) => void signIn(event)}>
            {info.auth_mode === "password" && (
              <label>
                {copy.password}
                <input
                  type="password"
                  autoComplete="current-password"
                  maxLength={1024}
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </label>
            )}
            {info.requires_code && (
              <label>
                {copy.code}
                <input
                  autoComplete="off"
                  maxLength={128}
                  required
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                />
              </label>
            )}
            <button type="submit" disabled={busy}>
              {busy ? copy.signingIn : copy.signIn}
            </button>
          </form>
        )}
        <small>{copy.secureNotice}</small>
      </section>
    </main>
  );
}

function Workspace({
  ownerSession,
  signOut,
  expired,
  notice,
}: {
  notice: string;
  ownerSession: SessionInfo;
  signOut: () => void;
  expired: () => void;
}) {
  const connected = true;
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      setResult((await preview(draft.trim())).text);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) expired();
      else setError(copy.failed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="workspace">
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
        <a className="brand" href="/" aria-label={copy.appName}>
          <span className="brand-mark" aria-hidden="true">
            L
          </span>
          <span>
            <strong>{copy.appName}</strong>
            <small>{copy.subtitle}</small>
          </span>
        </a>
        <div className="sidebar-note">
          <span className="eyebrow">{copy.roadmap}</span>
          <p>{copy.roadmapDetail}</p>
        </div>
        <span className="status">
          <i data-connected={connected} />
          {connected ? copy.connected : copy.connecting}
        </span>
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
        <div className="content">
          <section className="intro">
            <span className="eyebrow">{copy.subtitle}</span>
            <h1>{copy.title}</h1>
            <p>{copy.description}</p>
          </section>
          {ownerSession.provider_mode === "mock" ? (
            <section className="preview-panel" aria-label={copy.previewHeading}>
              <div className="notice">{copy.mockNotice}</div>
              {result && (
                <article aria-live="polite" className="result">
                  <span className="eyebrow">{copy.previewHeading}</span>
                  <p>{result}</p>
                </article>
              )}
              {(error || notice) && (
                <p role="alert" className="error">
                  {error || notice}
                </p>
              )}
              <form onSubmit={(event) => void submit(event)}>
                <label className="sr-only" htmlFor="prompt">
                  {copy.promptLabel}
                </label>
                <textarea
                  id="prompt"
                  rows={3}
                  maxLength={2000}
                  placeholder={copy.placeholder}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                />
                <div className="composer-footer">
                  <span>{draft.length} / 2000</span>
                  <button
                    type="submit"
                    disabled={!connected || busy || !draft.trim()}
                  >
                    {busy ? copy.sending : copy.submit}
                    <span aria-hidden="true">↗</span>
                  </button>
                </div>
              </form>
            </section>
          ) : (
            <p>{copy.livePending}</p>
          )}
          <p className="privacy">{copy.privacy}</p>
        </div>
      </main>
    </div>
  );
}
