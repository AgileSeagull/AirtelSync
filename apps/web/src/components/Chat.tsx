import { useCallback, useEffect, useRef, useState } from "react";
import { api, type SessionView, type Tier } from "../api";
import { LANGUAGES, type Tr } from "../i18n";
import { speechSupported, useSpeech } from "../speech";
import { TierCards } from "./TierCards";

export function Chat({ session, setSession, tr, onChoose }: {
  session: SessionView; setSession: (s: SessionView) => void; tr: Tr; onChoose: (t: Tier) => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const speechLang = LANGUAGES.find((l) => l.code === session.lang)?.speech || "en-IN";

  const send = useCallback(async (msg: string) => {
    const m = msg.trim();
    if (!m || busy) return;
    setBusy(true);
    setError(null);
    setText("");
    // optimistic echo
    setSession({ ...session, transcript: [...session.transcript, { role: "user", text: m }] });
    try {
      setSession(await api.send(session.session_id, m));
    } catch {
      setError(tr("error"));
      setSession(session);
      setText(m);
    } finally {
      setBusy(false);
    }
  }, [busy, session, setSession, tr]);

  const { listening, toggle } = useSpeech(speechLang, (heard) => send(heard));

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); },
    [session.transcript.length, busy, session.recommendation]);

  const chipKey = session.recommendation ? null : (session.last_asked as string | null) || (session.transcript.length <= 1 ? "business_type" : null);
  const chips = chipKey ? (tr(`chips_${chipKey}` as any) as unknown as string[] | undefined) : undefined;

  return (
    <>
      <div className="chat" aria-live="polite">
        {session.transcript.map((turn, i) => (
          <div key={i} className={`bubble ${turn.role === "user" ? "me" : "bot"}`}>{turn.text}</div>
        ))}
        {busy && <div className="typing">{tr("thinking")}</div>}
        {session.recommendation && <TierCards rec={session.recommendation} tr={tr} lang={session.lang} onChoose={onChoose} />}
        {session.handoff && <div className="notice ok">{tr("handoff")}</div>}
        {error && <div className="notice bad">{error}</div>}
        <div ref={endRef} />
      </div>
      <form className="composer" onSubmit={(e) => { e.preventDefault(); send(text); }}>
        {Array.isArray(chips) && chips.length > 0 && (
          <div className="chips">
            {chips.map((c) => <button type="button" key={c} onClick={() => send(c)} disabled={busy}>{c}</button>)}
            <button type="button" onClick={() => send(tr("talkToPerson"))} disabled={busy}>{tr("talkToPerson")}</button>
          </div>
        )}
        <div className="inputrow">
          <label htmlFor="msg" className="sr-only" style={{ position: "absolute", left: -9999 }}>{tr("typeHere")}</label>
          <textarea id="msg" rows={1} value={text} placeholder={listening ? tr("listening") : tr("typeHere")}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }} />
          {speechSupported() && (
            <button type="button" className={`iconbtn mic${listening ? " on" : ""}`} onClick={toggle} aria-label="Speak" aria-pressed={listening}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
            </button>
          )}
          <button type="submit" className="iconbtn" aria-label={tr("send")} disabled={busy || !text.trim()}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M3 20.5 21 12 3 3.5l2.5 7L15 12l-9.5 1.5z" /></svg>
          </button>
        </div>
      </form>
    </>
  );
}
