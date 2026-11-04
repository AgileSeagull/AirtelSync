import { useEffect, useRef, useState } from "react";
import { ApiError, kyc, type DocType, type KycCase, type KycCheck, type Lang, type Notice } from "../api";
import type { Tr } from "../i18n";

const SLOTS: DocType[] = ["gst_certificate", "udyam_certificate", "signatory_id", "address_proof"];
const SAMPLES = ["K01", "K02", "K03", "K04", "K05", "K06", "K07", "K08", "K09", "K10", "K11", "K12"];
const SLOT_LABEL: Record<DocType, { en: string; hi: string }> = {
  gst_certificate: { en: "GST certificate", hi: "GST सर्टिफ़िकेट" },
  udyam_certificate: { en: "Udyam certificate", hi: "Udyam सर्टिफ़िकेट" },
  signatory_id: { en: "Signatory ID", hi: "साइन करने वाले का ID" },
  address_proof: { en: "Address proof (bill)", hi: "पते का प्रमाण (बिल)" },
};

export function Kyc({ orderId, lang, tr, onTrack }: { orderId: string | null; lang: Lang; tr: Tr; onTrack: (oid: string) => void }) {
  const [c, setC] = useState<KycCase | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [purposes, setPurposes] = useState<string[]>(["kyc_verification"]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [gstin, setGstin] = useState("");
  const [otp, setOtp] = useState("");
  const fileRefs = useRef<Partial<Record<DocType, HTMLInputElement | null>>>({});

  useEffect(() => {
    kyc.notice(lang).then(setNotice).catch(() => setError("error"));
    const key = `udyam.kyc.${orderId || "demo"}`;
    let existing: string | null = null;
    try { existing = sessionStorage.getItem(key); } catch { /* ignore */ }
    (existing ? kyc.get(existing) : Promise.reject())
      .catch(() => kyc.create(orderId, lang))
      .then((k) => { setC(k); try { sessionStorage.setItem(key, k.id); } catch { /* ignore */ } })
      .catch(() => setError("error"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId, lang]);

  const run = async (label: string, fn: () => Promise<KycCase>) => {
    setBusy(label);
    setError(null);
    try { setC(await fn()); } catch (e) { setError(e instanceof ApiError ? e.message : tr("error")); } finally { setBusy(null); }
  };

  if (!c || !notice) return <main className="page"><p className="muted">…</p></main>;

  // ---------------------------------------------------------------- consent
  if (!c.consent_id) {
    return (
      <main className="page" style={{ paddingBottom: 40 }}>
        <h2 className="h2">{notice.title}</h2>
        <p style={{ margin: 0 }}>{notice.intro}</p>
        <section className="card notice-card">
          <div><div className="label">{tr("kycWhat")}</div><ul>{notice.collect.map((x) => <li key={x}>{x}</li>)}</ul></div>
          <div><div className="label">{tr("kycUse")}</div><p>{notice.use}</p></div>
          <div><div className="label">{tr("kycHow")}</div><p>{notice.how}</p></div>
          <div><div className="label">{tr("kycKeep")}</div><p>{notice.keep}</p></div>
          <div><div className="label">{tr("kycRights")}</div><p>{notice.rights}</p></div>
        </section>
        <fieldset className="card purposes">
          {Object.entries(notice.purposes).map(([k, label]) => {
            const required = k === "kyc_verification";
            return (
              <label key={k} className="purpose">
                <input type="checkbox" checked={purposes.includes(k)} disabled={required}
                  onChange={(e) => setPurposes((p) => (e.target.checked ? [...p, k] : p.filter((x) => x !== k)))} />
                <span>{label}</span>
              </label>
            );
          })}
        </fieldset>
        <p className="muted small" style={{ margin: 0 }}>Notice version {notice.version}</p>
        <button className="btn primary block" disabled={!!busy}
          onClick={() => run("consent", async () => (await kyc.consent(c.id, purposes, lang)).case)}>{notice.agree}</button>
        {error && <div className="notice bad">{error === "error" ? tr("error") : error}</div>}
      </main>
    );
  }

  // ---------------------------------------------------------------- signed
  if (c.esigned_at) {
    return (
      <main className="done">
        <div className="tick" aria-hidden>✓</div>
        <h2>{tr("signed")}</h2>
        <p className="muted" style={{ margin: 0 }}>{tr("signedBody")}</p>
        {c.order_id && <button className="btn primary block" onClick={() => onTrack(c.order_id!)}>{tr("trackOrder")}</button>}
      </main>
    );
  }

  const issues = c.checks.filter((x) => x.status === "action" || x.status === "review" || x.status === "block");
  const infos = c.checks.filter((x) => x.status === "info");
  const passed = c.checks.filter((x) => x.status === "pass");
  const verdictClass = { approved: "ok", needs_action: "warn", review: "info", blocked: "bad", pending: "" }[c.verdict];

  const fix = (ch: KycCheck) => {
    if (ch.action === "confirm_udyam") return run("udyam", () => kyc.confirmUdyam(c.id).then(() => kyc.verify(c.id)));
    if (ch.action === "digilocker") return run("digi", () => kyc.digilocker(c.id, gstin || null).then(() => kyc.verify(c.id)));
    if (ch.doc_type) fileRefs.current[ch.doc_type]?.click();
  };

  return (
    <main className="page" style={{ paddingBottom: 40 }}>
      <h2 className="h2">{tr("kycTitle")}</h2>

      {c.verdict !== "pending" && (
        <section className={`verdict ${verdictClass}`} aria-live="polite">
          <strong>{tr(`verdict_${c.verdict}` as any) as string}</strong>
          <span>{tr(`verdictBody_${c.verdict}` as any) as string}</span>
        </section>
      )}

      {issues.length > 0 && (
        <ul className="checks">
          {issues.map((ch) => (
            <li key={ch.code + ch.doc_type} className={`check ${ch.status}`}>
              <div className="check-head"><span className={`dot ${ch.status}`} aria-hidden />{ch.title}</div>
              <p>{ch.message}</p>
              {ch.status === "action" && ch.action !== "none" && (
                <button className="btn secondary small-btn" disabled={!!busy} onClick={() => fix(ch)}>
                  {ch.action === "retake" ? tr("fixRetake") : ch.action === "upload" ? tr("fixUpload")
                    : ch.action === "confirm_udyam" ? tr("fixConfirmUdyam") : tr("fixDigilocker")}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {c.verdict === "approved" && (
        <section className="card esign">
          <strong>{tr("esignTitle")}</strong>
          <span className="muted small">{tr("esignHint", { otp: c.demo_otp })}</span>
          <div className="inputrow">
            <label htmlFor="otp" style={{ position: "absolute", left: -9999 }}>OTP</label>
            <input id="otp" className="field" inputMode="numeric" maxLength={6} value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))} placeholder="••••••" />
            <button className="btn primary" disabled={otp.length !== 6 || !!busy} onClick={() => run("esign", () => kyc.esign(c.id, otp))}>{tr("esignBtn")}</button>
          </div>
        </section>
      )}

      <section className="card digi">
        <div style={{ display: "grid", gap: 2 }}>
          <strong>{tr("kycDigilocker")}</strong>
          <span className="muted small">{tr("kycDigilockerHint")}</span>
        </div>
        <div className="inputrow">
          <label htmlFor="gstin" style={{ position: "absolute", left: -9999 }}>{tr("kycGstinPrompt")}</label>
          <input id="gstin" className="field" placeholder={tr("kycGstinPrompt")} value={gstin} maxLength={15}
            onChange={(e) => setGstin(e.target.value.toUpperCase())} />
          <button className="btn secondary" disabled={!!busy} onClick={() => run("digi", () => kyc.digilocker(c.id, gstin || null))}>→</button>
        </div>
      </section>

      <section className="card" aria-label={tr("kycDocs")}>
        <ul className="rows">
          {SLOTS.map((slot) => {
            const d = c.documents[slot];
            const flagged = issues.some((x) => x.doc_type === slot);
            return (
              <li key={slot} className="row">
                <span className="name">{SLOT_LABEL[slot][lang === "hi" ? "hi" : "en"]}</span>
                <button className="add" onClick={() => fileRefs.current[slot]?.click()} disabled={!!busy}>
                  {d ? tr("kycReplace") : tr("kycUpload")}
                </button>
                <input type="file" accept="image/*" capture="environment" hidden ref={(el) => { fileRefs.current[slot] = el; }}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    e.target.value = "";
                    if (f) run(slot, async () => (await kyc.upload(c.id, f, slot)).case);
                  }} />
                <span className="sub">
                  {d ? (
                    <>
                      <span className={`pill${flagged ? " lock" : ""}`}>
                        {d.source === "digilocker" ? tr("kycFromDigilocker") : d.source === "registry" ? tr("kycFromRegistry") : `✓ ${tr("kycUploaded")}`}
                      </span>
                      <span>{summary(slot, d.fields)}</span>
                      {d.raw_deleted && d.source !== "digilocker" && d.source !== "registry" && <span>· {tr("rawDeleted")}</span>}
                    </>
                  ) : <span>—</span>}
                </span>
              </li>
            );
          })}
        </ul>
      </section>

      {(infos.length > 0 || passed.length > 0) && (
        <details className="card addons">
          <summary>{tr("checksPassed", { n: passed.length })}</summary>
          <ul className="checks flat">
            {[...infos, ...passed].map((ch, i) => (
              <li key={i} className={`check ${ch.status}`}>
                <div className="check-head"><span className={`dot ${ch.status}`} aria-hidden />{ch.title}</div>
                <p>{ch.message}</p>
              </li>
            ))}
          </ul>
        </details>
      )}

      <button className="btn primary block" disabled={!!busy || Object.keys(c.documents).length === 0}
        onClick={() => run("verify", () => kyc.verify(c.id))}>
        {busy ? tr("kycChecking") : tr("kycVerify")}
      </button>
      {error && <div className="notice bad">{error === "error" ? tr("error") : error}</div>}

      <div style={{ display: "grid", gap: 6 }}>
          <div className="label">{tr("kycSamples")}</div>
          <div className="chips wrap">
            {SAMPLES.map((s) => (
              <button key={s} type="button" disabled={!!busy}
                onClick={() => run(s, async () => { await kyc.sample(c.id, s); return kyc.verify(c.id); })}>{s}</button>
            ))}
          </div>
      </div>
      <button className="btn link" onClick={() => run("withdraw", () => kyc.withdraw(c.id))}>{tr("withdraw")}</button>
    </main>
  );
}

function summary(slot: DocType, f: Record<string, any>): string {
  if (slot === "gst_certificate") return [f.trade_name, f.gstin_resolved || f.gstin].filter(Boolean).join(" · ");
  if (slot === "udyam_certificate") return [f.enterprise_name, f.udyam_number].filter(Boolean).join(" · ");
  if (slot === "signatory_id") return [f.name, f.designation].filter(Boolean).join(" · ");
  return [f.billed_to, f.bill_date].filter(Boolean).join(" · ");
}
