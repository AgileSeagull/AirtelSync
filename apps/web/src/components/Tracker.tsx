import { useCallback, useEffect, useState } from "react";
import { ApiError, fmtDate, inr, orders, type Lang, type Track } from "../api";
import type { Tr } from "../i18n";

export function Tracker({ orderId, lang, tr, onKyc }: { orderId: string; lang: Lang; tr: Tr; onKyc: () => void }) {
  const [t, setT] = useState<Track | null>(null);
  const [upi, setUpi] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => orders.track(orderId).then(setT).catch(() => setError("error")), [orderId]);

  useEffect(() => {
    load();
    const h = setInterval(load, 5000); // the owner sees back-office changes without refreshing
    return () => clearInterval(h);
  }, [load]);

  const act = async (fn: () => Promise<Track>) => {
    setBusy(true);
    setError(null);
    try { setT(await fn()); } catch (e) { setError(e instanceof ApiError ? e.message : "error"); } finally { setBusy(false); }
  };

  if (!t) return <main className="page"><p className="muted">…</p></main>;
  const L = (lang || t.lang) as Lang;

  let headline: string = t.label;
  if (t.state === "Activated") headline = tr("liveSince", { d: fmtDate(t.activated_at, L) });
  else if (t.eta) headline = tr("readyBy", { d: fmtDate(t.eta, L) });
  else if (t.state === "QuoteAccepted") headline = tr("waitingKyc");
  else if (t.state === "KYCVerified") headline = tr("waitingMandate");

  const notes = t.events.filter((e) => e.state === "Rerouted" || e.state === "Delayed");

  return (
    <main className="page" style={{ paddingBottom: 40 }}>
      <section className={`status-card${t.state === "Activated" ? " live" : t.sla_breach ? " late" : ""}`}>
        <div className="muted small">{t.business.trade_name || t.business.business_type} · <span className="ref small-ref">{t.order_id}</span></div>
        <div className="status-label">{t.label}</div>
        <div className="status-eta">{headline}</div>
        {t.install_slot && t.state === "InstallScheduled" && <div className="small">{tr("techVisit", { d: fmtDate(t.install_slot, L) })}</div>}
        {t.sla_breach && t.state !== "Activated" && <span className="badge late-badge">{tr("delayed")}</span>}
      </section>

      {t.owner_action?.type === "kyc" && (
        <button className="btn primary block" onClick={onKyc}>{tr("doKyc")}</button>
      )}
      {t.owner_action?.type === "mandate" && (
        <section className="card digi">
          <strong>{tr("mandateTitle")}</strong>
          <span className="muted small">{tr("mandateBody", { x: inr(t.owner_action.amount || 0) })}</span>
          <div className="inputrow">
            <label htmlFor="upi" style={{ position: "absolute", left: -9999 }}>UPI ID</label>
            <input id="upi" className="field" placeholder={tr("upiPlaceholder")} value={upi} onChange={(e) => setUpi(e.target.value.trim())} />
            <button className="btn primary" disabled={busy || !upi.includes("@")} onClick={() => act(() => orders.mandate(orderId, upi))}>{tr("setMandate")}</button>
          </div>
        </section>
      )}
      {error && <div className="notice bad">{error === "error" ? tr("error") : error}</div>}
      {notes.map((n, i) => <div key={i} className={`notice${n.state === "Rerouted" ? " ok" : ""}`}>{n.note}</div>)}

      <section className="card" aria-label={tr("progress")}>
        <ol className="timeline">
          {t.steps.map((s) => (
            <li key={s.state} className={`is-${s.status}`}>
              <span className="node" aria-hidden>{s.status === "done" ? "✓" : ""}</span>
              <div>
                <div className="step-label">{s.label}</div>
                {s.at && <div className="muted small">{fmtDate(s.at, L, true)}</div>}
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="card" aria-label={tr("services")}>
        <ul className="rows">
          {t.lines.map((l) => (
            <li key={l.product_id} className="row">
              <span className="name">{l.name}{l.qty > 1 ? ` ×${l.qty}` : ""}</span>
              <span className={`pill state-${l.state}`}>{tr(`line_${l.state}` as any) as string}</span>
              {l.eta && l.state !== "Active" && l.state !== "Installed" && <span className="sub">{fmtDate(l.eta, L)}</span>}
            </li>
          ))}
        </ul>
      </section>

      {t.state === "Activated" && (
        <section className="card refer">
          <strong>{tr("referTitle")}</strong>
          <span className="muted">{tr("referBody")}</span>
          <button className="btn secondary" onClick={() => navigator.clipboard?.writeText(`${location.origin}/?ref=${t.order_id}`)}>{tr("referBtn")}</button>
        </section>
      )}

      <section style={{ display: "grid", gap: 8 }}>
        <div className="label">{tr("messages")}</div>
        <p className="muted small" style={{ margin: 0 }}>{tr("noCalls")}</p>
        {t.notifications.length === 0 && <p className="muted small" style={{ margin: 0 }}>{tr("noMessages")}</p>}
        <div className="phone-msgs">
          {t.notifications.map((n) => (
            <div key={n.id} className="wa-msg">
              <span>{n.text}</span>
              <time className="muted">{fmtDate(n.at, L, true)}</time>
            </div>
          ))}
        </div>
      </section>

      <details className="card addons demo-controls">
        <summary>{tr("demo")}</summary>
        <div className="demo-btns">
          <button className="btn secondary" disabled={busy} onClick={() => act(() => orders.advance(orderId))}>{tr("demoNext")}</button>
          {t.state === "MandateSet" && <button className="btn secondary" disabled={busy} onClick={() => act(() => orders.advance(orderId, false))}>{tr("demoNoFibre")}</button>}
          {t.state === "InstallScheduled" && <button className="btn secondary" disabled={busy} onClick={() => act(() => orders.delay(orderId))}>{tr("demoDelay")}</button>}
        </div>
      </details>
    </main>
  );
}
