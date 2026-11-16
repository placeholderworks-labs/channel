import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Alert, Bot, Check, Chevron, Clock, Copy, Globe, History as HistoryIcon, Inbox, Info, Key, Pencil, Plus, Refresh, Trash, X,
} from "../components/Icons";
import { Badge, Confirm, Empty, Field, Modal, PageHeader, Skeleton, Toggle } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { clockTime, relativeTime } from "../lib/format";
import { curlFor, endpointOf, span, stateOf, triggerText, TYPE_LABELS, dedupeOf } from "../lib/qms";
import { useToast } from "../lib/toast";
import { STATUS } from "./History";

const POLL_MS = 15000;
const VIEWS = [
  { id: "all", label: "All", test: () => true },
  { id: "active", label: "Active", test: (s, on) => stateOf(s, on).live },
  { id: "setup", label: "Needs setup", test: (s, on) => s.enabled && on && !stateOf(s, on).live },
  { id: "off", label: "Off", test: (s) => !s.enabled },
];

function copy(text, toast, what) {
  navigator.clipboard?.writeText(text);
  toast.ok(`${what} copied`);
}

export default function QMS() {
  const { can } = useAuth();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [syncedAt, setSyncedAt] = useState(null);
  const [view, setView] = useState("all");
  const [editing, setEditing] = useState(null);
  const [token, setToken] = useState(null);
  const [del, setDel] = useState(null);
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(0);
  const manage = can("settings.edit");

  const load = useCallback(async () => {
    try {
      setData(await api.qms());
      setSyncedAt(new Date().toISOString());
      setTick((t) => t + 1);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const sources = data?.sources || [];
  const on = data?.enabled !== false;
  const shown = sources.filter((s) => VIEWS.find((v) => v.id === view).test(s, on));
  const selectedId = params.get("api") || shown[0]?.id || sources[0]?.id;
  const selected = sources.find((s) => s.id === selectedId);
  const select = (id) => setParams((p) => { p.set("api", id); return p; }, { replace: true });

  const remove = async () => {
    setBusy(true);
    try {
      await api.deleteIntake(del.id);
      toast.ok(`${del.name} deleted`);
      setDel(null);
      setParams((p) => { p.delete("api"); return p; }, { replace: true });
      load();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const rotate = async (intake) => {
    try {
      const r = await api.newIntakeToken(intake.id);
      setToken({ intake, token: r.token });
      load();
    } catch (e) {
      toast.error(e.message);
    }
  };

  const toggle = async (intake, enabled) => {
    try {
      await api.updateIntake(intake.id, { enabled });
      toast.ok(`${intake.name} ${enabled ? "accepting records" : "switched off"}`);
      load();
    } catch (e) {
      toast.error(e.message);
    }
  };

  return (
    <div className="page wide">
      <PageHeader
        eyebrow="Operate"
        title="QMS"
        subtitle="The APIs that ask for calls. Each one has its own endpoint, token and payload; which agent it calls, and when, is set on that agent's QMS tab."
        actions={
          <>
            <span className="tiny faint mono hide-sm">{error ? "" : syncedAt ? `synced ${clockTime(syncedAt)}` : "syncing…"}</span>
            <button className="btn btn-sm" onClick={load}><Refresh size={14} /> Refresh</button>
            {manage && <button className="btn btn-primary btn-sm" onClick={() => setEditing({ _new: true })}><Plus size={14} /> New API</button>}
          </>
        }
      />

      <div className="stack" style={{ gap: 14 }}>
        {error && <div className="notice halt"><Alert size={15} /><span>{error}</span></div>}
        {data && !data.persisted && (
          <div className="notice warn"><Info size={15} /><span>No database configured. APIs cannot be added and records are kept in memory only.</span></div>
        )}
        {data?.note && <div className="notice warn"><Alert size={15} /><span>{data.note}</span></div>}
        {data && <BaseBar data={data} />}

        {!data && !error ? (
          <div className="qms-layout"><Skeleton h={360} r={14} /><Skeleton h={520} r={14} /></div>
        ) : sources.length === 0 ? (
          <Empty icon={<Inbox size={22} />} title="No APIs yet">Create one for each system that sends customers to call.</Empty>
        ) : (
          <div className="qms-layout">
            <aside className="panel qms-list">
              <div className="qms-list-head">
                <div className="toolviews" role="tablist" aria-label="Filter APIs" style={{ margin: 0 }}>
                  {VIEWS.map((v) => (
                    <button key={v.id} type="button" role="tab" aria-selected={view === v.id}
                      className={`toolview ${view === v.id ? "on" : ""}`} onClick={() => setView(v.id)}>{v.label}</button>
                  ))}
                </div>
              </div>
              {shown.length === 0 && <div className="small faint" style={{ padding: "18px 16px" }}>Nothing here.</div>}
              {shown.map((s) => {
                const st = stateOf(s, on);
                return (
                  <button key={s.id} type="button" className={`qms-item ${s.id === selected?.id ? "on" : ""}`} onClick={() => select(s.id)}>
                    <span className={`lamp ${st.live ? "on" : ""}`} />
                    <span className="qms-item-main">
                      <span className="qms-item-name ellipsis">{s.name}</span>
                      <span className="mono tiny faint ellipsis">{s.path}</span>
                      <span className="tiny ellipsis qms-item-agent">
                        <Bot size={11} /> {s.agent ? (s.agentName || s.agent) : <span className="faint">no agent connected</span>}
                      </span>
                    </span>
                    <span className="qms-item-side">
                      <Badge tone={st.tone} dot>{st.label}</Badge>
                      <span className="tiny faint">{s.counts?.lastAt ? relativeTime(s.counts.lastAt) : "no data yet"}</span>
                    </span>
                  </button>
                );
              })}
            </aside>

            {selected && (
              <IntakeDetail key={selected.id} s={selected} base={data.baseUrl} on={on} manage={manage} tick={tick} onReload={load}
                onEdit={() => setEditing(selected)} onDelete={() => setDel(selected)}
                onToken={() => rotate(selected)} onToggle={(v) => toggle(selected, v)} />
            )}
          </div>
        )}
      </div>

      {editing && (
        <IntakeEditor intake={editing} fieldTypes={data?.fieldTypes || Object.keys(TYPE_LABELS)}
          onClose={() => setEditing(null)}
          onSaved={(saved, newToken) => {
            setEditing(null);
            load();
            select(saved.id);
            if (newToken) setToken({ intake: saved, token: newToken });
          }} />
      )}
      {token && <TokenDialog info={token} base={data?.baseUrl} onClose={() => setToken(null)} />}
      <Confirm open={!!del} danger busy={busy} title={`Delete ${del?.name}?`} confirmLabel="Delete API"
        body="Its endpoint stops accepting records straight away. Records it already sent stay in History."
        onConfirm={remove} onClose={() => setDel(null)} />
    </div>
  );
}

function BaseBar({ data }) {
  const toast = useToast();
  const { can } = useAuth();
  const base = data.baseUrl || window.location.origin;
  const from = data.baseUrlFrom === "setting" ? "Settings → QMS" : data.baseUrlFrom === "derived" ? "the public WebSocket address" : "";
  return (
    <div className="qms-base">
      <span className="qms-base-icon"><Globe size={16} /></span>
      <div className="qms-base-text">
        <span className="eyebrow">Base URL</span>
        <code className="mono">{base}</code>
        <span className="tiny faint">
          {from ? `From ${from}. Every endpoint below is this plus its path.` : "Not set, so this is the address you opened the console on. Set the public one in Settings → QMS before sharing an endpoint."}
        </span>
      </div>
      <div className="row" style={{ gap: 6 }}>
        {!data.enabled && <Badge tone="halt" dot>QMS switched off</Badge>}
        <button className="btn btn-ghost btn-sm" onClick={() => copy(base, toast, "Base URL")}><Copy size={13} /> Copy</button>
        {can("settings.view") && <Link className="btn btn-sm" to="/settings?group=ingestion">{data.baseUrlFrom === "setting" ? "Change" : "Set it"}</Link>}
      </div>
    </div>
  );
}

const TABS = [
  { id: "data", label: "Received data" },
  { id: "payload", label: "Payload" },
  { id: "api", label: "Endpoint & curl" },
  { id: "response", label: "Response" },
];

function IntakeDetail({ s, base, on, manage, tick, onReload, onEdit, onDelete, onToken, onToggle }) {
  const toast = useToast();
  const { can } = useAuth();
  const [tab, setTab] = useState("data");
  const st = stateOf(s, on);
  const url = endpointOf(s, base);
  const counts = s.counts;

  return (
    <section className="panel qms-detail">
      <div className="qms-detail-head">
        <span className="qms-icon"><Inbox size={18} /></span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 className="row" style={{ gap: 8, flexWrap: "wrap", margin: 0 }}>
            {s.name}
            <Badge tone={st.tone} dot>{st.label}</Badge>
            {s.builtin && <Badge>built in</Badge>}
          </h3>
          {s.description && <p className="small dim" style={{ margin: "4px 0 0" }}>{s.description}</p>}
        </div>
        <div className="row qms-detail-actions">
          {manage && <Toggle size="sm" checked={s.enabled} onChange={onToggle} label="Accept records" />}
          {manage && <button className="btn btn-sm" onClick={onEdit}><Pencil size={13} /> Edit</button>}
          {manage && !s.builtin && <button className="btn btn-ghost btn-icon btn-sm" onClick={onDelete} aria-label="Delete API"><Trash size={14} /></button>}
        </div>
      </div>

      <div className="qms-facts">
        <div className="qms-fact span-2">
          <span className="eyebrow">Endpoint</span>
          <div className="row" style={{ gap: 6, minWidth: 0 }}>
            <span className="method">POST</span>
            <code className="mono ellipsis grow" title={url}>{url}</code>
            <button className="btn btn-ghost btn-icon btn-sm" aria-label="Copy endpoint" onClick={() => copy(url, toast, "Endpoint")}><Copy size={13} /></button>
          </div>
        </div>
        <div className="qms-fact">
          <span className="eyebrow">Token</span>
          <div className="row" style={{ gap: 6 }}>
            {s.tokenSet
              ? <span className="mono small">{s.tokenHint ? `qms_…${s.tokenHint}` : "legacy shared token"}</span>
              : <Badge tone="halt" dot>none, refusing every request</Badge>}
            {manage && <button className="btn btn-ghost btn-sm" onClick={onToken}><Key size={12} /> {s.tokenSet ? "Replace" : "Create"}</button>}
          </div>
        </div>
        <div className="qms-fact">
          <span className="eyebrow">Agent it calls</span>
          {s.agent ? (
            <Link to={`/agents/${s.agent}?tab=qms`} className="row small" style={{ gap: 6, fontWeight: 650 }}>
              <Bot size={13} /> {s.agentName || s.agent}
              {s.agentReady === false && <Badge tone="warn">not live on {s.channel}</Badge>}
            </Link>
          ) : (
            <span className="small">None yet. <Link to="/agents">Open an agent</Link> → QMS tab to connect it.</span>
          )}
        </div>
        <div className="qms-fact span-2">
          <span className="eyebrow">When it calls</span>
          <span className="small"><Clock size={12} /> {triggerText(s)}. A record's <span className="mono">scheduled_at</span> wins. Same number or reference within {span(dedupeOf(s))} is a duplicate.</span>
        </div>
      </div>

      <div className="qms-stats">
        <Stat label="Received" value={counts?.received} sub="last 24h" />
        <Stat label="Calls placed" value={counts?.triggered} sub="last 24h" tone="ok" />
        <Stat label="Rejected" value={counts?.rejected} sub="bad data" tone={counts?.rejected ? "halt" : ""} />
        <Stat label="Trigger pending" value={counts?.awaiting} sub="held" tone={counts?.awaiting ? "warn" : ""} />
      </div>

      {counts?.awaiting > 0 && <Held s={s} count={counts.awaiting} canRelease={can("calls.place")} onDone={onReload} />}

      <div className="qms-tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} className={`qms-tab ${tab === t.id ? "on" : ""}`} onClick={() => setTab(t.id)}>
            {t.label}{t.id === "payload" && <span className="qms-tab-n">{s.allFields.length}</span>}
          </button>
        ))}
      </div>

      <div className="qms-pane">
        {tab === "data" && <Received s={s} tick={tick} />}
        {tab === "payload" && <Payload s={s} />}
        {tab === "api" && <ApiTab s={s} url={url} base={base} manage={manage} onToken={onToken} />}
        {tab === "response" && <ResponseTab s={s} />}
      </div>
    </section>
  );
}

function Held({ s, count, canRelease, onDone }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const live = s.agent && s.agentReady !== false;
  const n = `${count} valid record${count === 1 ? "" : "s"}`;
  const release = async () => {
    setBusy(true);
    try {
      const r = await api.releaseIntake(s.id);
      toast.ok(`${r.released} queued for calling${r.duplicate ? ` · ${r.duplicate} duplicate` : ""}${r.rejected ? ` · ${r.rejected} no longer valid` : ""}`);
      onDone?.();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="qms-held">
      <Clock size={16} />
      <span>
        {!s.agent
          ? <><strong>{n} waiting for an agent.</strong> Connect one from the agent's QMS tab and choose whether to call them.</>
          : !live
            ? <><strong>{n} waiting.</strong> They are called once {s.agentName || s.agent} is live on {s.channel}, if that was chosen when connecting.</>
            : <><strong>{n} waiting to be called.</strong> They go to {s.agentName || s.agent} on its schedule, spaced out.</>}
      </span>
      {live && canRelease && <button className="btn btn-primary btn-sm" disabled={busy} onClick={release}>{busy ? "Queueing…" : `Call ${count} now`}</button>}
    </div>
  );
}

function Stat({ label, value, sub, tone }) {
  return (
    <div className={`qms-stat ${tone || ""}`}>
      <span className="qms-stat-v">{value ?? "–"}</span>
      <span className="qms-stat-l">{label}<span className="faint"> · {sub}</span></span>
    </div>
  );
}

function Received({ s, tick }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(null);

  useEffect(() => {
    api.history({ limit: 50, source: s.id })
      .then((r) => { setRows(r.events || []); setError(""); })
      .catch((e) => setError(e.message));
  }, [s.id, tick]);

  if (error) return <div className="notice halt"><Alert size={15} /><span>{error}</span></div>;
  if (!rows) return <div className="stack" style={{ gap: 8 }}>{[0, 1, 2].map((i) => <Skeleton key={i} h={46} r={10} />)}</div>;
  if (!rows.length) {
    return (
      <div className="qms-empty">
        <Inbox size={20} />
        <strong>Nothing received yet</strong>
        <span className="small faint">Every request to this endpoint shows here with exactly what was sent, valid or not.</span>
      </div>
    );
  }
  return (
    <div className="qrec-list">
      {rows.map((e) => {
        const st = STATUS[e.status] || { pill: "", label: e.status };
        const isOpen = open === e.id;
        const payload = e.payload && typeof e.payload === "object" ? e.payload : {};
        const raw = payload._raw_body !== undefined;
        return (
          <div key={e.id} className={`qrec ${isOpen ? "open" : ""}`}>
            <button type="button" className="qrec-row" onClick={() => setOpen(isOpen ? null : e.id)} aria-expanded={isOpen}>
              <span className="qrec-who">
                <strong className="ellipsis">{e.name || "-"}</strong>
                <span className="mono tiny faint">{e.phone || "no number"}</span>
              </span>
              <span className="mono small ellipsis qrec-ref">{e.referenceId || "-"}</span>
              <Badge tone={st.pill} dot>{st.label}</Badge>
              <span className="tiny faint qrec-when" title={e.receivedAt}>{relativeTime(e.receivedAt)}</span>
              <Chevron size={14} dir={isOpen ? "up" : "down"} />
            </button>
            {isOpen && (
              <div className="qrec-body">
                {(e.reason || e.errors?.length > 0) && (
                  <div className={`notice ${e.status === "rejected" || e.status === "failed" ? "halt" : "warn"}`}>
                    <Alert size={15} />
                    <span>{e.errors?.length ? e.errors.map((x) => `${x.field || "record"} ${x.error}`).join("; ") : e.reason}</span>
                  </div>
                )}
                <div className="qrec-meta">
                  <span><span className="faint">Received</span> {new Date(e.receivedAt).toLocaleString()}</span>
                  {e.scheduledFor && <span><span className="faint">Call at</span> {new Date(e.scheduledFor).toLocaleString()}</span>}
                  {e.agent && <span><span className="faint">Agent</span> {e.agent}</span>}
                  {e.sourceIp && <span><span className="faint">From</span> <span className="mono">{e.sourceIp}</span></span>}
                  <span><span className="faint">ID</span> <span className="mono">#{e.id}</span></span>
                </div>
                {raw ? (
                  <pre className="prewrap datapre">{payload._raw_body}</pre>
                ) : (
                  <div className="qrec-fields">
                    {Object.entries(payload).map(([k, v]) => {
                      const bad = e.errors?.some((x) => x.field === k);
                      return (
                        <div key={k} className={`qrec-field ${bad ? "bad" : ""}`}>
                          <span className="mono tiny faint">{k}</span>
                          <span className="small">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
                        </div>
                      );
                    })}
                    {e.errors?.filter((x) => x.field && !(x.field in payload)).map((x) => (
                      <div key={x.field} className="qrec-field bad">
                        <span className="mono tiny faint">{x.field}</span>
                        <span className="small">{x.error}</span>
                      </div>
                    ))}
                  </div>
                )}
                <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>
                  <CopyJson value={payload} />
                  <Link className="btn btn-sm" to={`/history?source=${s.id}&q=${encodeURIComponent(e.referenceId || e.phone || "")}`}><HistoryIcon size={13} /> Open in History</Link>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function CopyJson({ value }) {
  const toast = useToast();
  return <button className="btn btn-ghost btn-sm" onClick={() => copy(JSON.stringify(value, null, 2), toast, "Payload")}><Copy size={12} /> Copy JSON</button>;
}

function Payload({ s }) {
  return (
    <div className="stack" style={{ gap: 10 }}>
      <p className="hint" style={{ margin: 0 }}>
        What each record carries. Required fields must be present and valid or the record is rejected and never dialled.
        Every field is told to the agent on the call, and the Phone and Browser tests ask for exactly these.
      </p>
      <div className="table-wrap">
        <table className="table qms-fields">
          <thead><tr><th>Field</th><th>Type</th><th>Required</th><th>Rules and meaning</th></tr></thead>
          <tbody>
            {s.allFields.map((f) => (
              <tr key={f.key}>
                <td><div className="mono small" style={{ fontWeight: 650 }}>{f.key}</div><div className="tiny faint">{f.label}</div></td>
                <td className="small nowrap">{TYPE_LABELS[f.type] || f.type}</td>
                <td className="small">
                  {f.generated ? <Badge>auto</Badge>
                    : f.required ? <Badge tone="brand">required</Badge>
                      : f.required_if ? <span className="tiny">when <span className="mono">{f.required_if.field}</span> = {f.required_if.equals}</span>
                        : <span className="faint">optional</span>}
                </td>
                <td className="small">
                  {[
                    f.options && `one of ${f.options.join(", ")}`,
                    f.min !== undefined && `at least ${f.min}`,
                    f.max !== undefined && `at most ${f.max}`,
                    f.future_only && "not in the past",
                    f.description,
                  ].filter(Boolean).join(" · ") || <span className="faint">-</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ApiTab({ s, url, base, manage, onToken }) {
  const toast = useToast();
  const sample = JSON.stringify(s.samplePayload, null, 2);
  const curl = curlFor(s, base);
  return (
    <div className="stack" style={{ gap: 14 }}>
      <dl className="qms-kv">
        <dt>Method</dt><dd className="mono">POST</dd>
        <dt>URL</dt><dd className="mono break">{url}</dd>
        <dt>Headers</dt>
        <dd className="mono">
          Content-Type: application/json<br />
          X-API-Key: {s.tokenHint ? `qms_…${s.tokenHint}` : "<token>"} <span className="faint">(or Authorization: Bearer &lt;token&gt;)</span>
        </dd>
        <dt>Body</dt><dd>One record as a JSON object, or up to {s.maxBatch} as an array. <span className="mono">reference_id</span> is optional: one is generated and returned when left out.</dd>
      </dl>
      <div className="codeblock">
        <div className="codeblock-head"><span>curl</span>
          <button className="btn btn-ghost btn-sm" onClick={() => copy(curl, toast, "curl")}><Copy size={12} /> Copy</button></div>
        <pre>{curl}</pre>
      </div>
      <div className="codeblock">
        <div className="codeblock-head"><span>Smallest valid body</span>
          <button className="btn btn-ghost btn-sm" onClick={() => copy(sample, toast, "Body")}><Copy size={12} /> Copy</button></div>
        <pre>{sample}</pre>
      </div>
      <p className="hint" style={{ margin: 0 }}>
        The token is shown once, when it is created or replaced. {manage && <button className="auth-link" onClick={onToken}><Key size={11} /> {s.tokenSet ? "Replace the token" : "Create a token"}</button>}
      </p>
    </div>
  );
}

const CODES = [
  ["202", "At least one record was queued, held as trigger pending (no live agent yet), or was a duplicate."],
  ["422", "Nothing was queued: every record had missing or invalid fields, or the body was not JSON."],
  ["401", "Missing or wrong token."],
  ["404", "No API with this path."],
  ["503", "The API, QMS or the dialer is switched off."],
];

function ResponseTab({ s }) {
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="table-wrap">
        <table className="table">
          <tbody>
            {CODES.map(([code, text]) => <tr key={code}><td className="mono" style={{ fontWeight: 700, width: 70 }}>{code}</td><td className="small">{text}</td></tr>)}
          </tbody>
        </table>
      </div>
      <p className="hint" style={{ margin: 0 }}>Each record gets its own result with an <span className="mono">ingestion_id</span> and its <span className="mono">reference_id</span>, so a batch can be matched line by line.</p>
      <div className="qms-two">
        <div className="codeblock"><div className="codeblock-head"><span><Check size={12} /> Accepted · 202</span></div><pre>{JSON.stringify(s.sampleResponse, null, 2)}</pre></div>
        <div className="codeblock"><div className="codeblock-head"><span><X size={12} /> Rejected · 422</span></div><pre>{JSON.stringify(s.sampleRejection, null, 2)}</pre></div>
      </div>
    </div>
  );
}

const BLANK_FIELD = { key: "", label: "", type: "text", required: true, description: "", example: "" };

function IntakeEditor({ intake, fieldTypes, onClose, onSaved }) {
  const toast = useToast();
  const isNew = !!intake._new;
  const locked = intake.kind === "cart";
  const [draft, setDraft] = useState(() => ({
    id: intake.id || "", name: intake.name || "", description: intake.description || "",
    channel: intake.channel || "acefone", enabled: intake.enabled !== false,
    fields: (intake.fields || []).map((f) => ({ ...BLANK_FIELD, ...f, options: (f.options || []).join(", ") })),
  }));
  const [open, setOpen] = useState(null);
  const [busy, setBusy] = useState(false);

  const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }));
  const setField = (i, k, v) => setDraft((d) => ({ ...d, fields: d.fields.map((f, j) => (j === i ? { ...f, [k]: v } : f)) }));
  const keys = draft.fields.map((f) => f.key).filter(Boolean);
  const idOk = !isNew || /^[a-z][a-z0-9_]{2,40}$/.test(draft.id);
  const valid = idOk && draft.name.trim() && draft.fields.every((f) => /^[a-z][a-z0-9_]{1,40}$/.test(f.key) && (f.type !== "enum" || f.options.trim()));
  const path = useMemo(() => (intake.path || `/api/qms/${draft.id || "<identifier>"}/calls`), [intake.path, draft.id]);

  const save = async () => {
    setBusy(true);
    const payload = {
      ...draft,
      fields: draft.fields.map((f) => ({
        ...f,
        options: f.type === "enum" ? f.options.split(",").map((o) => o.trim()).filter(Boolean) : undefined,
        min: f.min === "" ? undefined : f.min,
        max: f.max === "" ? undefined : f.max,
        example: f.example === "" ? undefined : f.example,
        required_if: f.required_if?.field && f.required_if?.equals ? f.required_if : undefined,
      })),
    };
    try {
      if (isNew) {
        const r = await api.createIntake(payload);
        toast.ok(`${r.intake.name} created`);
        onSaved(r.intake, r.token);
      } else {
        const r = await api.updateIntake(intake.id, payload);
        toast.ok(`${r.name} saved`);
        onSaved(r, null);
      }
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open title={isNew ? "New QMS API" : `Edit ${intake.name}`} onClose={onClose} width={900}
      subtitle="The endpoint and the payload it accepts. Connect it to an agent afterwards, from that agent's QMS tab."
      footer={<>
        <span className="row" style={{ gap: 8, marginRight: "auto" }}>
          <Toggle checked={draft.enabled} onChange={(v) => set("enabled", v)} label="Accept records" />
          <span className="small">{draft.enabled ? "Accepting records" : "Switched off"}</span>
        </span>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={save} disabled={busy || !valid}>{busy ? "Saving…" : isNew ? "Create API" : "Save API"}</button>
      </>}>
      <div className="form-grid">
        <Field label="Name" required><input className="input" value={draft.name} onChange={(e) => set("name", e.target.value)} placeholder="Demo request API" /></Field>
        <Field label="Identifier" required hint={<>Endpoint: <span className="mono">{path}</span>{!isNew && " · fixed once created"}</>}
          error={draft.id && !idOk ? "3 to 41 lowercase letters, digits or underscores" : ""}>
          <input className="input mono" value={draft.id} disabled={!isNew} placeholder="demo_requests"
            onChange={(e) => set("id", e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"))} />
        </Field>
        <Field label="What it is for" className="span-2">
          <input className="input" value={draft.description} onChange={(e) => set("description", e.target.value)} placeholder="People who asked for a demo on placeholderworks.com." />
        </Field>
      </div>

      <div className="stack" style={{ gap: 10, marginTop: 6 }}>
        <div className="eyebrow">Payload fields</div>
        <div className="notice"><Info size={15} /><span>
          Always included: <span className="mono">customer_name</span> and <span className="mono">phone_number</span> (required), <span className="mono">reference_id</span> (generated when left out), and optional <span className="mono">scheduled_at</span> and <span className="mono">language</span>. Add what else this API sends.
        </span></div>
        {locked ? (
          <div className="notice warn"><Alert size={15} /><span>The Abandoned cart fields feed the cart tools (cart details, discount, booking link), so they are fixed.</span></div>
        ) : (
          <>
            {draft.fields.length === 0 && <p className="hint" style={{ margin: 0 }}>No fields of its own yet.</p>}
            {draft.fields.map((f, i) => (
              <div key={i} className="intake-field">
                <div className="intake-field-row">
                  <input className="input mono" placeholder="key" value={f.key} onChange={(e) => setField(i, "key", e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"))} />
                  <input className="input" placeholder="Label" value={f.label} onChange={(e) => setField(i, "label", e.target.value)} />
                  <select className="input select" value={f.type} onChange={(e) => setField(i, "type", e.target.value)}>
                    {fieldTypes.map((t) => <option key={t} value={t}>{TYPE_LABELS[t] || t}</option>)}
                  </select>
                  <span className="row" style={{ gap: 6 }}><Toggle size="sm" checked={!!f.required} onChange={(v) => setField(i, "required", v)} label="Required" /><span className="small">Required</span></span>
                  <span className="row" style={{ gap: 4, justifyContent: "flex-end" }}>
                    <button className="btn btn-ghost btn-sm" onClick={() => setOpen(open === i ? null : i)}>{open === i ? "Less" : "More"}</button>
                    <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setDraft((d) => ({ ...d, fields: d.fields.filter((_, j) => j !== i) }))} aria-label="Remove field"><X size={13} /></button>
                  </span>
                </div>
                {f.type === "enum" && (
                  <input className="input" placeholder="Options, separated by commas: deluxe, suite" value={f.options} onChange={(e) => setField(i, "options", e.target.value)} />
                )}
                {open === i && (
                  <div className="form-grid" style={{ marginTop: 4 }}>
                    <Field label="What it means" className="span-2" hint="Shown in the API docs and the test forms.">
                      <input className="input" value={f.description} onChange={(e) => setField(i, "description", e.target.value)} />
                    </Field>
                    <Field label="Example value"><input className="input mono" value={f.example ?? ""} onChange={(e) => setField(i, "example", e.target.value)} /></Field>
                    <Field label="Required only when">
                      <div className="row" style={{ gap: 6 }}>
                        <select className="input select" value={f.required_if?.field || ""} onChange={(e) => setField(i, "required_if", { ...(f.required_if || {}), field: e.target.value })}>
                          <option value="">(another field)</option>
                          {keys.filter((k) => k !== f.key).map((k) => <option key={k} value={k}>{k}</option>)}
                        </select>
                        <input className="input mono" placeholder="equals" value={f.required_if?.equals || ""} onChange={(e) => setField(i, "required_if", { ...(f.required_if || {}), equals: e.target.value })} />
                      </div>
                    </Field>
                    {(f.type === "number" || f.type === "integer") && (
                      <>
                        <Field label="Minimum"><input className="input mono" type="number" value={f.min ?? ""} onChange={(e) => setField(i, "min", e.target.value)} /></Field>
                        <Field label="Maximum"><input className="input mono" type="number" value={f.max ?? ""} onChange={(e) => setField(i, "max", e.target.value)} /></Field>
                      </>
                    )}
                    {f.type === "date" && (
                      <div className="switchrow span-2"><div className="switchrow-text"><strong>Not in the past</strong><span>Reject a date before today.</span></div>
                        <Toggle checked={!!f.future_only} onChange={(v) => setField(i, "future_only", v)} label="Not in the past" /></div>
                    )}
                  </div>
                )}
              </div>
            ))}
            <button className="btn btn-sm" style={{ justifySelf: "start" }} onClick={() => setDraft((d) => ({ ...d, fields: [...d.fields, { ...BLANK_FIELD }] }))}>
              <Plus size={13} /> Add field
            </button>
          </>
        )}
      </div>
    </Modal>
  );
}

function TokenDialog({ info, base, onClose }) {
  const toast = useToast();
  const url = info.intake.path ? endpointOf(info.intake, base) : "";
  return (
    <Modal open title={`Token for ${info.intake.name}`} onClose={onClose} width={580}
      subtitle="Shown once. Give it to the team that posts to this API; it replaces any earlier token straight away."
      footer={<button className="btn btn-primary" onClick={onClose}><Check size={14} /> Done</button>}>
      <div className="notice warn"><Alert size={15} /><span>Copy it now. Only its last four characters are kept for display.</span></div>
      <div className="row" style={{ gap: 6 }}>
        <code className="codeline grow" style={{ wordBreak: "break-all" }}>{info.token}</code>
        <button className="btn btn-sm" onClick={() => copy(info.token, toast, "Token")}><Copy size={13} /> Copy</button>
      </div>
      {url && (
        <div className="row" style={{ gap: 6 }}>
          <code className="codeline grow ellipsis">POST {url}</code>
          <button className="btn btn-ghost btn-sm" onClick={() => copy(url, toast, "Endpoint")}><Copy size={13} /></button>
        </div>
      )}
      <p className="hint" style={{ margin: 0 }}>Send it as <span className="mono">X-API-Key: {"<token>"}</span> or <span className="mono">Authorization: Bearer {"<token>"}</span>.</p>
    </Modal>
  );
}
