import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useSearchParams } from "react-router-dom";
import { Alert, Chat, Check, CheckCircle, Clock, Cpu, History as HistoryIcon, Info, Refresh, Search, Sparkle, X, Zap } from "../components/Icons";
import { Badge, Select, Skeleton, Tabs } from "../components/ui";
import { api } from "../lib/api";
import { clockTime, relativeTime } from "../lib/format";
import { useAuth } from "../lib/auth";
import { useToast } from "../lib/toast";

const POLL_MS = 5000;

export const STATUS = {
  awaiting_agent: { pill: "warn", label: "trigger pending", call: "waiting for an agent" },
  scheduled: { pill: "brand", label: "scheduled", call: "waiting" },
  dialing: { pill: "live", label: "dialing", call: "dialing" },
  triggered: { pill: "ok", label: "call triggered", call: "yes" },
  rejected: { pill: "halt", label: "rejected", call: "no" },
  duplicate: { pill: "warn", label: "duplicate", call: "no" },
  failed: { pill: "halt", label: "failed", call: "no" },
  cancelled: { pill: "", label: "cancelled", call: "no" },
};

const FILTERS = [
  { key: "", label: "All", count: "received" },
  { key: "awaiting_agent", label: "Trigger pending", count: "awaiting_agent" },
  { key: "scheduled", label: "Scheduled", count: "scheduled" },
  { key: "triggered", label: "Triggered", count: "triggered" },
  { key: "rejected", label: "Rejected", count: "rejected" },
  { key: "duplicate", label: "Duplicate", count: "duplicate" },
  { key: "failed", label: "Failed", count: "failed" },
  { key: "cancelled", label: "Cancelled", count: "cancelled" },
];

function stamp(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.toLocaleDateString([], { day: "2-digit", month: "short" })} ${clockTime(iso)}`;
}

function StatusPill({ status }) {
  const s = STATUS[status] || { pill: "", label: status };
  return (
    <span className={`pill ${s.pill}`}>
      <span className={`lamp ${s.pill === "ok" ? "on" : s.pill}`} />
      {s.label}
    </span>
  );
}

export default function History() {
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const filter = params.get("status") || "";
  const agent = params.get("agent") || "";
  const source = params.get("source") || "";
  const setParam = (key, value) =>
    setParams((p) => {
      const next = new URLSearchParams(p);
      if (value) next.set(key, value);
      else next.delete(key);
      return next;
    }, { replace: true });
  const setFilter = (v) => setParam("status", v);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(null);
  const [syncedAt, setSyncedAt] = useState(null);
  const [retrying, setRetrying] = useState(null);
  const { can } = useAuth();
  const canRetry = can("calls.place");

  useEffect(() => {
    const id = setTimeout(() => setSearch(query.trim()), 300);
    return () => clearTimeout(id);
  }, [query]);

  const load = useCallback(async () => {
    try {
      setData(await api.history({ status: filter, q: search, agent, source }));
      setSyncedAt(new Date().toISOString());
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, [filter, search, agent, source]);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const retry = async (id) => {
    setRetrying(id);
    try {
      const r = await api.retryIngestion(id);
      toast.ok(r.message);
      return r.ingestionId;
    } catch (e) {
      toast.error(e.message);
      return null;
    } finally {
      setRetrying(null);
      load();
    }
  };

  const counts = data?.counts;
  const events = data?.events || [];
  const filtered = !!(filter || agent || source || search);

  return (
    <div className="page ing-page">
      <div className="page-head page-head-row">
        <div style={{ flex: 1, minWidth: 260 }}>
          <h1>History</h1>
          <p>
            Every call request from the QMS intakes and the Phone test, and what happened to it.
            Filter by status, agent or source; retry a failed call from its row.
          </p>
        </div>
        <div className="row">
          <span className="tiny faint mono">
            {error ? "" : syncedAt ? `synced ${clockTime(syncedAt)}` : "syncing…"}
          </span>
          <button className="btn btn-sm" onClick={load}>
            <Refresh size={14} />
            Refresh
          </button>
        </div>
      </div>

      <div className="stack" style={{ gap: 16 }}>
        {error && (
          <div className="notice halt">
            <Alert size={15} />
            <span>{error}</span>
          </div>
        )}
        {data && !data.persisted && (
          <div className="notice warn">
            <Info size={15} />
            <span>
              No database configured. Records are kept in memory only and scheduled calls do
              not survive a restart.
            </span>
          </div>
        )}
        {data?.note && (
          <div className="notice warn">
            <Alert size={15} />
            <span>{data.note}</span>
          </div>
        )}

        <div className="grid grid-4">
          <Metric label="Received" value={counts?.received} unit="last 24h" foot={filtered ? "matching the agent and source filters" : "every record, valid or not"} />
          <Metric
            label="Calls triggered"
            value={counts?.triggered}
            unit="last 24h"
            tone="ok"
            foot={counts?.failed ? `${counts.failed} failed at the provider` : "none failed"}
          />
          <Metric
            label="Not dialled"
            value={counts ? counts.rejected + counts.duplicate : undefined}
            unit="last 24h"
            tone={counts?.rejected ? "halt" : undefined}
            foot={counts ? `${counts.rejected} rejected · ${counts.duplicate} duplicate` : ""}
          />
          <Metric label="Waiting to ring" value={counts?.pending} unit="scheduled" foot="queued, not yet dialled" />
        </div>

        <section className="card">
          <div className="card-body ing-toolbar">
            <div className="seg seg-sm ing-seg">
              {FILTERS.map((f) => (
                <button
                  key={f.key || "all"}
                  className={`seg-btn ${filter === f.key ? "on" : ""}`}
                  onClick={() => setFilter(f.key)}
                >
                  {f.label}
                  {counts && <span className="lc-tab-n">{counts[f.count] ?? 0}</span>}
                </button>
              ))}
            </div>
            <div className="hist-filters">
              <div className="hist-select">
                <Select
                value={agent}
                onChange={(v) => setParam("agent", v)}
                options={[{ value: "", label: "All agents" }, ...(data?.agents || []).map((a) => ({ value: a, label: a }))]}
                />
              </div>
              <div className="hist-select">
                <Select
                value={source}
                onChange={(v) => setParam("source", v)}
                options={[{ value: "", label: "All sources" }, ...(data?.sources || []).map((x) => ({ value: x.id, label: x.label }))]}
                />
              </div>
            <div className="searchbar" style={{ flex: 1, minWidth: 220 }}>
              <Search size={15} />
              <input
                className="searchinput"
                placeholder="Reference, number, name or reason"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              {query && (
                <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setQuery("")} aria-label="Clear search">
                  <X size={14} />
                </button>
              )}
            </div>
            </div>
          </div>

          {!data && !error ? (
            <div className="card-body stack">
              <div className="skeleton" style={{ height: 40 }} />
              <div className="skeleton" style={{ height: 40 }} />
              <div className="skeleton" style={{ height: 40 }} />
            </div>
          ) : events.length === 0 ? (
            <div className="empty">
              <HistoryIcon size={20} />
              <h4>{filtered ? "Nothing matches" : "No calls yet"}</h4>
              <p>
                {filtered
                  ? "Try another filter or clear the search."
                  : "Records appear here the moment a QMS intake or the Phone test sends one."}
              </p>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="table ing-table">
                <thead>
                  <tr>
                    <th>Received</th>
                    <th>Customer</th>
                    <th>Reference</th>
                    <th>Agent · source</th>
                    <th>Status</th>
                    <th>Call</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((e) => (
                    <tr key={e.id} onClick={() => setSelected(e)} className="ing-row">
                      <td className="nowrap">
                        <div className="mono small">{stamp(e.receivedAt)}</div>
                        <div className="tiny faint">{relativeTime(e.receivedAt)}</div>
                      </td>
                      <td>
                        <div className="small" style={{ fontWeight: 600 }}>{e.name || <span className="faint">no name</span>}</div>
                        <div className="mono tiny faint">{e.phone || "no number"}</div>
                      </td>
                      <td className="mono small">{e.referenceId || <span className="faint">-</span>}</td>
                      <td className="nowrap">
                        <div className="mono small">{e.agent || <span className="faint">-</span>}</div>
                        <div className="tiny faint">{e.sourceLabel}</div>
                      </td>
                      <td><StatusPill status={e.status} /></td>
                      <td className="nowrap small">
                        <CallCell event={e} onRetry={canRetry ? retry : null} retrying={retrying === e.id} />
                      </td>
                      <td className="small ing-reason">
                        {e.reason ? <span className={e.status === "rejected" || e.status === "failed" ? "tone-halt" : "dim"}>{e.reason}</span> : <span className="faint">-</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      {selected && (
        <EventDetail
          initial={selected}
          onClose={() => setSelected(null)}
          onChanged={load}
          onRetry={canRetry ? retry : null}
          retrying={retrying === selected.id}
        />
      )}
    </div>
  );
}

function CallCell({ event, onRetry, retrying }) {
  if (event.status === "triggered") {
    return (
      <span className="tone-ok">
        <Check size={13} /> {clockTime(event.triggeredAt)}
      </span>
    );
  }
  if (event.status === "scheduled") {
    return <span className="dim">at {stamp(event.scheduledFor)}</span>;
  }
  if (event.status === "dialing") return <span className="dim">dialing now</span>;
  if (event.status === "failed" && onRetry) {
    return (
      <button className="btn btn-sm" disabled={retrying}
        onClick={(e) => { e.stopPropagation(); onRetry(event.id); }}>
        <Refresh size={12} /> {retrying ? "Retrying…" : "Retry"}
      </button>
    );
  }
  return <span className="faint">not triggered</span>;
}

const ms = (v) => (v == null ? "-" : v >= 1000 ? `${(v / 1000).toFixed(2)}s` : `${Math.round(v)}ms`);
const secs = (v) => (v == null ? "-" : v >= 60 ? `${Math.floor(v / 60)}m ${Math.round(v % 60)}s` : `${Math.round(v)}s`);
const OUTCOME_TONE = { converted: "ok", interested: "ok", callback: "brand", transferred: "brand", not_interested: "warn", unresolved: "warn", wrong_number: "halt", no_conversation: "" };

function EventDetail({ initial, onClose, onChanged, onRetry, retrying }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [event, setEvent] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState("conversation");
  const [summary, setSummary] = useState({ loading: false, data: null, error: "" });

  useEffect(() => {
    let alive = true;
    const pull = () =>
      api
        .callDetail(initial.id)
        .then((d) => {
          if (!alive) return;
          setData(d);
          setEvent(d.event);
          if (d.summary) setSummary((s) => (s.data ? s : { loading: false, data: d.summary, error: "" }));
        })
        .catch(() => {});
    pull();
    const id = setInterval(pull, POLL_MS);
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      alive = false;
      clearInterval(id);
      window.removeEventListener("keydown", onKey);
    };
  }, [initial.id, onClose]);

  const summarize = useCallback(async (refresh = false) => {
    setSummary({ loading: true, data: null, error: "" });
    try {
      setSummary({ loading: false, data: await api.callSummary(initial.id, refresh), error: "" });
    } catch (e) {
      setSummary({ loading: false, data: null, error: e.message });
    }
  }, [initial.id]);

  const transcript = data?.transcript || [];
  useEffect(() => {
    if (data && transcript.length && !data.summary && !summary.loading && !summary.data && !summary.error) summarize(false);
  }, [data, transcript.length, summary, summarize]);

  const cancel = async () => {
    setBusy(true);
    try {
      setEvent(await api.cancelIngestion(event.id));
      toast.ok("Call cancelled");
      onChanged();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const record = data?.record;
  const session = data?.session;
  const metrics = record?.metrics;
  const duration = session?.durationSecs ?? record?.durationSecs ?? metrics?.durationSecs;
  const tabs = [
    { id: "conversation", label: "Conversation", badge: transcript.length || undefined },
    { id: "latency", label: "Latency & providers" },
    { id: "timeline", label: "Timeline" },
    { id: "request", label: "Request" },
  ];

  return createPortal(
    <>
      <div className="scrim lc-scrim" onClick={onClose} />
      <div className="lc-modal ing-modal call-modal" role="dialog" aria-modal="true" aria-label="Call details">
        <div className="lc-modal-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2>{event.name || event.referenceId || `Record #${event.id}`}</h2>
            <div className="row" style={{ gap: 8, marginTop: 6, flexWrap: "wrap" }}>
              <StatusPill status={event.status} />
              {event.agent && <Badge tone="brand">{event.agent}</Badge>}
              <span className="tiny faint">{event.sourceLabel}</span>
              <span className="mono tiny faint">#{event.id} · {event.phone || "no number"} · {event.referenceId || "no reference"}</span>
            </div>
          </div>
          <button className="btn btn-ghost btn-icon btn-sm" onClick={onClose} aria-label="Close">
            <X size={14} />
          </button>
        </div>

        <div className="lc-modal-body ing-modal-body">
          <div className="call-kpis">
            <CallKpi icon={<Clock size={15} />} label="Duration" value={secs(duration)} />
            <CallKpi icon={<Chat size={15} />} label="Turns" value={metrics?.turns?.length ?? record?.transcriptTurns ?? (transcript.length ? Math.ceil(transcript.length / 2) : "-")} />
            <CallKpi icon={<Zap size={15} />} label="Avg response" value={ms(metrics?.averageMs)} />
            <CallKpi icon={<CheckCircle size={15} />} label="Outcome" value={sentence(summary.data?.outcome ? summary.data.outcome.replaceAll("_", " ") : session?.endedReason || record?.endedReason || STATUS[event.status]?.label || "-")} />
          </div>

          {event.reason && (
            <div className={`notice ${event.status === "rejected" || event.status === "failed" ? "halt" : "warn"}`}>
              <Alert size={15} />
              <span>{event.reason}</span>
            </div>
          )}

          {(transcript.length > 0 || summary.loading || summary.data) && (
            <div className="call-summary">
              <div className="row" style={{ gap: 8 }}>
                <span className="gsug-title"><Sparkle size={14} /> Summary</span>
                {summary.data?.outcome && <Badge tone={OUTCOME_TONE[summary.data.outcome] ?? ""}>{summary.data.outcome.replaceAll("_", " ")}</Badge>}
                {summary.data?.sentiment && <span className="tiny faint">sentiment: {summary.data.sentiment}</span>}
                <span className="grow" />
                {transcript.length > 0 && (
                  <button className="btn btn-ghost btn-sm" onClick={() => summarize(true)} disabled={summary.loading}>
                    <Refresh size={13} /> {summary.loading ? "Writing…" : "Rewrite"}
                  </button>
                )}
              </div>
              {summary.loading && <Skeleton h={54} r={8} />}
              {summary.error && <div className="notice warn"><Alert size={15} /><span>{summary.error}</span></div>}
              {summary.data && (
                <>
                  <p className="call-summary-text">{summary.data.summary}</p>
                  {summary.data.next_step && <p className="small" style={{ margin: 0 }}><strong>Next step:</strong> {summary.data.next_step}</p>}
                </>
              )}
            </div>
          )}

          <Tabs value={tab} onChange={setTab} tabs={tabs} />

          {tab === "conversation" && (
            transcript.length === 0 ? (
              <p className="hint" style={{ margin: 0 }}>
                {!data ? "Loading…" : event.callRecordId ? "No conversation was recorded for this call. The customer may not have answered." : "This request never became a call, so there is no conversation."}
              </p>
            ) : (
              <div className="chatlog">
                {transcript.map((m) => (
                  <div key={m.id} className={`chatmsg ${m.role === "user" || m.role === "customer" ? "user" : "bot"}`}>
                    <div className="chatmsg-who">{m.role === "user" || m.role === "customer" ? event.name || "Customer" : event.agent || "Agent"}{m.at && <span>{clockTime(m.at)}</span>}</div>
                    <div className="chatmsg-text">{m.text}{m.spoken === false && <span className="tiny faint"> (not spoken)</span>}</div>
                  </div>
                ))}
              </div>
            )
          )}

          {tab === "latency" && <LatencyView metrics={metrics} />}

          {tab === "timeline" && (
            <dl className="deflist">
              <Row label="Received" value={stamp(event.receivedAt)} />
              <Row label="Scheduled for" value={event.scheduledFor ? stamp(event.scheduledFor) : "-"} />
              <Row label="Dial requested" value={record?.createdAt ? stamp(record.createdAt) : event.triggeredAt ? stamp(event.triggeredAt) : "-"} />
              <Row label="Answered" value={session?.answeredAt ? stamp(session.answeredAt) : "-"} />
              {session?.transferredAt && <Row label="Transferred to a person" value={stamp(session.transferredAt)} />}
              <Row label="Ended" value={session?.endedAt ? stamp(session.endedAt) : record?.endedAt ? stamp(record.endedAt) : "-"} />
              <Row label="Ended because" value={session?.endedReason || record?.endedReason || "-"} />
              <Row label="Provider call id" value={event.providerCallId || record?.providerCallId || "-"} />
              {session?.recordingUrl && (
                <div className="defrow"><dt>Recording</dt><dd><a href={session.recordingUrl} target="_blank" rel="noreferrer">Open recording</a></dd></div>
              )}
              {record?.error && <Row label="Dial error" value={record.error} tone="halt" />}
            </dl>
          )}

          {tab === "request" && (
            <div className="stack" style={{ gap: 14 }}>
              <dl className="deflist">
                <Row label="Source" value={event.sourceLabel || event.source || "-"} />
                <Row label="Agent" value={event.agent || "-"} />
                <Row label="Sent by" value={event.sourceIp || "-"} />
                <Row label="Channel" value={event.channel || "-"} />
                {event.callRecordId && <Row label="Dial attempt" value={`call_records #${event.callRecordId}`} />}
              </dl>
              {event.errors?.length > 0 && (
                <div>
                  <div className="eyebrow">What was wrong</div>
                  <ul className="ing-errors">
                    {event.errors.map((err, i) => (
                      <li key={i}><code>{err.field || "record"}</code> {err.error}</li>
                    ))}
                  </ul>
                </div>
              )}
              <div>
                <div className="eyebrow">Payload as received</div>
                <pre className="prewrap datapre ing-payload">{JSON.stringify(event.payload ?? {}, null, 2)}</pre>
              </div>
            </div>
          )}

          {event.status === "failed" && onRetry && (
            <div className="lc-modal-foot">
              <span className="tiny faint" style={{ flex: 1 }}>
                Dials the same payload again now, as a new record. Every field is checked again first.
              </span>
              <button className="btn btn-primary btn-sm" disabled={retrying}
                onClick={async () => { if (await onRetry(event.id)) onClose(); }}>
                <Refresh size={13} /> {retrying ? "Retrying…" : "Retry this call"}
              </button>
            </div>
          )}

          {event.status === "scheduled" && (
            <div className="lc-modal-foot">
              <button className="btn btn-danger btn-sm" onClick={cancel} disabled={busy}>
                {busy ? "Cancelling…" : "Cancel this call"}
              </button>
            </div>
          )}
        </div>
      </div>
    </>,
    document.body
  );
}

const sentence = (text) => (text ? text.charAt(0).toUpperCase() + text.slice(1) : text);

function CallKpi({ icon, label, value }) {
  return (
    <div className="call-kpi">
      <span className="call-kpi-icon">{icon}</span>
      <div style={{ minWidth: 0 }}>
        <div className="tiny faint">{label}</div>
        <div className="call-kpi-value ellipsis">{value}</div>
      </div>
    </div>
  );
}

function LatencyView({ metrics }) {
  if (!metrics) {
    return <p className="hint" style={{ margin: 0 }}>Latency is recorded when a call ends. Calls placed before this was added, or that never connected, have none.</p>;
  }
  const p = metrics.providers || {};
  const turns = metrics.turns || [];
  const peak = Math.max(1, ...turns.map((t) => t.totalMs || 0));
  const tokens = metrics.tokens || {};
  const cost = metrics.cost || {};
  const total = Object.entries(cost).filter(([k]) => k.endsWith("_inr")).reduce((sum, [, v]) => sum + (Number(v) || 0), 0);
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="provider-chips">
        <ProviderChip leg="Speech to text" color="stt" name={p.stt?.provider} detail={p.stt?.model} avg={metrics.averageSttMs} />
        <ProviderChip leg="Language model" color="llm" name={p.llm?.provider} detail={p.llm?.model} avg={metrics.averageLlmMs} />
        <ProviderChip leg="Text to speech" color="tts" name={p.tts?.provider} detail={p.tts?.voice} avg={metrics.averageTtsMs} />
      </div>
      <div className="call-kpis">
        <CallKpi icon={<Zap size={15} />} label="Average turn" value={ms(metrics.averageMs)} />
        <CallKpi icon={<Zap size={15} />} label="Fastest" value={ms(metrics.minMs)} />
        <CallKpi icon={<Zap size={15} />} label="Slowest" value={ms(metrics.maxMs)} />
        <CallKpi icon={<Cpu size={15} />} label="Tokens" value={tokens.totalTokens != null ? `${tokens.totalTokens.toLocaleString()} (${tokens.cachedTokens || 0} cached)` : "-"} />
      </div>
      {turns.length === 0 ? <p className="hint" style={{ margin: 0 }}>No complete turn was measured on this call.</p> : (
        <div className="turnbars">
          <div className="turnbars-legend tiny faint">
            <span><i className="leg-stt" /> STT</span><span><i className="leg-llm" /> LLM</span><span><i className="leg-tts" /> TTS</span><span><i className="leg-sil" /> lead silence</span>
          </div>
          {turns.map((t) => (
            <div key={t.turn} className="turnbar">
              <span className="mono tiny faint">#{t.turn}</span>
              <div className="turnbar-track">
                {[["stt", t.sttMs], ["llm", t.llmMs], ["tts", t.ttsMs], ["sil", t.silenceMs]].map(([k, v]) => v ? (
                  <span key={k} className={`seg-${k}`} style={{ width: `${(v / peak) * 100}%` }} title={`${k.toUpperCase()} ${ms(v)}`} />
                ) : null)}
              </div>
              <span className="mono small">{ms(t.totalMs)}</span>
            </div>
          ))}
        </div>
      )}
      {total > 0 && <p className="small dim" style={{ margin: 0 }}>Estimated cost of this call: <strong>₹{total.toFixed(2)}</strong> (speech, model and voice).</p>}
    </div>
  );
}

function ProviderChip({ leg, color, name, detail, avg }) {
  return (
    <div className={`provider-chip c-${color}`}>
      <div className="tiny faint">{leg}</div>
      <div className="provider-chip-name">{name ? sentence(name.replaceAll("_", " ")) : "-"}</div>
      <div className="mono tiny ellipsis" title={detail || ""}>{detail || ""}</div>
      <div className="small"><strong>{ms(avg)}</strong> <span className="faint">average</span></div>
    </div>
  );
}

export function Metric({ label, value, unit, foot, tone }) {
  return (
    <div className={`metric ${tone === "halt" ? "halt" : ""}`}>
      <div className="eyebrow">{label}</div>
      <div className={`metric-value ${tone || ""}`}>
        {value ?? "-"}
        {unit && <span className="metric-unit">{unit}</span>}
      </div>
      {foot && <div className="tiny faint ellipsis">{foot}</div>}
    </div>
  );
}

export function Row({ label, value, tone }) {
  return (
    <div className="defrow">
      <dt>{label}</dt>
      <dd className={tone ? `tone-${tone}` : ""}>
        {tone === "ok" && <Check size={13} />}
        {tone === "halt" && <Alert size={13} />}
        {tone === "warn" && <Info size={13} />}
        <span className="mono">{value}</span>
      </dd>
    </div>
  );
}
