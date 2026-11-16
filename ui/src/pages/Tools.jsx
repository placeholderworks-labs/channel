import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Alert, Bot, Boxes, Check, Globe, Pencil, PhoneCall, Play, Plug, Plus, Refresh, Search, Server, Trash, Wrench, X } from "../components/Icons";
import { Badge, Confirm, Empty, Field, Modal, PageHeader, Segmented, Select, Skeleton, Slider, Tabs, Toggle, AutoTextarea } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useToast } from "../lib/toast";

const BLANK_TOOL = {
  name: "",
  description: "",
  enabled: true,
  config: {
    kind: "http",
    method: "POST",
    url: "https://",
    headers: {},
    parameters: [],
    body_template: "",
    timeout_secs: 8,
    response_path: "",
    speak_template: "",
    wants_voice_context: false,
  },
};

const BLANK_MCP = {
  name: "",
  description: "",
  enabled: true,
  config: { kind: "mcp", url: "", transport: "auto", headers: {}, timeout_secs: 10, tools: [], enabled_tools: null, server_info: {}, synced_at: null },
};

const PARAM_TYPES = ["string", "number", "integer", "boolean"];

const KIND = {
  builtin: { label: "Factory", tone: "", icon: Boxes },
  custom: { label: "HTTP API", tone: "brand", icon: Globe },
  mcp: { label: "MCP server", tone: "violet", icon: Server },
};

export function toolTitle(name) {
  const words = name.replace(/^voice_/, "").replace(/__/g, " · ").replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function brief(text) {
  const clean = (text || "").replace(/\s+/g, " ").trim();
  return clean.length > 220 ? `${clean.slice(0, 217)}…` : clean;
}

export default function Tools() {
  const { can } = useAuth();
  const toast = useToast();
  const [tools, setTools] = useState(null);
  const [usecases, setUsecases] = useState([]);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("builtin");
  const [query, setQuery] = useState("");
  const [view, setView] = useState("all");
  const [choosing, setChoosing] = useState(false);
  const [editing, setEditing] = useState(null);
  const [detail, setDetail] = useState(null);
  const [del, setDel] = useState(null);
  const [busy, setBusy] = useState(false);
  const edit = can("tools.edit");

  const load = useCallback(async () => {
    try {
      const [t, u] = await Promise.all([api.tools(), api.usecases().catch(() => ({ usecases: [] }))]);
      setTools((t.tools || []).filter((x) => x.kind !== "builtin" || x.voice_eligible));
      setUsecases(u.usecases || []);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const usedBy = useCallback((name) => usecases.filter((u) => (u.tools || []).includes(name)), [usecases]);

  const usage = useCallback((name) => {
    const agents = usedBy(name);
    const live = agents.filter((u) => u.status === "active");
    const channels = new Set(live.flatMap((u) => u.channels || []));
    return { agents, phone: channels.has("acefone"), website: channels.has("website"), live: live.length > 0 };
  }, [usedBy]);

  const VIEWS = [
    { id: "all", label: "All", test: () => true },
    { id: "active", label: "Active", test: (t, u) => t.enabled !== false && u.live },
    { id: "phone", label: "On phone", test: (t, u) => t.enabled !== false && u.phone },
    { id: "website", label: "On website", test: (t, u) => t.enabled !== false && u.website },
    { id: "unused", label: "Not used", test: (t, u) => !u.agents.length },
    { id: "off", label: "Switched off", test: (t) => t.enabled === false },
  ];

  const inTab = useMemo(() => (tools || []).filter((t) => t.kind === tab), [tools, tab]);

  useEffect(() => { setView("all"); }, [tab]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    const test = (VIEWS.find((v) => v.id === view) || VIEWS[0]).test;
    return inTab
      .filter((t) => test(t, usage(t.name)))
      .filter((t) => !q || `${t.name} ${t.description} ${t.category} ${t.url || ""}`.toLowerCase().includes(q));
  }, [inTab, query, view, usage]);

  const counts = Object.fromEntries(["builtin", "custom", "mcp"].map((k) => [k, (tools || []).filter((t) => t.kind === k).length]));

  const openEditor = async (tool) => {
    try {
      setEditing(await api.customTool(tool.name));
    } catch (e) {
      toast.error(e.message);
    }
  };

  const switchTool = async (tool, on) => {
    try {
      if (tool.kind === "builtin") await api.switchBuiltinTool(tool.name, on);
      else await api.updateTool(tool.name, { enabled: on });
      toast.ok(`${toolTitle(tool.name)} switched ${on ? "on" : "off"} for every agent`);
      load();
    } catch (e) {
      toast.error(e.message);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await api.deleteTool(del.name);
      toast.ok(`${del.name} deleted`);
      setDel(null);
      setDetail(null);
      load();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const EMPTY = {
    builtin: ["Nothing matches", "Try another search."],
    custom: ["No HTTP API tools yet", "Point a tool at any API (booking lookups, CRM updates, offers) with Add tool above."],
    mcp: ["No MCP servers yet", "Connect a Model Context Protocol server with Add tool above. Its tools become available to the agents you give it to."],
  }[tab];

  return (
    <div className="page wide">
      <PageHeader
        eyebrow="Build"
        title="Tools"
        subtitle="Actions a voice agent can take mid-call: factory tools that ship with the platform, your own HTTP APIs, and MCP servers. Give them to agents on each agent's Tools tab."
        actions={
          <>
            <button className="btn btn-sm" onClick={load}><Refresh size={14} /> Refresh</button>
            {edit && <button className="btn btn-primary btn-sm" onClick={() => setChoosing(true)}><Plus size={14} /> Add tool</button>}
          </>
        }
      />

      {error && <div className="notice halt" style={{ marginBottom: 16 }}><Alert size={15} /><span>{error}</span></div>}

      <div className="row" style={{ gap: 12, flexWrap: "wrap", alignItems: "center", marginBottom: 4 }}>
        <Tabs value={tab} onChange={setTab} tabs={[
          { id: "builtin", label: "Factory tools", badge: counts.builtin },
          { id: "custom", label: "HTTP APIs", badge: counts.custom },
          { id: "mcp", label: "MCP servers", badge: counts.mcp },
        ]} />
        <span className="grow" />
        <div className="searchbar" style={{ maxWidth: 300, marginBottom: 16 }}>
          <Search size={15} />
          <input className="searchinput" placeholder="Search tools" value={query} onChange={(e) => setQuery(e.target.value)} />
          {query && <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setQuery("")} aria-label="Clear"><X size={13} /></button>}
        </div>
      </div>

      {tools && (
        <div className="toolviews" role="tablist" aria-label="Filter tools">
          {VIEWS.map((v) => (
            <button key={v.id} type="button" role="tab" aria-selected={view === v.id}
              className={`toolview ${view === v.id ? "on" : ""} v-${v.id}`} onClick={() => setView(v.id)}>
              {v.label}
            </button>
          ))}
        </div>
      )}

      {!tools && !error ? (
        <div className="toolgrid">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} h={150} r={14} />)}</div>
      ) : shown.length === 0 ? (
        <div className="card"><Empty icon={<Wrench size={20} />} title={EMPTY[0]}>{EMPTY[1]}</Empty></div>
      ) : (
        <div className="toolgrid">
          {shown.map((t, i) => (
            <ToolCard key={t.name} tool={t} index={i} users={usedBy(t.name)} usage={usage(t.name)} canEdit={edit}
              onOpen={() => setDetail(t.name)} onSwitch={(on) => switchTool(t, on)} />
          ))}
        </div>
      )}

      {choosing && (
        <AddToolChooser onClose={() => setChoosing(false)}
          onPick={(kind) => { setChoosing(false); setEditing({ ...structuredClone(kind === "mcp" ? BLANK_MCP : BLANK_TOOL), _new: true }); }} />
      )}

      {detail && (tools || []).find((t) => t.name === detail) && (
        <ToolDetail tool={tools.find((t) => t.name === detail)} users={usedBy(detail)} canEdit={edit}
          onClose={() => setDetail(null)} onChanged={load}
          onEdit={(t) => openEditor(t)} onDelete={(t) => setDel({ ...t, users: usedBy(t.name) })}
          onSwitch={(on) => switchTool(tools.find((t) => t.name === detail), on)} />
      )}

      {editing && (editing.config?.kind === "mcp"
        ? <McpEditor tool={editing} onClose={() => setEditing(null)} onSaved={(name) => { setEditing(null); setTab("mcp"); load(); if (name) setDetail(name); }} />
        : <ToolEditor tool={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); setTab("custom"); load(); }} />)}

      <Confirm open={!!del} danger busy={busy} title={`Delete ${del?.name}?`} confirmLabel="Delete"
        body={del?.users?.length
          ? <>It's switched on in <strong>{del.users.map((u) => u.name).join(", ")}</strong>. Remove it there first. The brain refuses to delete a tool still in use.</>
          : "Agents lose access to it immediately. This can't be undone."}
        onConfirm={remove} onClose={() => setDel(null)} />
    </div>
  );
}

function ToolCard({ tool: t, index, users, usage, canEdit, onOpen, onSwitch }) {
  const kind = KIND[t.kind] || KIND.builtin;
  const Icon = kind.icon;
  const on = t.enabled !== false;
  const exposed = t.kind === "mcp" ? (t.tools || []).filter((x) => x.exposed).length : 0;
  return (
    <div className={`toolcard ${on ? "" : "off"}`} style={{ animationDelay: `${Math.min(index, 12) * 30}ms` }}
      role="button" tabIndex={0} onClick={onOpen} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onOpen()}>
      <div className="toolcard-top">
        <span className={`toolcard-icon k-${t.kind}`}><Icon size={18} /></span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="toolcard-title ellipsis">{toolTitle(t.name)}</div>
          <div className="toolcard-name mono ellipsis">{t.name}</div>
        </div>
        <span onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
          <Toggle size="sm" checked={on} disabled={!canEdit} onChange={onSwitch} label={`${on ? "Switch off" : "Switch on"} ${t.name}`} />
        </span>
      </div>
      <p className="toolcard-desc">{brief(t.description) || <span className="faint">No description</span>}</p>
      <div className="toolcard-use">
        <span className={`usechip ${on && usage.phone ? "on" : ""}`} title="Used by an active phone agent"><PhoneCall size={12} /> Phone</span>
        <span className={`usechip ${on && usage.website ? "on" : ""}`} title="Used by an active website agent"><Globe size={12} /> Website</span>
        <span className="toolcard-agents ellipsis" title={users.map((u) => u.name).join(", ")}>
          {users.length ? users.map((u) => u.name).join(", ") : "No agent uses it"}
        </span>
      </div>
      <div className="toolcard-foot">
        <Badge tone={kind.tone}>{kind.label}</Badge>
        {t.kind === "builtin" && t.category && <span className="tiny faint">{t.category}</span>}
        {t.kind === "mcp" && <span className="tiny faint">{exposed} of {(t.tools || []).length} tools exposed</span>}
        {!on && <Badge tone="warn">off for every agent</Badge>}
        <span className="grow" />
        <span className={`tiny row live-dot ${on && usage.live ? "is-live" : ""}`} style={{ gap: 5 }}>
          <i />{!on ? "off" : usage.live ? "active" : users.length ? "draft agents only" : "idle"}
        </span>
      </div>
    </div>
  );
}

function AddToolChooser({ onClose, onPick }) {
  const options = [
    { kind: "custom", icon: Globe, title: "HTTP API", text: "Call any REST endpoint: a booking lookup, a CRM update, an offer service. You define the request, the parameters the model fills, and what it reads back." },
    { kind: "mcp", icon: Server, title: "MCP server", text: "Connect a Model Context Protocol server by its URL. Its tools are discovered automatically, and you choose which ones agents may use." },
  ];
  return (
    <Modal open title="Add a tool" subtitle="Choose how this tool reaches the outside world." onClose={onClose} width={640}
      footer={<button className="btn btn-ghost" onClick={onClose}>Cancel</button>}>
      <div className="choosegrid">
        {options.map((o) => (
          <button key={o.kind} type="button" className="choosecard" onClick={() => onPick(o.kind)}>
            <span className={`toolcard-icon k-${o.kind}`}><o.icon size={20} /></span>
            <strong>{o.title}</strong>
            <span>{o.text}</span>
          </button>
        ))}
      </div>
    </Modal>
  );
}

function ParamTable({ params }) {
  if (!params?.length) return <p className="hint" style={{ margin: 0 }}>No parameters. The model calls it with no arguments.</p>;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead><tr><th>Parameter</th><th>Type</th><th>Required</th><th>What the model puts here</th></tr></thead>
        <tbody>
          {params.map((p) => (
            <tr key={p.name}>
              <td className="mono small">{p.name}</td>
              <td className="small dim">{p.type}</td>
              <td className="small">{p.required ? <Check size={13} /> : <span className="faint">optional</span>}</td>
              <td className="small">{p.description || <span className="faint">-</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ToolDetail({ tool, users, canEdit, onClose, onChanged, onEdit, onDelete, onSwitch }) {
  const toast = useToast();
  const kind = KIND[tool.kind] || KIND.builtin;
  const Icon = kind.icon;
  const [tab, setTab] = useState("overview");
  const [full, setFull] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const isCustom = tool.kind !== "builtin";

  useEffect(() => {
    if (isCustom) api.customTool(tool.name).then(setFull).catch(() => setFull(null));
  }, [tool.name, isCustom, tool]);

  const sync = async () => {
    setSyncing(true);
    try {
      await api.syncMcp(tool.name);
      toast.ok("Tool list refreshed from the server");
      onChanged();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSyncing(false);
    }
  };

  const setExposed = async (name, on) => {
    const all = (tool.tools || []).map((t) => t.name);
    const current = new Set((tool.tools || []).filter((t) => t.exposed).map((t) => t.name));
    if (on) current.add(name); else current.delete(name);
    const enabled_tools = current.size === all.length ? null : all.filter((n) => current.has(n));
    try {
      await api.updateTool(tool.name, { config: { enabled_tools } });
      onChanged();
    } catch (e) {
      toast.error(e.message);
    }
  };

  const c = full?.config || {};
  const tabs = [
    { id: "overview", label: "Overview" },
    ...(tool.kind === "mcp" ? [{ id: "tools", label: "Server tools", badge: (tool.tools || []).length }] : [{ id: "params", label: "Parameters", badge: (tool.parameters || []).length }]),
    ...(isCustom && canEdit ? [{ id: "test", label: "Test" }] : []),
    { id: "agents", label: "Agents", badge: users.length },
  ];

  return (
    <Modal open onClose={onClose} width={820}
      title={<span className="row" style={{ gap: 10 }}><span className={`toolcard-icon k-${tool.kind}`}><Icon size={18} /></span>{toolTitle(tool.name)}</span>}
      subtitle={<span className="mono">{tool.name}</span>}
      footer={<>
        <span className="row" style={{ gap: 8, marginRight: "auto" }}>
          <Toggle checked={tool.enabled !== false} disabled={!canEdit} onChange={onSwitch} label="Available to agents" />
          <span className="small">{tool.enabled !== false ? "Available to agents" : "Switched off for every agent"}</span>
        </span>
        {isCustom && canEdit && <button className="btn btn-ghost" onClick={() => onDelete(tool)}><Trash size={14} /> Delete</button>}
        {isCustom && canEdit && <button className="btn" onClick={() => onEdit(tool)}><Pencil size={14} /> Edit</button>}
        <button className="btn btn-primary" onClick={onClose}>Done</button>
      </>}>
      <div className="modal-tabs-sticky"><Tabs value={tab} onChange={setTab} tabs={tabs} /></div>

      {tab === "overview" && (
        <div className="stack-lg">
          <div>
            <div className="eyebrow">What it does</div>
            <p className="tooldetail-desc">{tool.description || <span className="faint">No description</span>}</p>
          </div>
          <dl className="deflist">
            <div className="defrow"><dt>Kind</dt><dd><Badge tone={kind.tone}>{kind.label}</Badge></dd></div>
            {tool.kind === "builtin" && <div className="defrow"><dt>Category</dt><dd>{tool.category}</dd></div>}
            {tool.kind === "builtin" && <div className="defrow"><dt>Receives call context</dt><dd>{tool.wants_voice_context ? "yes" : "no"}</dd></div>}
            {tool.kind === "custom" && <div className="defrow"><dt>Request</dt><dd className="mono small">{c.method} {c.url}</dd></div>}
            {tool.kind === "custom" && <div className="defrow"><dt>Headers</dt><dd className="mono small">{Object.keys(c.headers || {}).join(", ") || "none"}</dd></div>}
            {tool.kind === "custom" && <div className="defrow"><dt>Timeout</dt><dd>{c.timeout_secs}s</dd></div>}
            {tool.kind === "custom" && c.response_path && <div className="defrow"><dt>Reads</dt><dd className="mono small">{c.response_path}</dd></div>}
            {tool.kind === "custom" && c.speak_template && <div className="defrow"><dt>Spoken line</dt><dd>{c.speak_template}</dd></div>}
            {tool.kind === "mcp" && <div className="defrow"><dt>Server URL</dt><dd className="mono small">{tool.url}</dd></div>}
            {tool.kind === "mcp" && <div className="defrow"><dt>Transport</dt><dd>{tool.server_info?.transport || tool.transport}</dd></div>}
            {tool.kind === "mcp" && <div className="defrow"><dt>Server</dt><dd>{[tool.server_info?.name, tool.server_info?.version].filter(Boolean).join(" ") || "-"}</dd></div>}
            {tool.kind === "mcp" && <div className="defrow"><dt>Last synced</dt><dd>{tool.synced_at ? new Date(tool.synced_at).toLocaleString() : "never"}</dd></div>}
          </dl>
          {tool.kind === "mcp" && tool.server_info?.instructions && <Instructions text={tool.server_info.instructions} />}
          {tool.kind === "mcp" && (
            <p className="hint" style={{ margin: 0 }}>
              The model sees each exposed tool as <span className="mono">{tool.name}__&lt;tool&gt;</span>, so two servers can offer tools with the same name.
            </p>
          )}
        </div>
      )}

      {tab === "params" && <ParamTable params={tool.parameters} />}

      {tab === "tools" && (
        <div className="stack" style={{ gap: 8 }}>
          <div className="row" style={{ gap: 8 }}>
            <span className="hint" style={{ margin: 0, flex: 1 }}>Switch off any tool you don't want agents to use. New tools found on sync stay off until switched on, unless every tool is exposed.</span>
            {canEdit && <button className="btn btn-sm" onClick={sync} disabled={syncing}><Refresh size={13} /> {syncing ? "Syncing…" : "Sync from server"}</button>}
          </div>
          {(tool.tools || []).length === 0 && <div className="notice warn"><Alert size={15} /><span>The server listed no tools at the last sync.</span></div>}
          {(tool.tools || []).map((t) => <McpToolRow key={t.name} tool={t} canEdit={canEdit} onToggle={(on) => setExposed(t.name, on)} />)}
        </div>
      )}

      {tab === "test" && <ToolTester tool={tool} full={full} />}

      {tab === "agents" && (
        users.length === 0 ? <p className="hint" style={{ margin: 0 }}>No agent has this tool switched on. Give it to an agent on that agent's Tools tab.</p> : (
          <div className="stack" style={{ gap: 8 }}>
            {users.map((u) => (
              <Link key={u.slug} to={`/agents/${u.slug}`} className="toolrow on" style={{ textDecoration: "none" }}>
                <span className="toolrow-icon"><Bot size={15} /></span>
                <div style={{ minWidth: 0 }}><div style={{ fontWeight: 650 }}>{u.name}</div><div className="toolrow-desc mono">{u.slug}</div></div>
                <Badge tone={u.status === "active" ? "ok" : "warn"}>{u.status}</Badge>
              </Link>
            ))}
          </div>
        )
      )}
    </Modal>
  );
}

function Instructions({ text }) {
  const [open, setOpen] = useState(false);
  const long = text.length > 280;
  return (
    <div>
      <div className="eyebrow">Server instructions</div>
      <p className={`tooldetail-desc small ${long && !open ? "clamped" : ""}`}>{text}</p>
      {long && <button type="button" className="auth-link" onClick={() => setOpen((v) => !v)}>{open ? "Show less" : "Show all"}</button>}
    </div>
  );
}

function McpToolRow({ tool, canEdit, onToggle }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`toolrow ${tool.exposed ? "on" : ""}`} style={{ alignItems: "flex-start" }}>
      <span className="toolrow-icon"><Plug size={15} /></span>
      <div style={{ minWidth: 0 }}>
        <div className="row" style={{ gap: 8 }}>
          <span className="toolrow-name">{tool.name}</span>
          <button type="button" className="auth-link" onClick={() => setOpen((v) => !v)}>{open ? "Hide details" : `${tool.parameters.length} parameter${tool.parameters.length === 1 ? "" : "s"}`}</button>
        </div>
        <div className="toolrow-desc">{tool.description || "No description"}</div>
        {open && <div style={{ marginTop: 8 }}><ParamTable params={tool.parameters} /></div>}
      </div>
      <Toggle checked={tool.exposed} disabled={!canEdit} onChange={onToggle} label={`Expose ${tool.name}`} />
    </div>
  );
}

function ToolTester({ tool, full }) {
  const isMcp = tool.kind === "mcp";
  const choices = isMcp ? tool.tools || [] : [];
  const [target, setTarget] = useState(choices[0]?.name || "");
  const params = isMcp ? choices.find((t) => t.name === target)?.parameters || [] : tool.parameters || [];
  const [args, setArgs] = useState({});
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);

  const run = async () => {
    setRunning(true);
    setResult(null);
    try {
      setResult(await api.testTool(tool.name, args, isMcp ? target : undefined));
    } catch (e) {
      setResult({ ok: false, error: e.message });
    } finally {
      setRunning(false);
    }
  };

  const typed = (p, raw) => (p.type === "string" ? raw : raw === "" ? "" : p.type === "boolean" ? raw === "true" : Number(raw));

  return (
    <div className="stack-lg">
      <p className="hint" style={{ margin: 0 }}>Calls the {isMcp ? "server" : "endpoint"} once with these arguments, exactly as an agent would mid-call.</p>
      {isMcp && (
        <Field label="Tool">
          <Select value={target} onChange={(v) => { setTarget(v); setArgs({}); setResult(null); }} options={choices.map((t) => ({ value: t.name, label: t.name }))} />
        </Field>
      )}
      <div className="form-grid">
        {params.map((p) => (
          <Field key={p.name} label={p.name} hint={`${p.type}${p.required ? ", required" : ""}`}>
            <input className="input mono" value={args[p.name] ?? ""} onChange={(e) => setArgs({ ...args, [p.name]: typed(p, e.target.value) })} />
          </Field>
        ))}
      </div>
      <button className="btn btn-primary btn-sm" style={{ justifySelf: "start" }} onClick={run} disabled={running || (isMcp && !target) || (!isMcp && !full)}>
        <Play size={13} /> {running ? "Calling…" : "Run test"}
      </button>
      {result && (
        <div className={`notice ${result.ok ? "ok" : "halt"}`} style={{ display: "block" }}>
          <div className="row" style={{ gap: 6, marginBottom: 6 }}>
            {result.ok ? <Check size={14} /> : <Alert size={14} />}
            <strong>{result.ok ? (result.status ? `HTTP ${result.status}` : "Succeeded") : "Failed"}</strong>
          </div>
          <pre className="preview-pre" style={{ maxHeight: 260 }}>{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

function McpEditor({ tool, onClose, onSaved }) {
  const toast = useToast();
  const isNew = !!tool._new;
  const [draft, setDraft] = useState(() => {
    const t = structuredClone(tool);
    t.config = { ...BLANK_MCP.config, ...(t.config || {}) };
    return t;
  });
  const [headers, setHeaders] = useState(() => Object.entries(draft.config.headers || {}).map(([k, v]) => ({ k, v })));
  const [found, setFound] = useState(() => (isNew ? null : { server_info: draft.config.server_info, tools: draft.config.tools }));
  const [picked, setPicked] = useState(() => new Set(draft.config.enabled_tools ?? (draft.config.tools || []).map((t) => t.name)));
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState("");
  const [busy, setBusy] = useState(false);

  const c = draft.config;
  const setC = (k, v) => { setDraft((d) => ({ ...d, config: { ...d.config, [k]: v } })); if (k === "url" || k === "transport") setFound(isNew ? null : found); };
  const headerMap = () => Object.fromEntries(headers.filter((h) => h.k.trim()).map((h) => [h.k.trim(), h.v]));

  const nameOk = /^[a-z][a-z0-9_]{2,48}$/.test(draft.name);
  const urlOk = /^https?:\/\/.+/.test(c.url);
  const valid = nameOk && urlOk && draft.description.trim().length >= 10 && !!found;

  const connect = async () => {
    setConnecting(true);
    setConnectError("");
    try {
      const r = await api.discoverMcp({ url: c.url, transport: c.transport, headers: headerMap(), timeout_secs: c.timeout_secs });
      setFound(r);
      setPicked((prev) => {
        const names = r.tools.map((t) => t.name);
        const keep = names.filter((n) => prev.has(n));
        return new Set(isNew || !keep.length ? names : keep);
      });
      if (!draft.description.trim() && r.server_info?.instructions) {
        setDraft((d) => ({ ...d, description: r.server_info.instructions.slice(0, 400) }));
      }
      toast.ok(`Connected: ${r.tools.length} tool${r.tools.length === 1 ? "" : "s"} found`);
    } catch (e) {
      setFound(null);
      setConnectError(e.message);
    } finally {
      setConnecting(false);
    }
  };

  const save = async () => {
    setBusy(true);
    const names = (found?.tools || []).map((t) => t.name);
    const enabled_tools = picked.size === names.length ? null : names.filter((n) => picked.has(n));
    const payload = {
      name: draft.name,
      description: draft.description,
      enabled: draft.enabled,
      config: {
        kind: "mcp", url: c.url, transport: c.transport, headers: headerMap(), timeout_secs: c.timeout_secs,
        tools: found.tools, enabled_tools, server_info: found.server_info || {}, synced_at: new Date().toISOString(),
      },
    };
    try {
      if (isNew) await api.createTool(payload);
      else await api.updateTool(draft.name, payload);
      toast.ok(`${draft.name} saved`);
      onSaved(draft.name);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open title={isNew ? "Connect an MCP server" : `Edit ${draft.name}`} onClose={onClose} width={780}
      subtitle="Point at the server's URL, connect to discover its tools, then choose which ones agents may use."
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={save} disabled={busy || !valid} title={!found ? "Connect to the server first" : undefined}>
          {busy ? "Saving…" : isNew ? "Add MCP server" : "Save server"}
        </button>
      </>}>
      <div className="form-grid">
        <Field label="Name" required hint="Prefix for its tools, e.g. crm__find_customer." error={draft.name && !nameOk ? "3-49 chars: lowercase letters, digits, underscores" : ""}>
          <input className="input mono" value={draft.name} disabled={!isNew} placeholder="crm"
            onChange={(e) => setDraft({ ...draft, name: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })} />
        </Field>
        <Field label="Timeout">
          <Slider min={1} max={30} value={c.timeout_secs} unit="s" onChange={(v) => setC("timeout_secs", v)} />
        </Field>
        <Field label="What it is for" required className="span-2" hint="One or two sentences. Shown on the Tools page; the model reads each tool's own description.">
          <AutoTextarea minRows={2} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })}
            placeholder="Customer records from the CRM: look up a customer and their open bookings." />
        </Field>
        <Field label="Server URL" required className="span-2" error={c.url && !urlOk ? "Must start with http:// or https://" : ""}
          hint="The MCP endpoint, e.g. https://mcp.example.com/mcp, or …/sse for older servers.">
          <input className="input mono" value={c.url} onChange={(e) => setC("url", e.target.value)} placeholder="https://mcp.example.com/mcp" />
        </Field>
        <Field label="Transport" className="span-2" hint="Auto tries Streamable HTTP, then the older HTTP + SSE.">
          <Segmented size="sm" value={c.transport} onChange={(v) => setC("transport", v)}
            options={[{ value: "auto", label: "Auto" }, { value: "http", label: "Streamable HTTP" }, { value: "sse", label: "HTTP + SSE" }]} />
        </Field>
        <Field label="Headers" className="span-2" hint="For an API key or bearer token. Reference a secret as {{secret:NAME}}; it is resolved on the server, never shown here.">
          <div className="stack" style={{ gap: 6 }}>
            {headers.map((h, i) => (
              <div key={i} className="row" style={{ gap: 6 }}>
                <input className="input mono" style={{ flex: 1 }} placeholder="Authorization" value={h.k} onChange={(e) => setHeaders(headers.map((x, j) => (j === i ? { ...x, k: e.target.value } : x)))} />
                <input className="input mono" style={{ flex: 2 }} placeholder="Bearer {{secret:CRM_TOKEN}}" value={h.v} onChange={(e) => setHeaders(headers.map((x, j) => (j === i ? { ...x, v: e.target.value } : x)))} />
                <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setHeaders(headers.filter((_, j) => j !== i))} aria-label="Remove header"><X size={13} /></button>
              </div>
            ))}
            <button className="btn btn-sm" style={{ justifySelf: "start" }} onClick={() => setHeaders([...headers, { k: "", v: "" }])}><Plus size={13} /> Add header</button>
          </div>
        </Field>
      </div>

      <div className="mcp-connect">
        <div className="row" style={{ gap: 10 }}>
          <button className="btn btn-primary btn-sm" onClick={connect} disabled={connecting || !urlOk}>
            <Plug size={14} /> {connecting ? "Connecting…" : found ? "Reconnect" : "Connect"}
          </button>
          {found && <span className="small tone-ok row" style={{ gap: 6 }}><Check size={14} /> {[found.server_info?.name, found.server_info?.version].filter(Boolean).join(" ") || "Connected"}{found.server_info?.transport ? ` · ${found.server_info.transport}` : ""}</span>}
        </div>
        {connectError && <div className="notice halt" style={{ marginTop: 10 }}><Alert size={15} /><span>{connectError}</span></div>}
        {found && (
          <div className="stack" style={{ gap: 6, marginTop: 12 }}>
            <div className="eyebrow">{found.tools.length} tool{found.tools.length === 1 ? "" : "s"} on this server · {picked.size} exposed</div>
            {found.tools.map((t) => (
              <label key={t.name} className={`toolrow ${picked.has(t.name) ? "on" : ""}`} style={{ cursor: "pointer" }}>
                <span className="toolrow-icon"><Plug size={14} /></span>
                <div style={{ minWidth: 0 }}>
                  <div className="toolrow-name">{t.name}</div>
                  <div className="toolrow-desc">{t.description || "No description"}</div>
                </div>
                <Toggle checked={picked.has(t.name)} label={`Expose ${t.name}`}
                  onChange={(on) => setPicked((prev) => { const next = new Set(prev); if (on) next.add(t.name); else next.delete(t.name); return next; })} />
              </label>
            ))}
          </div>
        )}
      </div>
    </Modal>
  );
}

function ToolEditor({ tool, onClose, onSaved }) {
  const toast = useToast();
  const isNew = !!tool._new;
  const [draft, setDraft] = useState(() => {
    const t = structuredClone(tool);
    t.config = { ...BLANK_TOOL.config, ...(t.config || {}) };
    return t;
  });
  const [tab, setTab] = useState("request");
  const [busy, setBusy] = useState(false);
  const [headers, setHeaders] = useState(() => Object.entries(draft.config.headers || {}).map(([k, v]) => ({ k, v })));
  const [testArgs, setTestArgs] = useState({});
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);

  const c = draft.config;
  const setC = (k, v) => setDraft((d) => ({ ...d, config: { ...d.config, [k]: v } }));
  const setParam = (i, k, v) => setC("parameters", c.parameters.map((p, j) => (j === i ? { ...p, [k]: v } : p)));

  const nameOk = /^[a-z][a-z0-9_]{2,48}$/.test(draft.name);
  const urlOk = /^https?:\/\/.+/.test(c.url);
  const valid = nameOk && urlOk && draft.description.trim().length >= 10;

  const payload = () => ({
    name: draft.name,
    description: draft.description,
    enabled: draft.enabled,
    config: { ...c, kind: "http", headers: Object.fromEntries(headers.filter((h) => h.k.trim()).map((h) => [h.k.trim(), h.v])) },
  });

  const save = async () => {
    setBusy(true);
    try {
      if (isNew) await api.createTool(payload());
      else await api.updateTool(draft.name, payload());
      toast.ok(`${draft.name} saved`);
      onSaved();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const runTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      if (!isNew) await api.updateTool(draft.name, payload());
      setTestResult(await api.testTool(draft.name, testArgs));
    } catch (e) {
      setTestResult({ ok: false, error: e.message });
    } finally {
      setTesting(false);
    }
  };

  return (
    <Modal open title={isNew ? "New HTTP API tool" : `Edit ${draft.name}`} onClose={onClose} width={760}
      subtitle="The model decides when to call it from the description, and fills the parameters from the conversation."
      footer={<>
        <span className="row" style={{ gap: 8, marginRight: "auto" }}>
          <Toggle checked={draft.enabled} onChange={(v) => setDraft({ ...draft, enabled: v })} label="Enabled" />
          <span className="small">{draft.enabled ? "Enabled" : "Disabled everywhere"}</span>
        </span>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={save} disabled={busy || !valid}>{busy ? "Saving…" : isNew ? "Create tool" : "Save tool"}</button>
      </>}>
      <div className="form-grid">
        <Field label="Name" required hint="What the model calls. lowercase_with_underscores." error={draft.name && !nameOk ? "3–49 chars: lowercase letters, digits, underscores" : ""}>
          <input className="input mono" value={draft.name} disabled={!isNew} placeholder="lookup_offer"
            onChange={(e) => setDraft({ ...draft, name: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })} />
        </Field>
        <Field label="Timeout">
          <Slider min={1} max={20} value={c.timeout_secs} unit="s" onChange={(v) => setC("timeout_secs", v)} />
        </Field>
        <Field label="Description" required className="span-2" hint="Tell the model exactly when to use it and when not to. This is the most important field.">
          <AutoTextarea minRows={2} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })}
            placeholder="Look up the best active offer for the customer's route. Use only after the customer asks about discounts." />
        </Field>
      </div>

      <Tabs value={tab} onChange={setTab} tabs={[
        { id: "request", label: "Request" },
        { id: "params", label: "Parameters", badge: c.parameters.length },
        { id: "response", label: "Response" },
        ...(isNew ? [] : [{ id: "test", label: "Test" }]),
      ]} />

      {tab === "request" && (
        <div className="stack-lg">
          <Field label="Endpoint" required error={c.url && !urlOk ? "Must start with http:// or https://" : ""}
            hint="Use {param} to place a parameter in the URL.">
            <div className="row" style={{ gap: 8 }}>
              <Segmented size="sm" value={c.method} onChange={(v) => setC("method", v)} options={["GET", "POST", "PUT", "PATCH"]} />
              <input className="input mono" value={c.url} onChange={(e) => setC("url", e.target.value)} placeholder="https://api.example.com/offers/{route}" />
            </div>
          </Field>
          <Field label="Headers" hint='Reference a secret as {{secret:NAME}}. It is resolved on the server from a stored variable, never shown here.'>
            <div className="stack" style={{ gap: 6 }}>
              {headers.map((h, i) => (
                <div key={i} className="row" style={{ gap: 6 }}>
                  <input className="input mono" style={{ flex: 1 }} placeholder="Header" value={h.k} onChange={(e) => setHeaders(headers.map((x, j) => (j === i ? { ...x, k: e.target.value } : x)))} />
                  <input className="input mono" style={{ flex: 2 }} placeholder="Value" value={h.v} onChange={(e) => setHeaders(headers.map((x, j) => (j === i ? { ...x, v: e.target.value } : x)))} />
                  <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setHeaders(headers.filter((_, j) => j !== i))} aria-label="Remove header"><X size={13} /></button>
                </div>
              ))}
              <button className="btn btn-sm" style={{ justifySelf: "start" }} onClick={() => setHeaders([...headers, { k: "", v: "" }])}><Plus size={13} /> Add header</button>
            </div>
          </Field>
          {c.method !== "GET" && (
            <Field label="Body template" hint="Optional JSON with {param} placeholders. Empty sends the parameters as a JSON body.">
              <textarea className="textarea code" rows={5} value={c.body_template} onChange={(e) => setC("body_template", e.target.value)} placeholder={'{"route": "{route}", "pax": {pax}}'} />
            </Field>
          )}
          <div className="switchrow">
            <div className="switchrow-text"><strong>Send call context</strong><span>Adds call id, phone number and booking reference as <code>context</code> in the request.</span></div>
            <Toggle checked={c.wants_voice_context} onChange={(v) => setC("wants_voice_context", v)} label="Send call context" />
          </div>
        </div>
      )}

      {tab === "params" && (
        <div className="stack" style={{ gap: 10 }}>
          {c.parameters.length === 0 && <p className="hint" style={{ margin: 0 }}>No parameters. The model calls it with no arguments.</p>}
          {c.parameters.map((p, i) => (
            <div key={i} className="card card-pad" style={{ padding: 12 }}>
              <div className="form-grid" style={{ gridTemplateColumns: "1.2fr 0.8fr auto", alignItems: "end" }}>
                <Field label="Name"><input className="input mono" value={p.name} onChange={(e) => setParam(i, "name", e.target.value.replace(/[^a-zA-Z0-9_]/g, "_"))} /></Field>
                <Field label="Type"><Select value={p.type} options={PARAM_TYPES} onChange={(v) => setParam(i, "type", v)} /></Field>
                <div className="row" style={{ gap: 8, paddingBottom: 6 }}>
                  <Toggle size="sm" checked={!!p.required} onChange={(v) => setParam(i, "required", v)} label="Required" />
                  <span className="small">Required</span>
                  <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setC("parameters", c.parameters.filter((_, j) => j !== i))} aria-label="Remove"><Trash size={13} /></button>
                </div>
                <div className="span-2" style={{ gridColumn: "1 / -1" }}>
                  <Field label="Description"><AutoTextarea value={p.description || ""} onChange={(e) => setParam(i, "description", e.target.value)} placeholder="What the model should put here" /></Field>
                </div>
              </div>
            </div>
          ))}
          <button className="btn btn-sm" style={{ justifySelf: "start" }}
            onClick={() => setC("parameters", [...c.parameters, { name: "", type: "string", description: "", required: true }])}>
            <Plus size={13} /> Add parameter
          </button>
        </div>
      )}

      {tab === "response" && (
        <div className="stack-lg">
          <Field label="Extract" hint="Dotted path into the JSON response, e.g. data.offer. Empty passes the whole (trimmed) response to the model.">
            <input className="input mono" value={c.response_path} onChange={(e) => setC("response_path", e.target.value)} placeholder="data.offer" />
          </Field>
          <Field label="Spoken line" hint="Optional line the agent can say with {field} filled from the result.">
            <input className="input" value={c.speak_template} onChange={(e) => setC("speak_template", e.target.value)} placeholder="I found an offer: {discount} rupees off on this route." />
          </Field>
        </div>
      )}

      {tab === "test" && (
        <div className="stack-lg">
          <p className="hint" style={{ margin: 0 }}>Saves your edits, then calls the endpoint once with these arguments.</p>
          <div className="form-grid">
            {c.parameters.map((p) => (
              <Field key={p.name} label={p.name} hint={p.type}>
                <input className="input mono" value={testArgs[p.name] ?? ""} onChange={(e) => setTestArgs({ ...testArgs, [p.name]: p.type === "string" ? e.target.value : e.target.value === "" ? "" : p.type === "boolean" ? e.target.value === "true" : Number(e.target.value) })} />
              </Field>
            ))}
          </div>
          <button className="btn btn-primary btn-sm" style={{ justifySelf: "start" }} onClick={runTest} disabled={testing || !valid}>
            <Play size={13} /> {testing ? "Calling…" : "Run test"}
          </button>
          {testResult && (
            <div className={`notice ${testResult.ok ? "ok" : "halt"}`} style={{ display: "block" }}>
              <div className="row" style={{ gap: 6, marginBottom: 6 }}>
                {testResult.ok ? <Check size={14} /> : <Alert size={14} />}
                <strong>{testResult.ok ? `HTTP ${testResult.status ?? 200}` : "Failed"}</strong>
              </div>
              <pre className="preview-pre" style={{ maxHeight: 260 }}>{JSON.stringify(testResult, null, 2)}</pre>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
