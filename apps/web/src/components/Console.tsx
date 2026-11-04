import { useCallback, useEffect, useState } from "react";
import { ApiError, consoleApi, inr, type Driver, type Role } from "../api";

type Tab = "overview" | "leads" | "reengage" | "reviews" | "model";
const ROUTE_LABEL: Record<string, string> = { field_sales: "Field sales", channel_partner: "Channel partner", inside_sales: "Inside sales" };
const SEG: Record<string, string> = { micro: "Micro retail", prof: "Professional", multi: "Multi-site", mfg: "Manufacturer" };

function Drivers({ ds }: { ds: Driver[] }) {
  return <span className="drivers">{ds.map((d) => <span key={d.factor} className={`drv ${d.effect}`}>{d.effect === "up" ? "▲" : "▼"} {d.factor}</span>)}</span>;
}

function Score({ v }: { v: number }) {
  const pct = Math.round(v * 100);
  return <span className="score"><span className="score-bar"><span style={{ width: `${Math.min(100, pct * 3)}%` }} /></span>{pct}%</span>;
}

function Funnel({ title, rows }: { title: string; rows: { stage: string; count: number }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <section className="c-card">
      <h3>{title}</h3>
      <ul className="funnel">
        {rows.map((r, i) => (
          <li key={r.stage}>
            <span className="f-stage">{r.stage}</span>
            <span className="f-bar"><span style={{ width: `${(r.count / max) * 100}%` }} /></span>
            <span className="f-num">{r.count.toLocaleString("en-IN")}{i > 0 && rows[i - 1].count > 0 ? <small> {Math.round((r.count / rows[i - 1].count) * 100)}%</small> : null}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Console() {
  const [role, setRole] = useState<Role>("sales");
  const [tab, setTab] = useState<Tab>("overview");
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [assist, setAssist] = useState<Record<string, { code?: string; input: string; url?: string }>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setError(null);
    try {
      const fn = { overview: consoleApi.summary, leads: consoleApi.leads, reengage: consoleApi.reengage, reviews: consoleApi.reviews, model: consoleApi.model }[tab];
      setData(await fn(role));
    } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load"); }
  }, [tab, role]);

  useEffect(() => { setData(null); load(); }, [load]);

  const tabs: [Tab, string][] = [["overview", "Overview"], ["leads", "Leads to call"], ["reengage", "Re-engage Q2"], ["reviews", "KYC reviews"], ["model", "Lead score model"]];

  return (
    <div className="console">
      <header className="c-top">
        <div className="brand"><b>Accel Business</b> · Udyam console</div>
        <div className="seg c-role" role="group" aria-label="Signed in as">
          <button aria-pressed={role === "sales"} onClick={() => setRole("sales")}>Accel staff</button>
          <button aria-pressed={role === "partner"} onClick={() => setRole("partner")}>Channel partner</button>
        </div>
        <a className="c-link" href="#/">Owner app →</a>
      </header>
      <nav className="c-tabs">
        {tabs.filter(([t]) => role === "sales" || (t !== "reviews" && t !== "model")).map(([t, label]) => (
          <button key={t} aria-current={tab === t} onClick={() => setTab(t)}>{label}</button>
        ))}
      </nav>
      <main className="c-main">
        {error && <div className="notice bad">{error}</div>}
        {!data && !error && <p className="muted">Loading…</p>}

        {tab === "overview" && data?.digital_funnel && (
          <>
            <div className="tiles">
              <div className="tile"><span>Model AUC (June holdout)</span><b>{data.model.test_auc}</b></div>
              <div className="tile"><span>Top-decile lift</span><b>{data.model.top_decile_lift}×</b></div>
              <div className="tile"><span>KYC reviews waiting</span><b>{data.kyc_review_queue}</b></div>
              <div className="tile"><span>Install SLA breaches</span><b>{data.sla_breaches}</b></div>
              <div className="tile"><span>Asked for a person</span><b>{data.handoffs}</b></div>
            </div>
            <div className="c-grid">
              <Funnel title="Q2 2026 field-led funnel (smb_leads.csv)" rows={data.q2_baseline_funnel} />
              <Funnel title="Digital journey (this demo)" rows={data.digital_funnel} />
            </div>
            <section className="c-card"><h3>KYC verdicts</h3>
              <div className="tiles">{Object.entries(data.kyc_verdicts).map(([k, v]) => <div key={k} className="tile"><span>{k.replace("_", " ").replace(/^./, (c) => c.toUpperCase())}</span><b>{v as number}</b></div>)}</div>
            </section>
          </>
        )}

        {tab === "leads" && Array.isArray(data) && (
          <section className="c-card">
            <h3>Leads the advisor didn't close <small className="muted">ranked by score × monthly value</small></h3>
            {data.length === 0 && <p className="muted">No open leads. Start a conversation in the owner app and leave it before accepting.</p>}
            <div className="table-wrap"><table className="c-table">
              <thead><tr><th>Business</th><th>Score</th><th>Why</th><th>Value/mo</th><th>Stopped at</th><th>Route</th><th></th></tr></thead>
              <tbody>
                {data.map((l: any) => {
                  const a = assist[l.session_id];
                  return (
                    <tr key={l.session_id}>
                      <td><b>{l.business}</b><div className="muted small">{SEG[l.segment]} · {l.city || "city?"}</div><div className="muted small">"{l.last_message}"</div></td>
                      <td><Score v={l.score} /></td>
                      <td><Drivers ds={l.drivers} /></td>
                      <td className="num">{inr(l.monthly_value)}</td>
                      <td className="small">{l.reason}</td>
                      <td><span className="pill">{ROUTE_LABEL[l.route_to]}</span></td>
                      <td className="act">
                        {!a && <button className="btn secondary sm" onClick={async () => { const r = await consoleApi.assist(role, l.session_id); setAssist({ ...assist, [l.session_id]: { code: r.demo_code, input: "" } }); }}>Offer help</button>}
                        {a && !a.url && (
                          <div className="assist">
                            <span className="muted small">Owner got a code on WhatsApp (demo: {a.code})</span>
                            <input className="field sm" placeholder="Code" value={a.input} onChange={(e) => setAssist({ ...assist, [l.session_id]: { ...a, input: e.target.value } })} />
                            <button className="btn primary sm" onClick={async () => {
                              try { const r = await consoleApi.assistConfirm(role, l.session_id, a.input, role === "partner" ? "Sharma Telecom (partner)" : "Accel inside sales"); setAssist({ ...assist, [l.session_id]: { ...a, url: r.continue_url } }); }
                              catch (e) { setError(e instanceof ApiError ? e.message : "Failed"); }
                            }}>Confirm</button>
                          </div>
                        )}
                        {a?.url && <a className="btn primary sm" href={a.url} target="_blank" rel="noreferrer">Continue journey</a>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table></div>
          </section>
        )}

        {tab === "reengage" && data?.leads && (
          <>
            <section className="c-card">
              <h3>{data.pool.toLocaleString("en-IN")} Q2 leads lost before a needs assessment</h3>
              <div className="drivers">{Object.entries(data.reasons).map(([k, v]) => <span key={k} className="drv">{k}: {v as number}</span>)}</div>
            </section>
            <section className="c-card">
              <h3>Best 25 to win back</h3>
              <div className="table-wrap"><table className="c-table">
                <thead><tr><th>Lead</th><th>Score</th><th>Why</th><th>Lost because</th><th>Next action</th></tr></thead>
                <tbody>{data.leads.map((l: any) => (
                  <tr key={l.lead_id}>
                    <td><b>{l.business}</b><div className="muted small">{l.lead_id} · {l.segment} · {l.city} · {l.language}</div></td>
                    <td><Score v={l.score} /></td><td><Drivers ds={l.drivers} /></td>
                    <td className="small">{l.drop_reason}<div className="muted small">via {l.source}</div></td>
                    <td className="small">{l.suggested_channel}</td>
                  </tr>))}</tbody>
              </table></div>
            </section>
          </>
        )}

        {tab === "reviews" && Array.isArray(data) && (
          <section className="c-card">
            <h3>KYC cases waiting for a specialist</h3>
            {data.length === 0 && <p className="muted">Nothing to review. Try sample applicant K07 in the owner app's Smart KYC demo.</p>}
            {data.map((c: any) => (
              <article key={c.id} className="review">
                <div><b>{c.business || c.id}</b> <span className="muted small">{c.id}{c.order_id ? ` · order ${c.order_id}` : ""}</span></div>
                <ul>{c.issues.map((i: any) => <li key={i.code}><b>{i.title}.</b> {i.message}</li>)}</ul>
                <div className="inputrow">
                  <input className="field" placeholder="Reason for decision (audit-logged)" value={notes[c.id] || ""} onChange={(e) => setNotes({ ...notes, [c.id]: e.target.value })} />
                  <button className="btn secondary sm" onClick={() => consoleApi.decide(role, c.id, "approve", notes[c.id] || "").then(load, (e) => setError(e.message))}>Approve</button>
                  <button className="btn sm danger" onClick={() => consoleApi.decide(role, c.id, "reject", notes[c.id] || "").then(load, (e) => setError(e.message))}>Reject</button>
                </div>
              </article>
            ))}
          </section>
        )}

        {tab === "model" && data?.evaluation && (
          <div className="c-grid">
            <section className="c-card">
              <h3>How good is the score?</h3>
              <p className="small">Trained on April–May leads, tested on {data.evaluation.test_rows.toLocaleString("en-IN")} June leads it never saw.</p>
              <div className="tiles">
                <div className="tile"><span>AUC</span><b>{data.evaluation.test_auc}</b></div>
                <div className="tile"><span>Base activation</span><b>{(data.evaluation.base_rate * 100).toFixed(1)}%</b></div>
                <div className="tile"><span>Top 10% activation</span><b>{(data.evaluation.top_decile_rate * 100).toFixed(1)}%</b></div>
                <div className="tile"><span>Activations in top 30%</span><b>{Math.round(data.evaluation.top30_share_of_activations * 100)}%</b></div>
              </div>
              <p className="muted small">Not used as inputs: {data.excluded}.</p>
            </section>
            <section className="c-card">
              <h3>Strongest factors</h3>
              <ul className="coefs">{data.coefficients.map((c: any) => (
                <li key={c.factor}><span>{c.factor}</span>
                  <span className="coef-track"><span className={c.weight > 0 ? "pos" : "neg"} style={{ width: `${Math.min(50, Math.abs(c.weight) * 50)}%` }} /></span>
                  <span className="num">{c.weight > 0 ? "+" : ""}{c.weight}</span></li>))}</ul>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
