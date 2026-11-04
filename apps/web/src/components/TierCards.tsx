import { inr, type Lang, type Recommendation, type Tier } from "../api";
import { whyText, type Tr } from "../i18n";

export function TierCards({ rec, tr, lang, onChoose }: { rec: Recommendation; tr: Tr; lang: Lang; onChoose: (t: Tier) => void }) {
  return (
    <section aria-label={tr("plans")}>
      <div className="label" style={{ padding: "4px 2px 8px" }}>{tr("plans")}</div>
      <div className="tiers">
        {rec.tiers.map((t) => {
          const q = t.quote;
          const best = t.tier === "recommended";
          return (
            <article key={t.tier} className={`tier${best ? " best" : ""}`}>
              <header>
                <h3>{tr(t.tier)}</h3>
                {best && <span className="badge">{tr("bestFit")}</span>}
              </header>
              <div>
                <div className="price">{inr(q.monthly_total)}<small>{tr("perMonth")} · {tr("inclGst")}</small></div>
                <div className="meta" style={{ marginTop: 6 }}>
                  <span>{q.setup_total ? `+ ${inr(q.setup_total)} ${tr("setup")}` : tr("noSetup")}</span>
                  <span>{tr("readyIn", { n: q.earliest_activation_days })}</span>
                </div>
              </div>
              <ul className="items">
                {t.items.map((i) => (
                  <li key={i.product_id}>
                    <span>{i.name}</span>
                    <span className="qty">{i.qty > 1 ? `×${i.qty}` : ""}</span>
                    <span className="why">{whyText(lang, i.reasons, i.why)}</span>
                  </li>
                ))}
              </ul>
              <button className={`btn ${best ? "primary" : "secondary"} block`} onClick={() => onChoose(t)}>
                {tr("customise")}
              </button>
            </article>
          );
        })}
      </div>
      {rec.notes.map((n) => <div key={n} className="notice" style={{ marginTop: 6 }}>{n}</div>)}
    </section>
  );
}
