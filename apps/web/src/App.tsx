import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type Lang, type SessionView, type Tier } from "./api";
import { Chat } from "./components/Chat";
import { Kyc } from "./components/Kyc";
import { OrderPlaced } from "./components/OrderPlaced";
import { QuoteBuilder } from "./components/QuoteBuilder";
import { Welcome } from "./components/Welcome";
import { t } from "./i18n";

type Route =
  | { name: "welcome" }
  | { name: "chat"; sid: string }
  | { name: "quote"; sid: string; tier: Tier["tier"] }
  | { name: "order"; oid: string }
  | { name: "kyc"; oid: string | null }
  | { name: "track"; oid: string };

function parse(hash: string): Route {
  const [, a, b, c] = hash.replace(/^#/, "").split("/");
  if (a === "chat" && b) return { name: "chat", sid: b };
  if (a === "quote" && b && c) return { name: "quote", sid: b, tier: c as Tier["tier"] };
  if (a === "order" && b) return { name: "order", oid: b };
  if (a === "kyc" && b) return { name: "kyc", oid: b };
  if (a === "kyc-demo") return { name: "kyc", oid: null };
  if (a === "track" && b) return { name: "track", oid: b };
  return { name: "welcome" };
}

function go(path: string) {
  window.location.hash = path;
}

function storedLang(): Lang {
  try { return (localStorage.getItem("udyam.lang") as Lang) || "hi"; } catch { return "hi"; }
}

export default function App() {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash));
  const [lang, setLangState] = useState<Lang>(storedLang);
  const [session, setSession] = useState<SessionView | null>(null);
  const [busy, setBusy] = useState(false);
  const activeLang = session?.lang || lang;
  const tr = useMemo(() => t(activeLang), [activeLang]);

  useEffect(() => {
    const on = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  // Restore the session after a reload.
  useEffect(() => {
    const sid = route.name === "chat" || route.name === "quote" ? route.sid : null;
    if (sid && session?.session_id !== sid) api.getSession(sid).then(setSession).catch(() => go("/"));
  }, [route, session?.session_id]);

  const setLang = (l: Lang) => {
    setLangState(l);
    try { localStorage.setItem("udyam.lang", l); } catch { /* private mode */ }
  };

  const start = useCallback(async () => {
    setBusy(true);
    try {
      const s = await api.startSession(lang);
      setSession(s);
      go(`/chat/${s.session_id}`);
    } finally {
      setBusy(false);
    }
  }, [lang]);

  const restart = () => { setSession(null); go("/"); };

  let body = null;
  let title = "Accel Udyam";
  let back: (() => void) | null = null;
  if (route.name === "welcome") {
    body = <Welcome lang={lang} setLang={setLang} onStart={start} busy={busy} tr={tr} />;
  } else if (route.name === "chat" && session) {
    body = <Chat session={session} setSession={setSession} tr={tr} onChoose={(tier) => go(`/quote/${session.session_id}/${tier.tier}`)} />;
  } else if (route.name === "quote" && session?.recommendation) {
    const tier = session.recommendation.tiers.find((x) => x.tier === route.tier) || session.recommendation.tiers[1];
    title = tr("yourPlan");
    back = () => go(`/chat/${session.session_id}`);
    body = <QuoteBuilder key={tier.tier} sid={session.session_id} tier={tier} tr={tr} lang={session.lang} onAccepted={(oid) => go(`/order/${oid}`)} />;
  } else if (route.name === "order") {
    body = <OrderPlaced orderId={route.oid} tr={tr} onKyc={() => go(`/kyc/${route.oid}`)} />;
  } else if (route.name === "kyc") {
    title = tr("kycTitle");
    body = <Kyc key={route.oid || "demo"} orderId={route.oid} lang={session?.lang || lang} tr={tr} onTrack={(oid) => go(`/track/${oid}`)} />;
  } else if (route.name === "track") {
    body = <main className="done"><h2>{tr("trackOrder")}</h2><p className="ref">{route.oid}</p></main>;
  }

  return (
    <div className="shell">
      <header className="topbar">
        {back && <button className="back" onClick={back} aria-label="Back">←</button>}
        <div className="brand">
          <svg width="26" height="26" viewBox="0 0 64 64" aria-hidden><rect width="64" height="64" rx="14" fill="#0e5352" /><path d="M16 44c6-14 12-22 16-22s10 8 16 22" fill="none" stroke="#f2a93b" strokeWidth="6" strokeLinecap="round" /><circle cx="32" cy="18" r="5" fill="#f2a93b" /></svg>
          <div>{title}<small>Accel Business</small></div>
        </div>
        <div className="spacer" />
        {route.name !== "welcome" && <button className="ghost" onClick={restart}>{tr("restart")}</button>}
      </header>
      {body}
    </div>
  );
}
