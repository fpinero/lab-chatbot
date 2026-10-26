import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  loginInfo,
  login,
  logout,
  session,
  type LoginInfo,
  type SessionInfo,
} from "./lib/api";
import Workspace from "./features/chat/Workspace";
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
