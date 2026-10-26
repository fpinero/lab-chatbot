import { useEffect, useState, type FormEvent } from 'react';
import { bootstrap, preview } from './lib/api';
import { copy } from './lib/copy';

export default function App() {
  const [connected, setConnected] = useState(false);
  const [draft, setDraft] = useState('');
  const [result, setResult] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    void bootstrap().then(() => { if (active) setConnected(true); })
      .catch(() => { if (active) setError(copy.unavailable); });
    return () => { active = false; };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim() || busy) return;
    setBusy(true); setError('');
    try { setResult((await preview(draft.trim())).text); }
    catch { setError(copy.failed); }
    finally { setBusy(false); }
  }

  return <div className="workspace">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label={copy.appName}>
        <span className="brand-mark" aria-hidden="true">L</span>
        <span><strong>{copy.appName}</strong><small>{copy.subtitle}</small></span>
      </a>
      <div className="sidebar-note"><span className="eyebrow">{copy.roadmap}</span><p>{copy.roadmapDetail}</p></div>
      <span className="status"><i data-connected={connected} />{connected ? copy.connected : copy.connecting}</span>
    </aside>
    <main>
      <header><span className="mobile-brand">{copy.appName}</span><span className="badge">{copy.development}</span><span className="version">M0 / Bootstrap</span></header>
      <div className="content">
        <section className="intro"><span className="eyebrow">{copy.subtitle}</span><h1>{copy.title}</h1><p>{copy.description}</p></section>
        <section className="preview-panel" aria-label={copy.previewHeading}>
          <div className="notice">{copy.mockNotice}</div>
          {result && <article aria-live="polite" className="result"><span className="eyebrow">{copy.previewHeading}</span><p>{result}</p></article>}
          {error && <p role="alert" className="error">{error}</p>}
          <form onSubmit={event => void submit(event)}>
            <label className="sr-only" htmlFor="prompt">{copy.promptLabel}</label>
            <textarea id="prompt" rows={3} maxLength={2000} placeholder={copy.placeholder} value={draft} onChange={event => setDraft(event.target.value)} />
            <div className="composer-footer"><span>{draft.length} / 2000</span><button type="submit" disabled={!connected || busy || !draft.trim()}>{busy ? copy.sending : copy.submit}<span aria-hidden="true">↗</span></button></div>
          </form>
        </section>
        <p className="privacy">{copy.privacy}</p>
      </div>
    </main>
  </div>;
}
