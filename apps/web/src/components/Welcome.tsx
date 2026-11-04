import type { Lang } from "../api";
import { LANGUAGES, type Tr } from "../i18n";

export function Welcome({ lang, setLang, onStart, busy, tr }: {
  lang: Lang; setLang: (l: Lang) => void; onStart: () => void; busy: boolean; tr: Tr;
}) {
  return (
    <main className="welcome">
      <div style={{ display: "grid", gap: 10 }}>
        <h1>{tr("tagline")}</h1>
      </div>
      <ul className="promises">
        <li><span>1</span>{tr("promise1")}</li>
        <li><span>₹</span>{tr("promise2")}</li>
        <li><span>✓</span>{tr("promise3")}</li>
      </ul>
      <div style={{ display: "grid", gap: 10 }}>
        <div className="label" id="lang-label">{tr("chooseLang")}</div>
        <div className="langs" role="group" aria-labelledby="lang-label">
          {LANGUAGES.map((l) => (
            <button key={l.code} type="button" aria-pressed={lang === l.code} onClick={() => setLang(l.code)}>
              <b>{l.native}</b>
              <small>{l.english}</small>
            </button>
          ))}
        </div>
      </div>
      <button className="btn primary block" onClick={onStart} disabled={busy}>{tr("start")} →</button>
      <a className="btn link center" href="#/kyc-demo">Try Smart KYC with sample applicants →</a>
      <p className="muted small center" style={{ margin: 0 }}>
        Accel Business · prototype for YTL Hackathon 2026. All data is synthetic.
      </p>
    </main>
  );
}
