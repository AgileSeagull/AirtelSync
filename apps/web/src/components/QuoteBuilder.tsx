import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, inr, type Addon, type Contract, type Fix, type Lang, type Quote, type Tier } from "../api";
import { lockedText, whyText, type Tr } from "../i18n";

interface Row { product_id: string; name: string; qty: number; on: boolean; why?: string; unit: string }

const QTY_UNITS = new Set(["per line", "per user", "per device", "per camera", "per counter", "per vehicle", "per site", "per channel", "per IP"]);

export function QuoteBuilder({ sid, tier, tr, lang, onAccepted }: {
  sid: string; tier: Tier; tr: Tr; lang: Lang; onAccepted: (orderId: string) => void;
}) {
  const [rows, setRows] = useState<Row[]>(() =>
    tier.items.map((i) => ({ product_id: i.product_id, name: i.name, qty: i.qty, on: true, why: whyText(lang, i.reasons, i.why), unit: i.unit })));
  const [contract, setContract] = useState<Contract>("12");
  const [quote, setQuote] = useState<Quote | null>(tier.quote);
  const [fixes, setFixes] = useState<Fix[]>([]);
  const [addons, setAddons] = useState<Addon[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reqId = useRef(0);

  const active = useMemo(() => rows.filter((r) => r.on).map((r) => ({ product_id: r.product_id, qty: r.qty })), [rows]);

  useEffect(() => {
    const id = ++reqId.current;
    const h = setTimeout(async () => {
      try {
        const r = await api.quote(sid, active, contract);
        if (id !== reqId.current) return;
        setQuote(r.quote);
        setFixes(r.fixes);
        setAddons(r.addons);
        setError(null);
      } catch (e) {
        if (id === reqId.current) setError(e instanceof ApiError ? e.message : tr("error"));
      }
    }, 150);
    return () => clearTimeout(h);
  }, [sid, active, contract, tr]);

  const lineFor = (pid: string) => quote?.lines.find((l) => l.product_id === pid);
  const update = (pid: string, patch: Partial<Row>) => setRows((rs) => rs.map((r) => (r.product_id === pid ? { ...r, ...patch } : r)));
  const addRow = (a: { product_id: string; name: string; qty: number; unit: string }) =>
    setRows((rs) => rs.some((r) => r.product_id === a.product_id)
      ? rs.map((r) => (r.product_id === a.product_id ? { ...r, on: true } : r))
      : [...rs, { ...a, on: true }]);

  const applyFix = (f: Fix) => {
    if (f.action === "remove") update(f.product_id, { on: false });
    else {
      const addon = addons.find((a) => a.product_id === f.product_id);
      addRow({ product_id: f.product_id, name: f.name, qty: f.qty || 1, unit: addon?.unit || "per site" });
    }
  };

  const accept = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.accept(sid, active, contract);
      onAccepted(r.order_id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : tr("error"));
    } finally {
      setBusy(false);
    }
  };

  const blocked = fixes.length > 0 || active.length === 0;
  const eligibleAddons = addons.filter((a) => a.eligible);
  const lockedAddons = addons.filter((a) => !a.eligible);

  return (
    <>
      <main className="page">
        <section style={{ display: "grid", gap: 8 }}>
          <div className="label" id="contract-label">{tr("contract")}</div>
          <div className="seg" role="group" aria-labelledby="contract-label">
            {(["flexible", "12", "24"] as Contract[]).map((c) => (
              <button key={c} type="button" aria-pressed={contract === c} onClick={() => setContract(c)}>
                {c === "flexible" ? tr("flexible") : c === "12" ? tr("months12") : tr("months24")}
                {c === "24" && <small>{tr("saveMore")}</small>}
              </button>
            ))}
          </div>
        </section>

        {fixes.map((f) => (
          <div key={f.violation.product_id + f.violation.rule} className="notice bad fix">
            <span>{lockedText(lang, f.violation.rule, f.violation.message)}{lang === "hi" ? ` (${f.violation.product_id === f.product_id ? f.name : rows.find((r) => r.product_id === f.violation.product_id)?.name || ""})` : ""}</span>
            <button onClick={() => applyFix(f)}>{f.action === "add" ? `${tr("add")} ${f.name}` : `${tr("remove")}`}</button>
          </div>
        ))}

        <section className="card" aria-label={tr("yourPlan")}>
          <ul className="rows">
            {rows.map((r) => {
              const line = lineFor(r.product_id);
              return (
                <li key={r.product_id} className={`row${r.on ? "" : " off"}`}>
                  <span className="name">{r.name}</span>
                  <button className="switch" role="switch" aria-checked={r.on} aria-label={r.name}
                    onClick={() => update(r.product_id, { on: !r.on })} />
                  <span className="sub">
                    {QTY_UNITS.has(r.unit) && r.on && (
                      <span className="stepper" aria-label="quantity">
                        <button type="button" aria-label="less" onClick={() => update(r.product_id, { qty: Math.max(1, r.qty - 1) })}>−</button>
                        <span>{r.qty}</span>
                        <button type="button" aria-label="more" onClick={() => update(r.product_id, { qty: Math.min(99, r.qty + 1) })}>+</button>
                      </span>
                    )}
                    {line && r.on && <span>{inr(line.unit_price)} {r.unit} · {line.contract_months} mo</span>}
                    {line && r.on && <span style={{ marginLeft: "auto", fontWeight: 600, color: "var(--ink)" }}>{inr(line.monthly)}</span>}
                  </span>
                  {r.why && r.on && <span className="sub">{r.why}</span>}
                </li>
              );
            })}
          </ul>
        </section>

        <details className="card addons">
          <summary>{tr("addMore")}</summary>
          <ul className="rows">
            {eligibleAddons.map((a) => (
              <li key={a.product_id} className="row addon">
                <span className="name">{a.name}</span>
                <button className="add" onClick={() => addRow({ product_id: a.product_id, name: a.name, qty: a.default_qty, unit: a.unit })}>{tr("add")}</button>
                <span className="sub">{a.description}</span>
                <span className="sub">{tr("from")} {inr(a.price_from)} {a.unit}{a.setup_fee ? ` · setup ${inr(a.setup_fee)}` : ""}</span>
              </li>
            ))}
            {lockedAddons.map((a) => (
              <li key={a.product_id} className="row addon locked">
                <span className="name">{a.name}</span>
                <span className="pill lock">{tr("locked")}</span>
                <span className="sub">{lockedText(lang, a.locked_rule, a.locked_reason)}</span>
              </li>
            ))}
          </ul>
        </details>
        <p className="muted small" style={{ margin: 0 }}>{tr("priceRule")}</p>
        {quote?.notes.map((n) => <p key={n} className="muted small" style={{ margin: 0 }}>{n}</p>)}
      </main>

      <div className="summary">
        <div className="inner">
          {quote && (
            <>
              <div className="breakdown">
                <span>{tr("subtotal")}</span><span>{inr(quote.subtotal_monthly)}</span>
                {quote.bundle_discount > 0 && <><span>{tr("discount")} ({quote.bundle_discount_pct}%)</span><span>−{inr(quote.bundle_discount)}</span></>}
                <span>{tr("gst")}</span><span>{inr(quote.gst)}</span>
                <span>{tr("setupTotal")}</span><span>{quote.setup_total ? inr(quote.setup_total) : tr("noSetup")}</span>
                {quote.setup_waived > 0 && <><span className="muted">{tr("waived")}</span><span className="muted">−{inr(quote.setup_waived)}</span></>}
                {quote.monthly_difference !== null && quote.monthly_difference !== 0 && (
                  <><span className="muted">{tr("vsToday")}</span>
                    <span className="muted">{quote.monthly_difference > 0 ? tr("moreThanToday", { x: inr(quote.monthly_difference) }) : tr("lessThanToday", { x: inr(-quote.monthly_difference) })}</span></>
                )}
              </div>
              <div className="total">
                <div>
                  <div className="muted small">{tr("monthly")} · {tr("readyIn", { n: quote.earliest_activation_days })}</div>
                  <div className="price">{inr(quote.monthly_total)}<small>{tr("perMonth")}</small></div>
                </div>
                <button className="btn primary" onClick={accept} disabled={busy || blocked}>{tr("accept")}</button>
              </div>
            </>
          )}
          {error && <div className="notice bad">{error}</div>}
        </div>
      </div>
    </>
  );
}
