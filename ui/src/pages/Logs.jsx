import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Copy, Pause, PhoneCall, Play, Terminal } from "../components/Icons";
import { logCall, logCalls, logStreamUrl } from "../lib/api";
import { useToast } from "../lib/toast";

const CAP = 5000;
const BACKLOG = 1500;
const ANSI = /\u001b\[[0-9;]*m/g;
const SHOWN = new Set(["ts", "level", "msg", "event", "logger", "error", "color_message", "call_id", "session_id", "channel"]);

const pad = (n) => String(n).padStart(2, "0");
const clock = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--:--:--" : `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
};

const day = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString([], { day: "2-digit", month: "short" });
};

function parse(raw, seq) {
  let r;
  if (typeof raw === "object" && raw) r = raw;
  else {
    try {
      r = JSON.parse(raw);
    } catch {
      return { seq, at: "", level: "INFO", logger: "", msg: String(raw), extra: "", error: null, callId: "", channel: "" };
    }
  }
  const extra = Object.entries(r)
    .filter(([k, v]) => !SHOWN.has(k) && v !== null && v !== "")
    .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`)
    .join(" ");
  return {
    seq,
    at: r.ts || "",
    level: String(r.level || "INFO").toUpperCase(),
    logger: r.logger || "",
    msg: String(r.msg || r.event || "").replace(ANSI, ""),
    extra,
    error: r.error || null,
    callId: r.call_id || "",
    channel: r.channel || "",
  };
}

function asText(line) {
  let text = `${clock(line.at)} ${line.level} ${line.logger}: ${line.msg}`;
  if (line.extra) text += `  ${line.extra}`;
  if (line.error) text += `\n${line.error.stack || `${line.error.type}: ${line.error.message}`}`;
  return text;
}

export default function Logs() {
  const toast = useToast();
  const [lines, setLines] = useState([]);
  const [connected, setConnected] = useState(false);
  const [logFile, setLogFile] = useState("");
  const [view, setView] = useState("stream");
  const [paused, setPaused] = useState(false);
  const [callId, setCallId] = useState("");
  const pausedRef = useRef(false);
  const held = useRef([]);
  const paneRef = useRef(null);
  const follow = useRef(true);

  useEffect(() => {
    pausedRef.current = paused;
    if (!paused && held.current.length) {
      const queued = held.current;
      held.current = [];
      setLines((current) => [...current, ...queued].slice(-CAP));
    }
  }, [paused]);

  useEffect(() => {
    const stream = new EventSource(logStreamUrl(BACKLOG));
    let seq = 0;
    stream.addEventListener("open", () => setConnected(true));
    stream.addEventListener("ready", (e) => {
      setConnected(true);
      try {
        setLogFile(JSON.parse(e.data).file || "");
      } catch {
      }
    });
    stream.addEventListener("log", (e) => {
      const line = parse(e.data, ++seq);
      if (pausedRef.current) held.current.push(line);
      else setLines((current) => [...current, line].slice(-CAP));
    });
    stream.addEventListener("error", () => setConnected(false));
    return () => stream.close();
  }, []);

  const [calls, setCalls] = useState([]);
  const [callLines, setCallLines] = useState([]);
  const [callIds, setCallIds] = useState([]);
  const [callError, setCallError] = useState("");

  useEffect(() => {
    if (view !== "calls") return undefined;
    let alive = true;
    const load = () => logCalls().then((r) => alive && setCalls(r.calls || [])).catch((e) => alive && setCallError(e.message));
    load();
    const id = setInterval(load, 10000);
    return () => { alive = false; clearInterval(id); };
  }, [view]);

  useEffect(() => {
    if (view === "calls" && !callId && calls.length) setCallId(calls[0].id);
  }, [view, calls, callId]);

  useEffect(() => {
    if (view !== "calls" || !callId) return;
    setCallLines([]);
    logCall(callId)
      .then((r) => {
        setCallIds(r.ids || [callId]);
        setCallLines((r.lines || []).map((raw, i) => parse(raw, -1e9 + i)));
      })
      .catch((e) => setCallError(e.message));
  }, [view, callId]);

  const shown = useMemo(() => {
    if (view !== "calls") return lines;
    const lastLoaded = callLines.length ? callLines[callLines.length - 1].at : "";
    const ids = new Set(callIds.length ? callIds : [callId]);
    const live = lines.filter((l) => ids.has(l.callId) && l.at > lastLoaded);
    return [...callLines, ...live];
  }, [lines, view, callId, callLines, callIds]);

  useEffect(() => {
    const node = paneRef.current;
    if (node && follow.current) node.scrollTop = node.scrollHeight;
  }, [shown]);

  const onScroll = useCallback(() => {
    const node = paneRef.current;
    if (node) follow.current = node.scrollHeight - node.scrollTop - node.clientHeight < 40;
  }, []);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(shown.map(asText).join("\n"));
      toast.ok(`Copied ${shown.length} lines`);
    } catch {
      toast.error("The browser blocked the clipboard");
    }
  };

  const picked = calls.find((c) => c.id === callId);

  return (
    <div className="page wide">
      <div className="page-head page-head-row">
        <div style={{ flex: 1, minWidth: 240 }}>
          <h1>Logs</h1>
          <p>Everything the voice service writes, live, exactly as it appears in the terminal. By call shows every line from one call.</p>
        </div>
        <div className="row">
          <span className={`pill ${connected ? "ok" : "halt"}`}>
            <span className={`lamp ${connected ? "on pulse" : "halt"}`} />
            {connected ? "live" : "reconnecting"}
          </span>
          {logFile && (
            <span className="pill" title={`Reading ${logFile}`}>
              <Terminal size={11} />
              {logFile.split("/").pop()}
            </span>
          )}
        </div>
      </div>

      <div className="card termcard">
        <div className="logbar">
          <div className="seg seg-sm">
            <button className={`seg-btn ${view === "stream" ? "on" : ""}`} onClick={() => setView("stream")}>
              <Terminal size={13} /> Stream
            </button>
            <button className={`seg-btn ${view === "calls" ? "on" : ""}`} onClick={() => setView("calls")}>
              <PhoneCall size={13} /> By call
            </button>
          </div>
          <span className="tiny faint">{shown.length} lines{paused && held.current.length ? ` · ${held.current.length} waiting` : ""}</span>
          <div className="grow" />
          <button className="btn btn-sm" onClick={() => setPaused((p) => !p)}>
            {paused ? <><Play size={13} /> Resume</> : <><Pause size={13} /> Pause</>}
          </button>
          <button className="btn btn-sm" onClick={copy} disabled={!shown.length}><Copy size={13} /> Copy</button>
          <button className="btn btn-sm btn-ghost" onClick={() => { setLines([]); held.current = []; }}>Clear</button>
        </div>

        <div className={`termwrap ${view === "calls" ? "with-calls" : ""}`}>
          {view === "calls" && (
            <aside className="termcalls">
              {callError && <p className="termcalls-empty">{callError}</p>}
              {calls.length === 0 ? (
                <p className="termcalls-empty">No call has logged anything yet. Lines appear here as soon as a call starts.</p>
              ) : calls.map((c) => (
                <button key={c.id} type="button" className={`termcall ${c.id === callId ? "on" : ""}`} onClick={() => { setCallId(c.id); follow.current = true; }}>
                  <span className="termcall-id mono">{c.id}</span>
                  <span className="termcall-meta">
                    {c.channel || "call"} · {day(c.first)} {clock(c.first)}–{clock(c.last)} · {c.count} lines
                    {c.errors > 0 && <b> · {c.errors} error{c.errors === 1 ? "" : "s"}</b>}
                  </span>
                </button>
              ))}
            </aside>
          )}
          <div className="term" ref={paneRef} onScroll={onScroll} role="log" aria-live="off">
            {view === "calls" && picked && <div className="term-banner"># call {picked.id}{picked.channel ? ` on ${picked.channel}` : ""}</div>}
            {shown.length === 0 ? (
              <div className="term-empty">{connected ? (view === "calls" ? "Pick a call on the left." : "Waiting for output…") : "Connecting to the log stream…"}</div>
            ) : shown.map((l) => (
              <div key={l.seq} className={`term-line lv-${l.level.toLowerCase()}`}>
                <span className="t-time">{clock(l.at)}</span> <span className="t-lvl">{l.level}</span>{" "}
                <span className="t-logger">{l.logger}:</span> <span className="t-msg">{l.msg}</span>
                {l.extra && <span className="t-extra">  {l.extra}</span>}
                {l.error && <div className="t-stack">{l.error.stack || `${l.error.type}: ${l.error.message}`}</div>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
