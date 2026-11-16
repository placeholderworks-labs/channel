import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, Alert, PhoneOut, Refresh, Sparkle, X } from "../components/Icons";
import { api } from "../lib/api";
import { clockTime, duration, relativeTime } from "../lib/format";

const DID_KEY = "voicebot.did";
const POLL_MS = 5000;

const TONE = {
  ACTIVE: { pill: "live", lamp: "live", label: "with bot" },
  TRANSFER_INITIATED: { pill: "warn", lamp: "warn", label: "transferring" },
  TRANSFERRED: { pill: "warn", lamp: "warn", label: "ringing you" },
  ACTIVE_WITH_AGENT: { pill: "ok", lamp: "on", label: "with agent" },
  ENDED: { pill: "", lamp: "", label: "ended" },
};

const FILTERS = [
  { key: "all", label: "On the line", count: "live" },
  { key: "bot", label: "With the bot", count: "withBot", statuses: ["ACTIVE"] },
  {
    key: "transferring",
    label: "Transferring",
    count: "transferring",
    tone: "warn",
    statuses: ["TRANSFER_INITIATED", "TRANSFERRED"],
  },
  {
    key: "agent",
    label: "With an agent",
    count: "withAgent",
    tone: "ok",
    statuses: ["ACTIVE_WITH_AGENT"],
  },
];

function tone(status) {
  return TONE[status] || { pill: "", lamp: "", label: (status || "").toLowerCase() };
}

function storedDid() {
  try {
    return localStorage.getItem(DID_KEY) || "";
  } catch {
    return "";
  }
}

function rememberDid(did) {
  try {
    if (did) localStorage.setItem(DID_KEY, did);
    else localStorage.removeItem(DID_KEY);
  } catch {
  }
}

function elapsedSince(iso, until) {
  if (!iso) return null;
  const end = until ? new Date(until).getTime() : Date.now();
  return Math.max(0, (end - new Date(iso).getTime()) / 1000);
}

function missed(call) {
  return (call?.endedReason || "").startsWith("agent_no_answer");
}

export default function ActiveCalls() {
  const [did, setDid] = useState(storedDid);
  const [dids, setDids] = useState([]);
  const [configuredDid, setConfiguredDid] = useState("");
  const [askLine, setAskLine] = useState(() => !storedDid());
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState(null);
  const [filter, setFilter] = useState("all");
  const [error, setError] = useState("");
  const [syncedAt, setSyncedAt] = useState(null);
  const [tick, setTick] = useState(0);
  const firstLoad = useRef(true);
  const autoPicked = useRef(false);

  const load = useCallback(async () => {
    if (!did) {
      setData(null);
      firstLoad.current = false;
      return;
    }
    try {
      const next = await api.activeCalls(did);
      setData(next);
      setSyncedAt(new Date().toISOString());
      setError("");
    } catch (e) {
      setError(e.message);
    } finally {
      firstLoad.current = false;
    }
  }, [did]);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    api
      .callDids()
      .then((r) => {
        setDids(r.dids || []);
        setConfiguredDid(r.configured || "");
      })
      .catch(() => setDids([]));
  }, []);

  useEffect(() => {
    if (!did) return undefined;
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [did]);

  const active = useMemo(() => data?.active || [], [data]);
  const ended = data?.recentlyEnded || [];
  const counts = data?.counts || {};

  useEffect(() => {
    if (autoPicked.current || !active.length) return;
    autoPicked.current = true;
    setSelected(active[0].id);
  }, [active]);

  const choose = (next) => {
    const clean = (next || "").trim();
    if (!clean) return;
    setAskLine(false);
    if (clean === did) return;
    setDid(clean);
    rememberDid(clean);
    setSelected(null);
    setFilter("all");
    firstLoad.current = true;
    autoPicked.current = false;
    setData(null);
    setSyncedAt(null);
  };

  const options = useMemo(() => {
    const all = [...dids];
    if (configuredDid && !all.includes(configuredDid)) all.unshift(configuredDid);
    return all;
  }, [dids, configuredDid]);

  const shown = useMemo(() => {
    const rule = FILTERS.find((f) => f.key === filter);
    if (!rule?.statuses) return active;
    return active.filter((call) => rule.statuses.includes(call.status));
  }, [active, filter]);

  const selectedRow = useMemo(
    () => [...active, ...ended].find((call) => call.id === selected) || null,
    [active, ended, selected],
  );

  const loading = !data && firstLoad.current && !!did;

  return (
    <div className="lc-page">
      <header className="lc-bar">
        <div className="lc-bar-title">
          <h1>Live Calls</h1>
          <p>Calls headed for your line: with the bot, handing over, or yours.</p>
        </div>

        <div className="lc-bar-right">
          <button className="lc-line" onClick={() => setAskLine(true)} title="Change line">
            <span className="eyebrow">Your line</span>
            <span className="mono">{did || "not set"}</span>
          </button>
          <span className={`pill ${active.length ? "live" : ""}`}>
            <span className={`lamp ${active.length ? "live" : ""}`} />
            {active.length ? `${active.length} on the line` : "quiet"}
          </span>
          <button className="btn btn-ghost btn-icon btn-sm" onClick={load} aria-label="Refresh now">
            <Refresh size={14} />
          </button>
          <span className="lc-sync">
            {error ? (
              <span className="lc-sync-bad">
                <Alert size={12} /> {error}
              </span>
            ) : (
              <span className="mono">
                {syncedAt ? `synced ${clockTime(syncedAt)}` : did ? "syncing…" : "no line set"}
              </span>
            )}
          </span>
        </div>
      </header>

      <div className="lc-counts">
        {FILTERS.map((item) => (
          <button
            key={item.key}
            className={`lc-count ${filter === item.key ? "on" : ""}`}
            onClick={() => setFilter(item.key)}
            disabled={!did}
          >
            <span className="eyebrow">{item.label}</span>
            <span className={`lc-count-value ${item.tone || ""}`}>{counts[item.count] ?? 0}</span>
          </button>
        ))}
      </div>

      {data?.note && (
        <div className="notice warn lc-note">
          <Alert size={15} />
          <span>{data.note}</span>
        </div>
      )}

      <div className="lc-body">
        <aside className="lc-rail">
          <div className="lc-rail-head">
            <span>{FILTERS.find((f) => f.key === filter)?.label || "On the line"}</span>
            <span className="lc-rail-n">{shown.length}</span>
          </div>

          <div className="lc-rail-scroll">
            {loading ? (
              <div className="lc-rail-pad stack">
                <div className="skeleton" style={{ height: 58 }} />
                <div className="skeleton" style={{ height: 58 }} />
                <div className="skeleton" style={{ height: 58 }} />
              </div>
            ) : shown.length === 0 ? (
              <div className="lc-rail-empty">
                <PhoneOut size={18} />
                <p>
                  {did
                    ? "Nothing here right now. A call appears the moment it connects."
                    : "Set your line to start watching."}
                </p>
                {!did && <button className="btn btn-primary btn-sm" onClick={() => setAskLine(true)}>Set your line</button>}
              </div>
            ) : (
              <div className="lc-list">
                {shown.map((call) => (
                  <CallCard
                    key={call.id}
                    call={call}
                    tick={tick}
                    on={selected === call.id}
                    onPick={() => setSelected(call.id)}
                  />
                ))}
              </div>
            )}

            {ended.length > 0 && (
              <>
                <div className="lc-rail-sub">
                  <span>Recently ended</span>
                  <span className="lc-rail-n">{ended.length}</span>
                </div>
                <div className="lc-list">
                  {ended.map((call) => (
                    <CallCard
                      key={call.id}
                      call={call}
                      past
                      on={selected === call.id}
                      onPick={() => setSelected(call.id)}
                    />
                  ))}
                </div>
              </>
            )}
          </div>
        </aside>

        <section className="lc-detail">
          {selected ? (
            <CallDetail
              key={selected}
              sessionId={selected}
              summary={selectedRow}
              tick={tick}
              onClose={() => setSelected(null)}
            />
          ) : (
            <div className="lc-detail-blank">
              <Activity size={22} />
              <h4>Pick a call to read it</h4>
              <p>
                The conversation so far, who is on the line, and every step the call has
                taken appear here.
              </p>
            </div>
          )}
        </section>
      </div>

      {askLine && (
        <LineDialog
          did={did}
          suggested={configuredDid}
          options={options}
          dismissible
          onChoose={choose}
          onClose={() => setAskLine(false)}
        />
      )}
    </div>
  );
}

function LineDialog({ did, suggested, options, dismissible, onChoose, onClose }) {
  const [typed, setTyped] = useState(did || "");
  const inputRef = useRef(null);

  useEffect(() => {
    if (suggested) setTyped((current) => current || suggested);
  }, [suggested]);

  useEffect(() => {
    inputRef.current?.focus();
    const onKey = (e) => {
      if (e.key === "Escape" && dismissible) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dismissible, onClose]);

  const submit = (event) => {
    event.preventDefault();
    onChoose(typed);
  };

  return (
    <>
      <div className="scrim lc-scrim" onClick={dismissible ? onClose : undefined} />
      <div className="lc-modal" role="dialog" aria-modal="true" aria-label="Choose your line">
        <div className="lc-modal-head">
          <div>
            <h2>{did ? "Change your line" : "Which line do you answer?"}</h2>
            <p>Calls transferred to this number are the ones this screen follows.</p>
          </div>
          {dismissible && (
            <button className="btn btn-ghost btn-icon btn-sm" onClick={onClose} aria-label="Close">
              <X size={14} />
            </button>
          )}
        </div>

        <form className="lc-modal-body" onSubmit={submit}>
          {options.length > 0 && (
            <div className="field">
              <span className="label">Lines we have seen calls on</span>
              <div className="lc-modal-picks">
                {options.map((item) => (
                  <button
                    type="button"
                    key={item}
                    className={`choice mono ${typed === item ? "on" : ""}`}
                    onClick={() => setTyped(item)}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="field">
            <label className="label" htmlFor="lc-line-input">
              Or type it
            </label>
            <input
              id="lc-line-input"
              ref={inputRef}
              className="input mono"
              placeholder="+91XXXXXXXXXX"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
            />
            <span className="hint">Kept on this device, so you only do this once.</span>
          </div>

          <div className="lc-modal-foot">
            {dismissible && (
              <button type="button" className="btn btn-ghost" onClick={onClose}>
                Cancel
              </button>
            )}
            <button type="submit" className="btn btn-primary" disabled={!typed.trim()}>
              Watch this line
            </button>
          </div>
        </form>
      </div>
    </>
  );
}

function CallCard({ call, tick, on, past, onPick }) {
  const state = past
    ? { pill: missed(call) ? "halt" : "", lamp: "", label: missed(call) ? "missed" : "ended" }
    : tone(call.status);
  const live = call.durationSecs ?? elapsedSince(call.answeredAt || call.startedAt, call.endedAt);

  return (
    <button className={`lc-item ${on ? "on" : ""} ${past ? "past" : ""}`} onClick={onPick} data-tick={tick}>
      <span className="lc-item-top">
        <span className={`pill ${state.pill}`}>
          <span className={`lamp ${state.lamp}`} />
          {state.label}
        </span>
        <span className="lc-item-clock mono">{duration(live)}</span>
      </span>
      <span className="lc-item-who mono">{call.customerNumber || "unknown number"}</span>
      <span className="lc-item-sub">
        {call.customerName || "No name on file"}
        {call.bookingReferenceId && <span className="mono"> · {call.bookingReferenceId}</span>}
        {past && <span className="faint"> · {relativeTime(call.endedAt)}</span>}
      </span>
    </button>
  );
}

function CallDetail({ sessionId, summary, tick, onClose }) {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("talk");
  const scrollRef = useRef(null);
  const pinned = useRef(false);
  const seenTurns = useRef(null);

  const load = useCallback(() => {
    api
      .callTranscript(sessionId)
      .then((r) => {
        setPayload(r);
        setError("");
      })
      .catch((e) => setError(e.message));
  }, [sessionId]);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const call = payload?.call || summary;
  const turns = payload?.turns || [];
  const steps = payload?.timeline || [];
  const state = tone(call?.status);
  const live = call?.durationSecs ?? elapsedSince(call?.answeredAt || call?.startedAt, call?.endedAt);

  useEffect(() => {
    const before = seenTurns.current;
    seenTurns.current = turns.length;
    const el = scrollRef.current;
    if (!el || before === null || turns.length <= before) return;
    if (tab === "talk" && !call?.endedAt && pinned.current) el.scrollTop = el.scrollHeight;
  }, [turns.length, tab, call?.endedAt]);

  useEffect(() => {
    seenTurns.current = null;
    pinned.current = false;
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
  }, [sessionId]);

  const onScroll = (event) => {
    const el = event.currentTarget;
    pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  };

  return (
    <>
      <header className="lc-detail-head">
        <div className="lc-detail-who">
          <h2>{call?.customerName || call?.customerNumber || `Call #${sessionId}`}</h2>
          <div className="lc-detail-line">
            <span className={`pill ${state.pill}`}>
              <span className={`lamp ${state.lamp}`} />
              {state.label}
            </span>
            <span className="mono small dim">{call?.customerNumber || "-"}</span>
            <span className="mono small dim" data-tick={tick}>
              {duration(live)} {call?.endedAt ? "long" : "on the line"}
            </span>
          </div>
        </div>
        <button className="btn btn-ghost btn-icon btn-sm" onClick={onClose} aria-label="Close call">
          <X size={14} />
        </button>
      </header>

      {error ? (
        <div className="lc-detail-pad">
          <div className="notice halt">
            <Alert size={15} />
            <span>{error}</span>
          </div>
        </div>
      ) : (
        <div className="lc-detail-scroll" ref={scrollRef} onScroll={onScroll}>
          <CallBrief sessionId={sessionId} turns={turns.length} hasCustomer={turns.some((t) => t.role === "customer" || t.role === "user")} />

          <dl className="lc-facts">
            <Fact label="Booking" value={call?.bookingReferenceId} mono />
            <Fact label="Your line" value={call?.did} mono />
            <Fact label="Agent leg" value={call?.agentNumber} mono />
            <Fact label="Started" value={call?.startedAt && clockTime(call.startedAt)} mono />
            <Fact
              label="Transferred"
              value={call?.transferredAt ? clockTime(call.transferredAt) : null}
              mono
            />
            <Fact
              label="Picked up"
              value={call?.agentAnsweredAt ? clockTime(call.agentAnsweredAt) : null}
              mono
            />
            {call?.endedAt && (
              <Fact
                label="Ended"
                value={`${clockTime(call.endedAt)}${call.endedReason ? ` · ${call.endedReason}` : ""}`}
                tone={missed(call) ? "halt" : ""}
              />
            )}
            {call?.recordingUrl && (
              <Fact
                label="Recording"
                value={
                  <a href={call.recordingUrl} target="_blank" rel="noreferrer">
                    Open
                  </a>
                }
              />
            )}
          </dl>

          <div className="lc-tabs">
            <button className={`seg-btn ${tab === "talk" ? "on" : ""}`} onClick={() => setTab("talk")}>
              Conversation
              <span className="lc-tab-n">{turns.length}</span>
            </button>
            <button className={`seg-btn ${tab === "steps" ? "on" : ""}`} onClick={() => setTab("steps")}>
              Timeline
              <span className="lc-tab-n">{steps.length}</span>
            </button>
          </div>

          <div className="lc-detail-body">
            {!payload ? (
              <div className="lc-detail-pad stack">
                <div className="skeleton" style={{ height: 16, width: "70%" }} />
                <div className="skeleton" style={{ height: 16, width: "52%" }} />
                <div className="skeleton" style={{ height: 16, width: "64%" }} />
              </div>
            ) : tab === "talk" ? (
              <Transcript turns={turns} />
            ) : (
              <Timeline steps={steps} />
            )}
          </div>
        </div>
      )}
    </>
  );
}

function Transcript({ turns }) {
  if (turns.length === 0) {
    return (
      <div className="lc-detail-blank small">
        <h4>Nothing said yet</h4>
        <p>The conversation appears turn by turn as it happens.</p>
      </div>
    );
  }

  return (
    <div className="lc-turns">
      {turns.map((turn) => (
        <div key={turn.id} className={`lc-turn ${turn.role === "customer" ? "them" : "bot"}`}>
          <span className="lc-turn-role">{turn.role === "customer" ? "Customer" : "Bot"}</span>
          <span className="lc-turn-text">
            {turn.text}
            {turn.role === "bot" && !turn.spoken && (
              <span className="lc-turn-note">cut off: the customer talked over it</span>
            )}
          </span>
          <span className="lc-turn-at mono">{clockTime(turn.at)}</span>
        </div>
      ))}
    </div>
  );
}

function Timeline({ steps }) {
  if (steps.length === 0) {
    return (
      <div className="lc-detail-blank small">
        <h4>No steps recorded</h4>
        <p>Each stage of the call lands here as it happens.</p>
      </div>
    );
  }

  return (
    <ol className="lc-steps">
      {steps.map((step, i) => (
        <li key={`${step.at}-${i}`} className={step.source === "provider" ? "lc-step-theirs" : ""}>
          <span className="lc-step-at mono">{clockTime(step.at)}</span>
          <span className="lc-step-mark" aria-hidden="true" />
          <span className="lc-step-label">{step.label}</span>
        </li>
      ))}
    </ol>
  );
}

function Fact({ label, value, mono, tone }) {
  return (
    <div className="lc-fact">
      <dt>{label}</dt>
      <dd className={`${mono ? "mono" : ""} ${tone ? `tone-${tone}` : ""} ${value ? "" : "faint"}`}>
        {value || "-"}
      </dd>
    </div>
  );
}

const BRIEF_EVERY_MS = 15000;

function CallBrief({ sessionId, turns, hasCustomer }) {
  const [brief, setBrief] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const last = useRef({ turns: 0, at: 0 });

  const load = useCallback(async (force = false) => {
    if (!hasCustomer) return;
    const now = Date.now();
    if (!force && (turns === last.current.turns || now - last.current.at < BRIEF_EVERY_MS)) return;
    last.current = { turns, at: now };
    setLoading(true);
    try {
      setBrief(await api.callBrief(sessionId));
      setError("");
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [sessionId, turns, hasCustomer]);

  useEffect(() => { setBrief(null); last.current = { turns: 0, at: 0 }; }, [sessionId]);
  useEffect(() => { load(); }, [load]);

  if (!hasCustomer) {
    return <div className="lc-brief muted"><Sparkle size={14} /> A summary appears here once the customer starts talking to the AI.</div>;
  }

  return (
    <section className="lc-brief">
      <div className="lc-brief-head">
        <span className="lc-brief-title"><Sparkle size={14} /> What the customer told the AI</span>
        {brief?.sentiment && <span className={`pill ${brief.sentiment === "negative" ? "halt" : brief.sentiment === "positive" ? "ok" : ""}`}>{brief.sentiment}</span>}
        <span className="grow" />
        <button className="btn btn-ghost btn-sm" onClick={() => load(true)} disabled={loading}>
          <Refresh size={12} /> {loading ? "Updating…" : "Refresh"}
        </button>
      </div>
      {error && !brief && <div className="notice warn"><Alert size={14} /><span>{error}</span></div>}
      {!brief && loading && (
        <div className="stack" style={{ gap: 8 }}>
          <div className="skeleton" style={{ height: 14, width: "92%" }} />
          <div className="skeleton" style={{ height: 14, width: "78%" }} />
          <div className="skeleton" style={{ height: 14, width: "60%" }} />
        </div>
      )}
      {brief && (
        <div className="lc-brief-body">
          <p className="lc-brief-summary">{brief.summary}</p>
          {brief.wants && <div className="lc-brief-row"><b>Wants</b><span>{brief.wants}</span></div>}
          {brief.done?.length > 0 && (
            <div className="lc-brief-row"><b>AI already</b><span>{brief.done.join(" · ")}</span></div>
          )}
          {brief.pending && <div className="lc-brief-row"><b>Still open</b><span>{brief.pending}</span></div>}
          {brief.facts?.length > 0 && (
            <div className="lc-brief-facts">{brief.facts.map((f) => <span key={f}>{f}</span>)}</div>
          )}
          {brief.next_step && <div className="lc-brief-next"><b>Start with:</b> {brief.next_step}</div>}
        </div>
      )}
    </section>
  );
}
