import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  ArrowRight,
  Bot,
  Copy,
  Database,
  Globe,
  Headset,
  History as HistoryIcon,
  Inbox,
  Mic2,
  PhoneCall,
  Refresh,
  Shield,
  Users,
  Waves,
  Wrench,
} from "../components/Icons";
import { Badge, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { relativeTime, uptime } from "../lib/format";
import { useToast } from "../lib/toast";
import { endpointOf, stateOf, triggerText } from "../lib/qms";
import RequestAccess from "../components/RequestAccess";
import { channelLabel, initials } from "./UseCases";

function useCountUp(target, ms = 900) {
  const [shown, setShown] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    if (typeof target !== "number" || Number.isNaN(target)) return undefined;
    const start = performance.now();
    const begin = from.current;
    let frame;
    const tick = (now) => {
      const t = Math.min(1, (now - start) / ms);
      const eased = 1 - (1 - t) ** 3;
      setShown(Math.round(begin + (target - begin) * eased));
      if (t < 1) frame = requestAnimationFrame(tick);
      else from.current = target;
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, ms]);
  return typeof target === "number" ? shown : target;
}

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

export default function Overview({ status, reload, loading }) {
  const { user, can } = useAuth();
  const [studio, setStudio] = useState(null);
  const [guardrails, setGuardrails] = useState(null);
  const [team, setTeam] = useState(null);
  const [calls, setCalls] = useState(null);
  const [qms, setQms] = useState(null);

  useEffect(() => {
    if (can("usecases.view")) {
      Promise.all([api.usecases(), can("tools.view") ? api.tools().catch(() => null) : null])
        .then(([u, t]) => setStudio({ ...u, tools: t?.tools || [] }))
        .catch(() => setStudio({ usecases: [], tools: [], defaults: {} }));
    }
    if (can("usecases.view")) api.guardrails().then((r) => setGuardrails(r.guardrails || [])).catch(() => setGuardrails([]));
    if (can("team.view")) api.users().then((r) => setTeam(r.users || [])).catch(() => setTeam([]));
    if (can("calls.live.view")) api.calls(6).then((r) => setCalls(r.calls || [])).catch(() => setCalls([]));
    if (can("ingestion.view")) api.qms().then(setQms).catch(() => setQms({ sources: [] }));
  }, [can]);

  if (!status) {
    return (
      <div className="page wide stack-lg">
        <Skeleton h={150} r={18} />
        <div className="glass-stage"><div className="glass-grid">{[0, 1, 2, 3, 4, 5].map((i) => <GlassSkeleton key={i} />)}</div></div>
        <Skeleton h={220} r={14} />
      </div>
    );
  }

  const problems = [...findProblems(status), ...qmsProblems(qms)];
  const list = studio?.usecases || [];
  const active = list.filter((u) => u.status === "active");
  const armed = (status.channels || []).filter((c) => c.enabled);
  const firstName = user?.name ? user.name.split(" ")[0] : "";

  return (
    <div className="page wide stack-lg">
      <section className="ov-hero">
        <div className="ov-hero-text">
          <div className="ov-hero-eyebrow">PlaceholderWorks Voice Studio</div>
          <h1>
            <span>{greeting()}{firstName ? "," : ""}</span>
            <span className="nowrap">
              {firstName && <em className="serif-accent">{firstName}</em>}
            </span>
          </h1>
          <p>
            {!studio ? "" : active.length
              ? `${active.length} voice agent${active.length === 1 ? " is" : "s are"} live across ${armed.length} channel${armed.length === 1 ? "" : "s"}. `
              : "Create an agent and put it on a channel. "}
            Every agent, and ingestion pipeline in one place.
          </p>
        </div>
        <div className="ov-hero-side">
          <button className="btn btn-glass btn-icon" onClick={reload} disabled={loading} aria-label="Refresh"><Refresh size={15} /></button>
        </div>
        <HeroWave />
      </section>

      {problems.length > 0 && (
        <div className="stack" style={{ gap: 8 }}>
          {problems.map((p, i) => (
            <div key={i} className={`notice ${p.tone}`}>
              <Alert size={15} />
              <span>{p.text} {p.to && <Link to={p.to} style={{ fontWeight: 600 }}>{p.action}</Link>}</span>
            </div>
          ))}
        </div>
      )}

      <GlassStats status={status} studio={studio} guardrails={guardrails} team={team} can={can} armed={armed} />

      <section className="panel">
        <div className="panel-head">
          <div style={{ flex: 1 }}>
            <h3 className="serif-title">How a <em className="serif-accent">call</em> <span className="nowrap">runs<span className="sq-dot" aria-hidden="true" /></span></h3>
            <p>Every step below is configured from this dashboard. Click one to change it.</p>
          </div>
        </div>
        <div className="panel-body" style={{ padding: "26px 16px 22px" }}>
          <div className="flow">
            <FlowStep icon={<Inbox size={22} />} title="1 · Trigger" to="/qms" link="QMS"
              sub="A record posted to a QMS API, or a test" />
            <FlowStep icon={<Bot size={22} />} title="2 · Agent" to="/agents" link="Agents"
              sub="Prompt, persona, greeting, language" />
            <FlowStep icon={<Shield size={22} />} title="3 · Guardrails" to="/guardrails" link="Guardrails"
              sub="Scope, blocked topics, banned phrases, PII" />
            <FlowStep icon={<Wrench size={22} />} title="4 · Tools" to="/tools" link="Tools"
              sub="Transfer, cart, booking link, your APIs" />
            <FlowStep icon={<Mic2 size={22} />} title="5 · Voice & model" to="/settings" link="Settings"
              sub={`${status.stack?.stt?.provider} → LLM → ${status.stack?.tts?.provider}`} />
            <FlowStep icon={<PhoneCall size={22} />} title="6 · Channel" to="/live-calls" link="Live calls"
              sub={(status.channels || []).map((c) => c.name).join(" · ")} />
          </div>
        </div>
      </section>

      <div className="ov-grid">
        <div className="ov-col">
          <section className="panel ov-a">
            <div className="panel-head">
              <div style={{ flex: 1 }}><h3>Agents</h3><p>Agents, the channels they run on and which one each channel uses by default.</p></div>
              <Link className="btn btn-sm" to="/agents">View all</Link>
            </div>
            {!studio ? <div className="panel-body"><Skeleton h={120} /></div> : list.length === 0 ? (
              <div className="panel-body small dim">No agents yet.</div>
            ) : list.slice(0, 6).map((u) => (
              <Link key={u.slug} to={`/agents/${u.slug}`} className="list-row" style={{ padding: "12px 20px" }}>
                <span className={`uc-icon ${u.status}`} style={{ width: 34, height: 34, fontSize: 12.5, borderRadius: 10 }}>{initials(u.name)}</span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ fontWeight: 650, display: "block" }} className="ellipsis">{u.name}</span>
                  <span className="tiny faint">{(u.channels || []).map(channelLabel).join(" · ")} · {(u.tools || []).length} tools · v{u.version}</span>
                </span>
                {Object.entries(studio.defaults || {}).filter(([, s]) => s === u.slug).map(([c]) => <Badge key={c} tone="brand">default · {c}</Badge>)}
                <Badge tone={u.status === "active" ? "ok" : u.status === "draft" ? "warn" : ""} dot>{u.status}</Badge>
              </Link>
            ))}
          </section>

          {calls && (
            <section className="panel ov-r">
              <div className="panel-head">
                <div style={{ flex: 1 }}><h3>Recent calls</h3><p>The last dial attempts, from QMS or a test.</p></div>
                <Link className="btn btn-sm" to="/history"><HistoryIcon size={13} /> History</Link>
              </div>
              {calls.length === 0 ? <div className="panel-body small dim">No calls yet.</div> : (
                <div className="table-wrap">
                  <table className="table">
                    <tbody>
                      {calls.map((c) => (
                        <tr key={c.id}>
                          <td><div style={{ fontWeight: 600 }}>{c.name || "-"}</div><div className="mono tiny faint">{c.phone}</div></td>
                          <td className="mono small">{c.referenceId}</td>
                          <td><Badge tone={c.error ? "halt" : c.endedAt ? "" : "ok"} dot>{c.error ? "failed" : c.status}</Badge></td>
                          <td className="small faint" style={{ textAlign: "right" }}>{relativeTime(c.createdAt)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
        </div>

        <div className="ov-col">
          <section className="panel ov-h">
            <div className="panel-head"><div style={{ flex: 1 }}><h3>System health</h3><p>What the next call depends on.</p></div></div>
            <div className="health-grid">
            <Health icon={<Mic2 size={16} />} name="Speech to text" sub={`${status.stack?.stt?.provider} · ${status.stack?.stt?.model || ""}`} ok={status.stack?.stt?.ready} />
            <Health icon={<Bot size={16} />} name="Brain (pw-llm-layer)" sub={status.stack?.llm?.model} ok={status.stack?.llm?.ready} />
            <Health icon={<Waves size={16} />} name="Text to speech" sub={`${status.stack?.tts?.provider} · ${status.stack?.tts?.voice || ""}`} ok={status.stack?.tts?.ready} />
            {(status.channels || []).map((c) => (
              <Health key={c.id} icon={c.dialer ? <PhoneCall size={16} /> : <Globe size={16} />} name={c.name}
                sub={c.enabled ? (c.missing.length ? `missing ${c.missing.join(", ")}` : c.path) : "switched off"}
                ok={c.enabled && !c.missing.length} warn={c.enabled && c.missing.length > 0} />
            ))}
            <Health icon={<Database size={16} />} name="Settings database" sub={status.db?.ready ? "connected" : status.db?.error || "unreachable"} ok={status.db?.ready} />
            </div>
          </section>

          <Endpoints status={status} />
        </div>
      </div>

      {qms && <QmsPanel data={qms} agents={list} />}
    </div>
  );
}

function HeroWave() {
  return (
    <div className="ov-wave" aria-hidden="true">
      {Array.from({ length: 48 }, (_, i) => (
        <span key={i} style={{ height: 10 + Math.abs(Math.sin(i * 0.5) * 34) + (i % 4) * 3, animationDelay: `${(i % 12) * 0.08}s` }} />
      ))}
    </div>
  );
}

function GlassSkeleton() {
  return (
    <div className="glass-card is-loading" aria-hidden="true">
      <span className="gsk gsk-icon" />
      <span className="gsk gsk-label" />
      <span className="gsk gsk-value" />
      <span className="gsk gsk-row" />
    </div>
  );
}

function Glass({ to, icon, tone, label, value, chips = [], foot, loading, locked, perm, index }) {
  const shown = useCountUp(value);
  if (loading) return <GlassSkeleton />;
  const body = (
    <>
      <div className="glass-top">
        <span className={`glass-icon t-${tone}`}>{icon}</span>
        <span className="glass-label">{label}</span>
      </div>
      {locked ? (
        perm ? <RequestAccess compact perm={perm} title={label} /> : <div className="glass-locked">No access with your role</div>
      ) : (
        <>
          <div className="glass-value">{shown}</div>
          {chips.length > 0 && (
            <div className="glass-chips">
              {chips.map(([k, v, t]) => <span key={k} className={`glass-chip ${t || ""}`}><b>{v}</b> {k}</span>)}
            </div>
          )}
          {foot && <div className="glass-foot">{foot}</div>}
        </>
      )}
    </>
  );
  const style = { animationDelay: `${index * 70}ms` };
  return locked ? <div className="glass-card" style={style}>{body}</div> : <Link to={to} className="glass-card" style={style}>{body}</Link>;
}

function GlassStats({ status, studio, guardrails, team, can, armed }) {
  const agents = studio?.usecases || [];
  const live = agents.filter((u) => u.status === "active");
  const on = (ch) => live.filter((u) => (u.channels || []).includes(ch)).length;
  const tools = (studio?.tools || []).filter((t) => t.kind !== "builtin" || t.voice_eligible);
  const kinds = (k) => tools.filter((t) => t.kind === k).length;
  const lib = guardrails || [];
  const kind = (k) => lib.filter((g) => g.kind === k).length;
  const attached = new Set(agents.flatMap((u) => u.guardrails?.library || []));
  const people = team || [];
  const calls = status.calls;

  return (
    <section className="glass-stage">
      <div className="glass-grid">
        <Glass index={0} to="/agents" icon={<Bot size={18} />} tone="blue" label="Agents live"
          loading={can("usecases.view") && !studio} locked={!can("usecases.view")} perm="usecases.view"
          value={live.length}
          chips={[["on phone", on("acefone")], ["on website", on("website")], ["in total", agents.length]]} />
        <Glass index={1} to="/history" icon={<PhoneCall size={18} />} tone="green" label="Calls · last 24 hours"
          locked={!calls}
          value={calls?.last24h ?? 0}
          chips={calls ? [["failed", calls.failed24h, calls.failed24h ? "bad" : ""], ["all time", calls.total]] : []} />
        <Glass index={2} to="/tools" icon={<Wrench size={18} />} tone="amber" label="Tools available"
          loading={can("tools.view") && !studio} locked={!can("tools.view")} perm="tools.view"
          value={tools.length}
          chips={[["factory", kinds("builtin")], ["HTTP", kinds("custom")], ["MCP", kinds("mcp")]]} />
        <Glass index={3} to="/guardrails" icon={<Shield size={18} />} tone="violet" label="Guardrails"
          loading={can("usecases.view") && !guardrails} locked={!can("usecases.view")} perm="usecases.view"
          value={lib.length}
          chips={[["blocked topics", kind("blocked_topic")], ["banned phrases", kind("banned_phrase")], ["in use", attached.size]]} />
        <Glass index={4} to="/settings" icon={<Globe size={18} />} tone="teal" label="Channels live"
          value={`${armed.length}/${(status.channels || []).length}`}
          chips={(status.channels || []).map((c) => [c.name, c.enabled ? "on" : "off", c.enabled ? "" : "bad"])}
          foot={`Up ${uptime(status.app.uptimeSecs)}`} />
        <Glass index={5} to="/team" icon={<Users size={18} />} tone="rose" label="Team"
          loading={can("team.view") && !team} locked={!can("team.view")} perm="team.view"
          value={people.length}
          chips={[["active", people.filter((u) => u.isActive).length], ["admins", people.filter((u) => ["admin", "super_admin"].includes(u.role)).length]]} />
      </div>
    </section>
  );
}

function FlowStep({ icon, title, sub, to, link }) {
  return (
    <div className="flow-step">
      <div className="flow-node">{icon}</div>
      <div className="flow-title">{title}</div>
      <div className="flow-sub">{sub}</div>
      <Link className="flow-link" to={to}>{link} →</Link>
    </div>
  );
}

function Health({ icon, name, sub, ok, warn }) {
  return (
    <div className="health-row">
      <span className="health-icon">{icon}</span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <div className="health-name">{name}</div>
        <div className="health-sub ellipsis">{sub || "-"}</div>
      </span>
      <Badge tone={ok ? "ok" : warn ? "warn" : "halt"} dot>{ok ? "ready" : warn ? "incomplete" : "not ready"}</Badge>
    </div>
  );
}

function Endpoints({ status }) {
  const toast = useToast();
  const base = status.app?.publicBase || "wss://…";
  const rows = (status.channels || []).map((c) => ({ name: c.name, url: `${base}${c.path}`, on: c.enabled }));
  return (
    <section className="panel ov-e">
      <div className="panel-head"><div style={{ flex: 1 }}><h3>Channel endpoints</h3><p>Where telephony providers and the website stream audio to.</p></div></div>
      {rows.map((r) => (
        <div key={r.name} className="health-row">
          <span className={`lamp ${r.on ? "on" : ""}`} />
          <span style={{ flex: 1, minWidth: 0 }}>
            <div className="health-name">{r.name}</div>
            <div className="health-sub ellipsis">{r.url}</div>
          </span>
          <button className="btn btn-ghost btn-icon btn-sm" aria-label={`Copy ${r.name}`}
            onClick={() => { navigator.clipboard?.writeText(r.url); toast.ok(`${r.name} copied`); }}>
            <Copy size={13} />
          </button>
        </div>
      ))}
    </section>
  );
}

function findProblems(status) {
  const problems = [];
  const stack = status.stack || {};
  for (const [key, name] of [["stt", "speech-to-text"], ["llm", "brain"], ["tts", "voice"]]) {
    if (!stack[key]?.ready) {
      problems.push({ tone: "halt", text: `The ${name} side is not configured, so every call will fail.`, to: "/settings", action: "Fix it in Settings" });
    }
  }
  const armed = (status.channels || []).filter((c) => c.enabled);
  if (!armed.length) problems.push({ tone: "halt", text: "No channel is switched on, so nothing can connect.", to: "/settings", action: "Turn one on" });
  for (const c of armed) {
    if (c.missing.length) problems.push({ tone: "warn", text: `${c.name} is on but missing ${c.missing.join(", ")}.`, to: "/settings", action: "Fill it in" });
  }
  if (!status.app.publicBase && armed.some((c) => c.dialer)) {
    problems.push({ tone: "warn", text: "No public WebSocket address is set, so a dialled call has nowhere to stream audio.", to: "/settings", action: "Set it" });
  }
  if (status.db.useDb && !status.db.ready) {
    problems.push({ tone: "halt", text: `The settings database is unreachable: ${status.db.error || "unknown error"}.` });
  }
  return problems;
}

function qmsProblems(data) {
  if (!data?.sources) return [];
  const out = [];
  for (const s of data.sources.filter((x) => x.enabled)) {
    const st = stateOf(s, data.enabled !== false);
    if (st.label === "No token") out.push({ tone: "warn", text: `${s.name} has no token, so it refuses every record.`, to: `/qms?api=${s.id}`, action: "Create one" });
    if (st.label === "No agent") out.push({ tone: "warn", text: `${s.name} is not connected to an agent, so its valid records are held as trigger pending${s.counts?.awaiting ? ` (${s.counts.awaiting} now)` : ""}.`, to: "/agents", action: "Connect one" });
    if (st.label === "Agent not live") out.push({ tone: "warn", text: `${s.name} calls ${s.agentName || s.agent}, which is not live on ${s.channel}.`, to: `/agents/${s.agent}?tab=channels`, action: "Open the agent" });
  }
  if (data.sources.length && !data.baseUrlFrom) {
    out.push({ tone: "warn", text: "No public API base URL is set, so QMS endpoints show this browser's address.", to: "/settings?group=ingestion", action: "Set it" });
  }
  return out;
}

function QmsPanel({ data, agents }) {
  const toast = useToast();
  const on = data.enabled !== false;
  const sources = data.sources || [];
  const live = sources.filter((s) => stateOf(s, on).live).length;
  const base = data.baseUrl || window.location.origin;
  return (
    <section className="panel">
      <div className="panel-head ov-qms-head">
        <div style={{ flex: 1, minWidth: 220 }}>
          <h3 className="serif-title">QMS <em className="serif-accent">APIs</em></h3>
          <p>Where customers to call come from: each API, its endpoint, the agent it feeds and when that agent calls.</p>
        </div>
        <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
          <Badge tone={live ? "ok" : "warn"} dot>{live} of {sources.length} active</Badge>
          {!on && <Badge tone="halt" dot>QMS switched off</Badge>}
          <Link className="btn btn-sm" to="/qms"><Inbox size={13} /> Open QMS</Link>
        </div>
      </div>
      <div className="ov-qms-base">
        <span className="eyebrow">Base URL</span>
        <code className="mono ellipsis">{base}</code>
        <span className="tiny faint">{data.baseUrlFrom === "setting" ? "from Settings" : data.baseUrlFrom === "derived" ? "from the public WebSocket address" : "not set, showing this browser's address"}</span>
      </div>
      {sources.length === 0 ? <div className="panel-body small dim">No QMS APIs yet.</div> : (
        <div className="ov-qms-list">
          {sources.map((s) => {
            const st = stateOf(s, on);
            const url = endpointOf(s, data.baseUrl);
            const agent = agents.find((a) => a.slug === s.agent);
            return (
              <div key={s.id} className="ov-qms-row">
                <div className="ov-qms-name">
                  <span className={`lamp ${st.live ? "on" : ""}`} />
                  <span style={{ minWidth: 0 }}>
                    <Link to={`/qms?api=${s.id}`} className="health-name ellipsis" style={{ display: "block" }}>{s.name}</Link>
                    <span className="tiny faint">{(s.allFields || []).length} payload fields · {s.tokenSet ? (s.tokenHint ? `token …${s.tokenHint}` : "legacy token") : "no token"}</span>
                  </span>
                </div>
                <div className="ov-qms-url">
                  <span className="method">POST</span>
                  <code className="mono ellipsis" title={url}>{url}</code>
                  <button className="btn btn-ghost btn-icon btn-sm" aria-label={`Copy ${s.name} endpoint`}
                    onClick={() => { navigator.clipboard?.writeText(url); toast.ok("Endpoint copied"); }}><Copy size={13} /></button>
                </div>
                <div className="ov-qms-agent small">
                  <Bot size={13} />
                  {s.agent ? <Link to={`/agents/${s.agent}?tab=qms`} className="ellipsis">{agent?.name || s.agentName || s.agent}</Link> : <span className="faint">no agent</span>}
                </div>
                <div className="tiny dim ov-qms-when">{triggerText(s)}</div>
                <Badge tone={st.tone} dot>{st.label}</Badge>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
