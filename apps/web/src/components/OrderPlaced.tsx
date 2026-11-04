import type { Tr } from "../i18n";

export function OrderPlaced({ orderId, tr, onKyc }: { orderId: string; tr: Tr; onKyc: () => void }) {
  return (
    <main className="done">
      <div className="tick" aria-hidden>✓</div>
      <h2>{tr("orderPlaced")}</h2>
      <div>
        <div className="label">{tr("orderId")}</div>
        <div className="ref">{orderId}</div>
      </div>
      <div className="card" style={{ padding: 16, display: "grid", gap: 8 }}>
        <strong>{tr("nextKyc")}</strong>
        <span className="muted">{tr("nextKycBody")}</span>
        <button className="btn primary block" onClick={onKyc}>{tr("continueKyc")}</button>
      </div>
    </main>
  );
}
