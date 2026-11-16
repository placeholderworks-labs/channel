import { fillPersona, SAMPLE_CUSTOMER } from "../lib/persona";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import AgentQms from "../components/AgentQms";
import {
  Alert,
  ArrowLeft,
  Search,
  Server,
  Braces,
  Chevron,
  Bot,
  Check,
  Copy,
  FileText,
  Inbox,
  Layers,
  Pencil,
  Mic2,
  Plus,
  Trash,
  Shield,
  Sparkle,
  Waves,
  Wrench,
  X,
} from "../components/Icons";
import {
  Badge,
  Confirm,
  Empty,
  Field,
  FieldActions,
  Modal,
  PageHeader,
  Segmented,
  Select,
  Skeleton,
  Slider,
  Tabs,
  TagInput,
  Toggle, AutoTextarea } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { relativeTime } from "../lib/format";
import { useToast } from "../lib/toast";
import VarTextarea from "../components/VarTextarea";
import { SUGGESTED_VARIABLES } from "../lib/variables";
import useAutoHindi from "../lib/useAutoHindi";
import { KINDS } from "./Guardrails";
import { STATUS_TONE, channelLabel, initials, slugify } from "./UseCases";

const BLANK = {
  slug: "",
  name: "",
  description: "",
  status: "draft",
  persona: { agent_name: "", agent_name_hindi: "", company: "PlaceholderWorks" },
  prompt: { system_prompt: "", context_template: "", use_base_rules: true },
  greeting: { hindi: "", english: "" },
  language: { default: "hindi", allow_switch: true },
  tools: ["voice_end_call", "voice_log_disposition"],
  llm: { provider: "groq", model: "", temperature: 0.4, max_tokens: 300, reasoning_effort: "low" },
  history_limit: 12,
  guardrails: {
    stay_on_domain: true,
    blocked_topics: [],
    refusal_line: {
      hindi: "माफ़ कीजिए, इस बारे में मैं मदद नहीं कर पाऊँगी। क्या मैं आपकी किसी और बात में मदद कर सकती हूँ?",
      english: "Sorry, I can't help with that. Is there anything else I can help you with?",
    },
    banned_phrases: [],
    max_reply_sentences: 3,
    max_reply_chars: 400,
    mask_pii: true,
    escalate_on: [],
    library: [],
  },
  voice: { tts_provider: "", voice_id: "" },
  variables: [],
  channels: ["website"],
  call: { is_phone: false, needs_cart: false, max_call_duration_secs: null },
  overrides: {
    retention_discount_percent: null, retention_discount_min_inr: null, retention_discount_max_inr: null,
    whatsapp_event_name: "", whatsapp_template_name: "", transfer_number: "",
  },
};

const META = ["version", "created_at", "updated_at", "updated_by", "builtin"];
const PERSONA_VARS = ["{agent_name}", "{agent_name_hindi}", "{company}"];
const RESERVED = new Set([
  "agent_name", "agent_name_hindi", "company", "customer_name", "today", "cart_summary", "booking_reference_id",
  "phone_number", "language", "max_call_duration_minutes", "language_rule", "script_rule",
  "style_directive_rule", "expressive_tags_rule", "timezone",
]);
const CALL_VARS = [
  ["customer_name", "The customer's name.", "everywhere"],
  ["phone_number", "The number being called.", "context template"],
  ["booking_reference_id", "The reference the call is about.", "context template"],
  ["today", "Today's date.", "context template"],
  ["language", "The language the call is in right now.", "context template"],
  ["max_call_duration_minutes", "The call's time budget, in minutes.", "context template"],
];
const BASE_KEYS = new Set(["reference_id", "customer_name", "phone_number", "scheduled_at", "language"]);
function callVarsFor(draft) {
  const intakes = draft._qms || [];
  if (!intakes.length) return CALL_VARS;
  const seen = new Set();
  const own = [];
  for (const intake of intakes) {
    for (const f of intake.allFields || []) {
      if (BASE_KEYS.has(f.key) || seen.has(f.key)) continue;
      seen.add(f.key);
      own.push([f.key, `${f.label || f.key}${f.description ? `: ${f.description}` : ""} (from ${intake.name})`, "context template"]);
    }
  }
  const cart = intakes.some((i) => i.kind === "cart") ? [["cart_summary", "One line describing what the customer enquired about or left in the cart.", "context template"]] : [];
  return [...CALL_VARS, ["call_details", "Every field the QMS API sent, as a list.", "context template"], ...cart, ...own];
}

const greetingCallVars = (draft) => {
  const base = new Set([...CALL_VARS.map(([k]) => k), "call_details"]);
  return callVarsFor(draft).filter(([k]) => !base.has(k));
};

const allVars = (draft) => {
  const own = (draft.variables || []).filter((v) => v.key);
  const keys = new Set(own.map((v) => v.key));
  return [...own, ...(draft._globals || []).filter((g) => !keys.has(g.key))];
};
const customVars = (draft) => allVars(draft).map((v) => `{${v.key}}`);
function varSets(draft) {
  const own = customVars(draft);
  return {
    prompt: [...PERSONA_VARS, ...own, "{customer_name}"],
    greeting: ["{customer_name}", ...PERSONA_VARS, ...own, ...greetingCallVars(draft).map(([k]) => `{${k}}`)],
    refusal: [...PERSONA_VARS, ...own],
    context: [...callVarsFor(draft).map(([k]) => `{${k}}`), ...PERSONA_VARS, ...own],
  };
}

function varItems(draft, kind) {
  const p = draft.persona || {};
  const items = [
    { key: "agent_name", detail: p.agent_name || "agent's name (not set)", group: "Agent" },
    { key: "agent_name_hindi", detail: p.agent_name_hindi || p.agent_name || "Hindi name (not set)", group: "Agent" },
    { key: "company", detail: p.company || "company (not set)", group: "Agent" },
    ...(draft.variables || []).filter((v) => v.key).map((v) => ({ key: v.key, detail: v.value || v.description || "no value yet", group: "Yours" })),
    ...allVars(draft).slice((draft.variables || []).filter((v) => v.key).length)
      .map((v) => ({ key: v.key, detail: v.value || v.description || "no value yet", group: "Global" })),
  ];
  if (kind === "context") {
    items.push(...callVarsFor(draft).map(([key, what]) => ({ key, detail: what, group: "Call" })));
  } else if (kind !== "refusal") {
    items.push({ key: "customer_name", detail: "the customer's name, filled per call", group: "Call" });
    if (kind === "greeting") {
      items.push(...greetingCallVars(draft).map(([key, what]) => ({ key, detail: `${what}. Dates are said as "18 November".`, group: "Call" })));
    }
  }
  return items;
}

export { fillPersona };
function clone(v) {
  return JSON.parse(JSON.stringify(v));
}

function merge(base, over) {
  const out = clone(base);
  for (const [k, v] of Object.entries(over || {})) {
    out[k] = v && typeof v === "object" && !Array.isArray(v) && out[k] && typeof out[k] === "object" ? merge(out[k], v) : v;
  }
  return out;
}

function strip(uc) {
  const out = clone(uc);
  for (const k of META) delete out[k];
  for (const k of Object.keys(out)) if (k.startsWith("_")) delete out[k];
  return out;
}

const FIELD_PATHS = [
  "name", "description", "status",
  "persona.agent_name", "persona.agent_name_hindi", "persona.company",
  "prompt.system_prompt", "prompt.context_template", "prompt.use_base_rules",
  "greeting.hindi", "greeting.english", "language.default", "language.allow_switch",
  "tools", "llm.provider", "llm.model", "llm.temperature", "llm.max_tokens", "llm.reasoning_effort", "history_limit",
  "guardrails.library", "guardrails.stay_on_domain", "guardrails.refusal_line.hindi", "guardrails.refusal_line.english",
  "guardrails.mask_pii", "guardrails.max_reply_sentences", "guardrails.max_reply_chars",
  "voice", "channels", "call.is_phone", "call.needs_cart", "call.max_call_duration_secs", "variables",
  "overrides",
];
const FIELD_LABELS = {
  "llm.provider": "model", "llm.model": "model", "voice": "voice", "tools": "tools",
  "guardrails.library": "attached guardrails", "channels": "channels", "variables": "variables",
};

const getPath = (obj, path) => path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
function setPath(obj, path, value) {
  const keys = path.split(".");
  let node = obj;
  for (const k of keys.slice(0, -1)) node = node[k] ??= {};
  node[keys.at(-1)] = value;
  return obj;
}
const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

const SWITCH_TOOL = "voice_switch_language";
const LINKED = { "language.allow_switch": "tools", tools: "language.allow_switch" };
const withLinked = (paths) => [...new Set(paths.flatMap((p) => (LINKED[p] ? [p, LINKED[p]] : [p])))];

function linkLanguageSwitch(next, path) {
  if (path === "language.allow_switch") {
    const tools = (next.tools || []).filter((t) => t !== SWITCH_TOOL);
    next.tools = next.language.allow_switch ? [...tools, SWITCH_TOOL] : tools;
  } else if (path === "tools") {
    next.language = { ...next.language, allow_switch: (next.tools || []).includes(SWITCH_TOOL) };
  }
  return next;
}

const EditCtx = createContext(null);

function Dirty({ paths, label }) {
  const ctx = useContext(EditCtx);
  if (!ctx || ctx.isNew) return null;
  const dirty = paths.some((p) => ctx.differs(p));
  return (
    <FieldActions dirty={dirty} saving={ctx.savingPaths === paths.join()} label={label || FIELD_LABELS[paths[0]] || paths[0].split(".").pop().replaceAll("_", " ")}
      onSave={() => ctx.savePaths(paths)} onRevert={() => ctx.revertPaths(paths)} />
  );
}

export default function UseCaseEditor({ isNew }) {
  const { slug } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const { can } = useAuth();
  const editable = can("usecases.edit");

  const [saved, setSaved] = useState(null);
  const [draft, setDraft] = useState(null);
  const [catalog, setCatalog] = useState([]);
  const [llm, setLlm] = useState(null);
  const [voices, setVoices] = useState({});
  const [ttsDefault, setTtsDefault] = useState("");
  const [ingestionAgent, setIngestionAgent] = useState("");
  const [all, setAll] = useState([]);
  const [error, setError] = useState("");
  const [params] = useSearchParams();
  const [tab, setTab] = useState(() => params.get("tab") || "agent");
  const [qms, setQms] = useState([]);
  const [globals, setGlobals] = useState([]);
  const loadQms = useCallback(() => {
    if (isNew || !slug) return;
    api.qmsForAgent(slug).then((r) => setQms(r.intakes || [])).catch(() => setQms([]));
  }, [slug, isNew]);
  useEffect(() => { loadQms(); }, [loadQms]);
  const loadGlobals = useCallback(() => {
    api.globals().then((r) => setGlobals(r.variables || [])).catch(() => setGlobals([]));
  }, []);
  useEffect(() => { loadGlobals(); }, [loadGlobals]);
  const [saving, setSaving] = useState(false);
  const [savingPaths, setSavingPaths] = useState("");
  const announce = ({ qmsReleased, ...usecase }) => {
    for (const r of qmsReleased || []) {
      toast.ok(`${r.released} held record${r.released === 1 ? "" : "s"} from ${r.intake} queued for calling`);
    }
    if ((qmsReleased || []).length) loadQms();
    return usecase;
  };

  const load = useCallback(async () => {
    setError("");
    try {
      const [tools, options, list] = await Promise.all([
        api.tools().catch(() => ({ tools: [] })),
        api.llmOptions().catch(() => null),
        api.usecases().catch(() => ({ usecases: [] })),
      ]);
      setCatalog(tools.tools || []);
      setLlm(options);
      setAll(list.usecases || []);
      if (isNew) {
        const start = merge(BLANK, { llm: { model: options?.providers?.[0]?.default || options?.providers?.[0]?.models?.[0] || "" } });
        setSaved(start);
        setDraft(clone(start));
      } else {
        const uc = merge(BLANK, await api.usecase(slug));
        setSaved(uc);
        setDraft(clone(uc));
      }
    } catch (e) {
      setError(e.message);
    }
    api.status().then((st) => setIngestionAgent(st?.integrations?.ingestion?.agent || "")).catch(() => {});
    api.playground().then((p) => {
      setVoices(p?.webrtc?.tts || {});
      setTtsDefault(p?.webrtc?.ttsProvider || "");
    }).catch(() => {});
  }, [slug, isNew]);

  useEffect(() => {
    load();
  }, [load]);

  const dirty = useMemo(() => draft && saved && JSON.stringify(draft) !== JSON.stringify(saved), [draft, saved]);
  const view = useMemo(() => (draft ? { ...draft, _qms: qms, _globals: globals } : draft), [draft, qms, globals]);

  useEffect(() => {
    if (!dirty) return undefined;
    const warn = (e) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const set = (path, value) =>
    setDraft((current) => {
      const next = clone(current);
      const keys = path.split(".");
      let node = next;
      for (const k of keys.slice(0, -1)) node = node[k] ??= {};
      node[keys.at(-1)] = value;
      return linkLanguageSwitch(next, path);
    });

  const problems = useMemo(() => {
    if (!draft) return {};
    const p = {};
    if (!draft.name.trim()) p.name = "Give it a name";
    if (isNew && !/^[a-z][a-z0-9_]{2,40}$/.test(draft.slug)) p.slug = "3–41 chars: lowercase letters, digits, underscores; starts with a letter";
    if (draft.status === "active" && !draft.prompt.system_prompt.trim()) p.system_prompt = "An active agent needs a system prompt";
    if (!draft.channels.length) p.channels = "Pick at least one channel";
    if (!draft.llm.model) p.model = "Pick a model";
    return p;
  }, [draft, isNew]);

  const differs = useCallback((path) => !!draft && !!saved && !same(getPath(draft, path), getPath(saved, path)), [draft, saved]);
  const dirtyFields = useMemo(() => (draft && saved && !isNew ? FIELD_PATHS.filter(differs) : []), [draft, saved, isNew, differs]);

  const savePaths = async (requested) => {
    const paths = withLinked(requested);
    const patch = {};
    for (const path of paths) setPath(patch, path, clone(getPath(draft, path) ?? null));
    if (paths.some((x) => x.startsWith("llm.provider") || x.startsWith("llm.model"))) {
      setPath(patch, "llm.provider", draft.llm.provider);
      setPath(patch, "llm.model", draft.llm.model);
    }
    setSavingPaths(requested.join());
    try {
      const updated = merge(BLANK, announce(await api.updateUsecase(slug, patch)));
      const next = clone(updated);
      for (const path of FIELD_PATHS) {
        if (!paths.includes(path) && !same(getPath(draft, path), getPath(saved, path))) {
          setPath(next, path, clone(getPath(draft, path)));
        }
      }
      setSaved(updated);
      setDraft(next);
      toast.ok(`Saved. Version ${updated.version} is live on the next turn`);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSavingPaths("");
    }
  };

  const revertPaths = (paths) =>
    setDraft((current) => {
      const next = clone(current);
      for (const path of withLinked(paths)) setPath(next, path, clone(getPath(saved, path)));
      return next;
    });

  const ctx = { isNew, differs, savePaths, revertPaths, savingPaths };

  const save = async () => {
    if (Object.keys(problems).length) {
      toast.error(Object.values(problems)[0]);
      if (problems.channels) setTab("channels");
      else if (problems.model) setTab("voice");
      else setTab("agent");
      return;
    }
    setSaving(true);
    try {
      if (isNew) {
        const created = await api.createUsecase(strip(draft));
        toast.ok(`${created.name} created`);
        setSaved(merge(BLANK, created));
        navigate(`/agents/${created.slug}`, { replace: true });
      } else {
        const updated = merge(BLANK, announce(await api.updateUsecase(slug, strip(draft))));
        setSaved(updated);
        setDraft(clone(updated));
        toast.ok(`Saved. Version ${updated.version} is live on the next turn`);
      }
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  if (error) {
    return (
      <div className="page">
        <Link to="/agents" className="back-link"><ArrowLeft size={13} /> Agents</Link>
        <div className="notice halt"><Alert size={15} /><span>{error}</span></div>
      </div>
    );
  }

  if (!draft) {
    return (
      <div className="page wide stack-lg">
        <Skeleton h={28} w={260} />
        <Skeleton h={44} />
        <Skeleton h={420} r={12} />
      </div>
    );
  }

  const toolCount = draft.tools.length;
  const guardCount = (draft.guardrails.library || []).length;
  const tabs = [
    { id: "agent", label: "Agent", icon: <Bot size={14} />, badge: problems.name || problems.system_prompt || problems.slug ? "!" : "", badgeTone: "halt" },
    { id: "variables", label: "Variables", icon: <Braces size={14} />, badge: (draft.variables || []).length + 3, },
    { id: "tools", label: "Tools", icon: <Wrench size={14} />, badge: toolCount },
    { id: "guardrails", label: "Guardrails", icon: <Shield size={14} />, badge: guardCount || "" },
    { id: "voice", label: "Voice & model", icon: <Mic2 size={14} />, badge: problems.model ? "!" : "", badgeTone: "halt" },
    { id: "channels", label: "Channels & calls", icon: <Layers size={14} />, badge: problems.channels ? "!" : draft.channels.length, badgeTone: problems.channels ? "halt" : "" },
    ...(isNew ? [] : [
      { id: "qms", label: "QMS", icon: <Inbox size={14} />, badge: qms.length || "" },
      { id: "preview", label: "Preview", icon: <FileText size={14} /> },
    ]),
  ];

  return (
    <div className="page wide">
      <PageHeader
        back={<Link to="/agents" className="back-link"><ArrowLeft size={13} /> Agents</Link>}
        title={
          <span className="row" style={{ gap: 12 }}>
            <span className={`uc-icon ${draft.status}`}>{initials(draft.name || "New")}</span>
            <span>{draft.name || (isNew ? "New agent" : slug)}</span>
            <Badge tone={STATUS_TONE[draft.status]} dot>{draft.status}</Badge>
            {saved?.builtin && <Badge tone="brand">Built-in</Badge>}
          </span>
        }
        subtitle={isNew ? "Define the agent, then save it as a draft to test it before switching it on." : draft.description || undefined}
        actions={
          <>
            {!isNew && can("calls.place") && (draft.channels || []).includes("website") && (
              <Link className="btn btn-sm" to={`/playground/webrtc?use_case=${slug}`}><Waves size={14} /> Test in browser</Link>
            )}
            {editable && (
              <span className="row" style={{ gap: 6 }}>
                <Segmented
                  size="sm"
                  value={draft.status}
                  onChange={(v) => set("status", v)}
                  options={[
                    { value: "draft", label: "Draft" },
                    { value: "active", label: "Active" },
                    { value: "archived", label: "Archived" },
                  ]}
                />
                <EditCtx.Provider value={ctx}><Dirty paths={["status"]} label="status" /></EditCtx.Provider>
              </span>
            )}
            {editable && !isNew && dirtyFields.length > 1 && (
              <span className="unsaved-group">
                {dirtyFields.length} unsaved
                <FieldActions dirty saving={saving} label="all changes" onSave={save} onRevert={() => setDraft(clone(saved))} />
              </span>
            )}
            {editable && isNew && (
              <>
                <button className="btn btn-ghost btn-sm" onClick={() => navigate("/agents")}>Cancel</button>
                <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>{saving ? "Creating…" : "Create agent"}</button>
              </>
            )}
          </>
        }
      />

      {!editable && (
        <div className="notice" style={{ marginBottom: 16 }}>
          <Shield size={15} /><span>You can view this agent. Editing needs the “Edit agents” permission.</span>
        </div>
      )}

      <Tabs tabs={tabs} value={tab} onChange={setTab} />

      <div className="editor">
        <div className="tab-pane" key={tab}>
          <EditCtx.Provider value={ctx}>
          <fieldset disabled={!editable} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
            {tab === "agent" && <AgentTab draft={view} set={set} isNew={isNew} problems={problems} all={all} setDraft={setDraft} />}
            {tab === "variables" && <VariablesTab draft={view} set={set} onGlobals={loadGlobals} />}
            {tab === "tools" && <ToolsTab draft={view} set={set} catalog={catalog} onOwnSettings={() => {
              setTab("channels");
              setTimeout(() => document.getElementById("own-settings")?.scrollIntoView({ behavior: "smooth", block: "center" }), 120);
            }} />}
            {tab === "guardrails" && <GuardrailsTab draft={view} set={set} />}
            {tab === "voice" && <VoiceTab draft={draft} set={set} llm={llm} voices={voices} ttsDefault={ttsDefault} problems={problems} />}
            {tab === "channels" && <ChannelsTab draft={view} set={set} problems={problems} onQms={() => setTab("qms")} />}
          </fieldset>
          </EditCtx.Provider>
          {tab === "preview" && <PreviewTab slug={slug} dirty={dirty} />}
          {tab === "qms" && !isNew && <AgentQms slug={slug} agentName={draft.name} editable={editable} onChange={loadQms}
            live={saved?.status === "active"} channels={saved?.channels || []} />}
        </div>

        <aside className="editor-side">
          <div className="side-card">
            <h4>Summary</h4>
            <dl className="kv">
              <dt>Identifier</dt><dd className="mono">{draft.slug || "-"}</dd>
              <dt>Agent</dt><dd>{draft.persona.agent_name || "-"}</dd>
              <dt>Language</dt><dd>{draft.language.default}{draft.language.allow_switch ? " · can switch" : ""}</dd>
              <dt>Model</dt><dd className="mono">{draft.llm.model || "-"}</dd>
              <dt>Tools</dt><dd>{toolCount}</dd>
              <dt>Guardrails</dt><dd>{guardCount} attached{draft.guardrails.mask_pii ? " · PII masked" : ""}</dd>
              <dt>Channels</dt><dd>{draft.channels.map(channelLabel).join(", ") || "-"}</dd>
              {!isNew && <><dt>Version</dt><dd>v{saved?.version}</dd></>}
              {!isNew && saved?.updated_at && <><dt>Updated</dt><dd>{relativeTime(saved.updated_at)}</dd></>}
            </dl>
          </div>
          <div className="side-card">
            <h4>Checklist</h4>
            <Check1 ok={!!draft.prompt.system_prompt.trim()}>System prompt written</Check1>
            <Check1 ok={!!(draft.greeting.hindi || draft.greeting.english)}>Greeting set</Check1>
            <Check1 ok={toolCount > 0}>Tools chosen</Check1>
            <Check1 ok={draft.guardrails.stay_on_domain || guardCount > 0}>Guardrails in place</Check1>
            <Check1 ok={draft.channels.length > 0}>On at least one channel</Check1>
            <Check1 ok={draft.status === "active"}>Switched on</Check1>
          </div>
          {!isNew && (
            <div className="side-card">
              <h4>QMS</h4>
              <p className="hint" style={{ margin: 0 }}>
                {ingestionAgent === slug
                  ? "The Abandoned cart API in QMS calls every record with this agent."
                  : `No QMS intake dials this agent yet (the Abandoned cart API dials ${ingestionAgent || "another agent"}). It runs from its channel default or the test pages.`}
              </p>
            </div>
          )}
        </aside>
      </div>


    </div>
  );
}

function Check1({ ok, children }) {
  return (
    <div className="row" style={{ gap: 8, fontSize: 12.5, padding: "3px 0", color: ok ? "var(--ink)" : "var(--faint)" }}>
      <span style={{ width: 16, height: 16, borderRadius: 5, display: "grid", placeItems: "center",
        background: ok ? "var(--ok)" : "var(--surface-sunk)", color: "#fff", border: ok ? 0 : "1px solid var(--line-strong)" }}>
        {ok && <Check size={11} />}
      </span>
      {children}
    </div>
  );
}

function Section({ title, subtitle, children, aside }) {
  return (
    <section className="section">
      <div className="section-head">
        <div style={{ flex: 1 }}>
          <h3>{title}</h3>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {aside}
      </div>
      <div className="section-body">{children}</div>
    </section>
  );
}

function SwitchRow({ title, children, checked, onChange, paths }) {
  return (
    <div className="switchrow">
      <div className="switchrow-text"><strong>{title}</strong><span>{children}</span></div>
      {paths && <Dirty paths={paths} label={title.toLowerCase()} />}
      <Toggle checked={checked} onChange={onChange} label={title} />
    </div>
  );
}

const SUGGESTERS = {
  greeting: {
    title: "Suggested greetings",
    blurb: "Written from this agent's prompt, purpose and variables. Pick one, then save it with ✓.",
    button: "Suggest greetings",
    call: (body) => api.suggestGreetings(body),
    path: (lang) => `greeting.${lang}`,
    current: (draft, lang) => draft.greeting[lang],
    useLabel: (label) => `Use as ${label} greeting`,
    note: (line) => (line.includes("{customer_name}") ? "uses the customer's name" : "no customer name"),
  },
  refusal: {
    title: "Suggested refusal lines",
    blurb: "What the agent says when it won't discuss something, written from its purpose, blocked topics and variables. Pick one, then save it with ✓.",
    button: "Suggest refusal lines",
    call: (body) => api.suggestRefusals(body),
    path: (lang) => `guardrails.refusal_line.${lang}`,
    current: (draft, lang) => draft.guardrails.refusal_line[lang],
    useLabel: (label) => `Use as ${label} refusal`,
    note: () => "",
  },
};

function LineSuggestions({ kind, draft, set, extra = {} }) {
  const cfg = SUGGESTERS[kind];
  const [state, setState] = useState({ loading: false, error: "", data: null });
  const asked = useRef(false);
  const empty = !cfg.current(draft, "hindi").trim() && !cfg.current(draft, "english").trim();
  const hasBrief = !!(draft.name || draft.description || draft.prompt.system_prompt.trim());

  const suggest = useCallback(async () => {
    setState({ loading: true, error: "", data: null });
    try {
      const data = await cfg.call({
        name: draft.name,
        description: draft.description,
        system_prompt: draft.prompt.system_prompt,
        persona: draft.persona,
        variables: allVars(draft),
        is_phone: !!draft.call?.is_phone,
        fields: kind === "greeting" ? greetingCallVars(draft).map(([key, what]) => ({ key, label: what })) : [],
        ...extra,
      });
      setState({ loading: false, error: "", data });
    } catch (e) {
      setState({ loading: false, error: e.message, data: null });
    }
  }, [draft, cfg, extra]);

  useEffect(() => {
    if (empty && hasBrief && !asked.current) {
      asked.current = true;
      suggest();
    }
  }, [empty, hasBrief, suggest]);

  const groups = [["english", "English"], ["hindi", "Hindi"]];
  return (
    <div className="gsug">
      <div className="gsug-head">
        <span className="gsug-title"><Sparkle size={14} /> {cfg.title}</span>
        <span className="hint" style={{ margin: 0 }}>{cfg.blurb}</span>
        <span className="grow" />
        <button type="button" className="btn btn-sm" onClick={suggest} disabled={state.loading}>
          {state.loading ? "Writing…" : state.data ? "Suggest again" : cfg.button}
        </button>
      </div>
      {state.error && <div className="notice warn"><Alert size={15} /><span>{state.error}</span></div>}
      {state.loading && <div className="gsug-grid">{[0, 1, 2, 3].map((i) => <Skeleton key={i} h={92} r={10} />)}</div>}
      {state.data && (
        <div className="gsug-grid">
          {groups.flatMap(([lang, label]) =>
            (state.data[lang] || []).map((line, i) => {
              const inUse = cfg.current(draft, lang).trim() === line.trim();
              const note = cfg.note(line);
              return (
                <div key={`${lang}-${i}`} className={`gsug-card ${inUse ? "on" : ""}`}>
                  <div className="gsug-meta">
                    <Badge tone="brand">{label}</Badge>
                    {note && <span className="tiny faint">{note}</span>}
                  </div>
                  <div className="gsug-line">{line}</div>
                  <div className="gsug-said">{fillPersona(line, draft.persona, SAMPLE_CUSTOMER, allVars(draft), { greeting: kind === "greeting" })}</div>
                  <button type="button" className={`btn btn-sm ${inUse ? "" : "btn-primary"}`} disabled={inUse}
                    onClick={() => set(cfg.path(lang), line)}>
                    {inUse ? <><Check size={12} /> In use</> : cfg.useLabel(label)}
                  </button>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

function PersonaText({ label, value, onChange, vars, persona, placeholder, paths, variables, items, greeting = false }) {
  const ref = useRef(null);
  const insert = (token) => {
    const el = ref.current;
    const start = el?.selectionStart ?? value.length;
    const end = el?.selectionEnd ?? value.length;
    onChange(value.slice(0, start) + token + value.slice(end));
    requestAnimationFrame(() => {
      if (!el) return;
      el.focus();
      el.selectionStart = el.selectionEnd = start + token.length;
    });
  };
  const filled = fillPersona(value, persona, SAMPLE_CUSTOMER, variables, { greeting });
  return (
    <Field label={label} aside={paths && <Dirty paths={paths} label={label.toLowerCase()} />}>
      <div className="var-chips">
        {vars.map((v) => <button type="button" key={v} className="var-chip" onClick={() => insert(v)}>{v}</button>)}
      </div>
      <VarTextarea ref={ref} className="textarea" rows={3} value={value} placeholder={placeholder} onChange={onChange} items={items} />
      {value.trim() && (
        <div className="said-as"><span>Sounds like</span>
          {filled.split(/(\{[a-z][a-z0-9_]*\})/g).map((part, i) =>
            i % 2 === 1 ? <mark key={i} className="said-bad" title="Not defined. The customer would hear this as-is">{part}</mark> : part
          )}
        </div>
      )}
    </Field>
  );
}

function PromptArea({ value, onChange, vars, rows = 18, placeholder, tall, items }) {
  const ref = useRef(null);
  const insert = (token) => {
    const el = ref.current;
    if (!el) return onChange(value + token);
    const start = el.selectionStart ?? value.length;
    const end = el.selectionEnd ?? value.length;
    const next = value.slice(0, start) + token + value.slice(end);
    onChange(next);
    requestAnimationFrame(() => {
      el.focus();
      el.selectionStart = el.selectionEnd = start + token.length;
    });
  };
  return (
    <div className="stack" style={{ gap: 8 }}>
      {vars && (
        <div className="var-chips">
          {vars.map((v) => <button type="button" key={v} className="var-chip" onClick={() => insert(v)}>{v}</button>)}
        </div>
      )}
      <VarTextarea ref={ref} className={`textarea code ${tall ? "tall" : ""}`} rows={rows} value={value}
        placeholder={placeholder} onChange={onChange} items={items} />
      <div className="prompt-meta">
        <span>{value.length.toLocaleString()} chars · ~{Math.ceil(value.length / 4).toLocaleString()} tokens</span>
        <span>{value.split("\n").length} lines</span>
      </div>
    </div>
  );
}

function AgentTab({ draft, set, isNew, problems, all, setDraft }) {
  const [template, setTemplate] = useState("");
  return (
    <>
      {isNew && (
        <Section title="Start from" subtitle="Copy the prompt, tools and guardrails of an existing agent, or start blank.">
          <Select
            value={template}
            placeholder="Blank"
            options={all.map((u) => ({ value: u.slug, label: `${u.name} (${u.slug})` }))}
            onChange={async (v) => {
              setTemplate(v);
              if (!v) return;
              const src = await api.usecase(v);
              setDraft((d) => merge(BLANK, { ...strip(src), name: d.name, slug: d.slug, description: d.description, status: "draft" }));
            }}
          />
        </Section>
      )}

      <Section title="Identity" subtitle="How this agent is listed here. The name it speaks with and its company are on the Variables tab.">
        <div className="form-grid">
          <Field aside={<Dirty paths={["name"]} />} label="Name" required error={problems.name}>
            <input className={`input ${problems.name ? "err" : ""}`} value={draft.name} placeholder="Lead follow-up call"
              onChange={(e) => {
                set("name", e.target.value);
                if (isNew && !draft._slugTouched) set("slug", slugify(e.target.value));
              }} />
          </Field>
          <Field label="Identifier" required={isNew} error={problems.slug}
            hint={isNew ? "Used by QMS records and channel defaults. Can't be changed later." : "Fixed once created."}>
            <input className={`input mono ${problems.slug ? "err" : ""}`} value={draft.slug} disabled={!isNew}
              onChange={(e) => { set("slug", slugify(e.target.value)); set("_slugTouched", true); }} />
          </Field>
          <Field aside={<Dirty paths={["description"]} />} label="Description" hint="For the team: what this agent is for.">
            <AutoTextarea value={draft.description} placeholder="Calls people who left an enquiry on the website" onChange={(e) => set("description", e.target.value)} />
          </Field>
        </div>
      </Section>

      <Section title="System prompt" subtitle="Who the agent is, its goal, how a call should flow, and what it must never do. Sent once per call so the model can cache it."
        aside={<span className="row" style={{ gap: 6 }}><Dirty paths={["prompt.system_prompt"]} label="system prompt" />{problems.system_prompt && <Badge tone="halt">required</Badge>}</span>}>
        <PromptArea value={draft.prompt.system_prompt} onChange={(v) => set("prompt.system_prompt", v)} vars={varSets(draft).prompt} items={varItems(draft, "prompt")} tall
          placeholder={"<role>\nYou are {agent_name}, a voice assistant from {company}…\n</role>"} />
        {problems.system_prompt && <p className="hint field-err">{problems.system_prompt}</p>}
        <SwitchRow paths={["prompt.use_base_rules"]} title="Include the shared voice rules" checked={draft.prompt.use_base_rules} onChange={(v) => set("prompt.use_base_rules", v)}>
          Prepends the house rules for speaking: numbers in words, short sentences, language and script, TTS quirks. Leave on unless you know why.
        </SwitchRow>
      </Section>

      <Section title="Greeting" subtitle="The first line, spoken from a template the moment the call connects. Leave empty to let the model write it.">
        <div className="form-grid">
          <PersonaText greeting paths={["greeting.hindi"]} label="Hindi" value={draft.greeting.hindi} onChange={(v) => set("greeting.hindi", v)} vars={varSets(draft).greeting} variables={allVars(draft)} items={varItems(draft, "greeting")}
            persona={draft.persona} placeholder="नमस्ते {customer_name} जी, मैं {agent_name_hindi} बोल रही हूँ {company} से।" />
          <PersonaText greeting paths={["greeting.english"]} label="English" value={draft.greeting.english} onChange={(v) => set("greeting.english", v)} vars={varSets(draft).greeting} variables={allVars(draft)} items={varItems(draft, "greeting")}
            persona={draft.persona} placeholder="Hi {customer_name}, this is {agent_name} from {company}." />
        </div>
        <p className="hint" style={{ margin: 0 }}>Type <code>{"{"}</code> to pick a variable. Names and values come from the Variables tab. Change them once and every line follows. A greeting with <code>{"{customer_name}"}</code> is skipped when the name isn't known, so the model opens instead.</p>
        <LineSuggestions kind="greeting" draft={draft} set={set} />
      </Section>

      <Section title="Language">
        <div className="form-grid">
          <Field aside={<Dirty paths={["language.default"]} />} label="Opens in">
            <Segmented value={draft.language.default} onChange={(v) => set("language.default", v)}
              options={[{ value: "hindi", label: "Hindi" }, { value: "english", label: "English" }]} />
          </Field>
          <SwitchRow paths={["language.allow_switch"]} title="Allow switching mid-call" checked={draft.language.allow_switch} onChange={(v) => set("language.allow_switch", v)}>
            Only when the customer explicitly asks. This is the <span className="mono">voice_switch_language</span> tool: turning it on gives the agent that tool, turning it off takes it away.
          </SwitchRow>
        </div>
      </Section>

      <Section title="Call context template" subtitle="Per-call facts the agent sees alongside each turn: customer, cart, time left. Leave empty to use the built-in template for phone or web."
        aside={<Dirty paths={["prompt.context_template"]} label="context template" />}>
        <PromptArea value={draft.prompt.context_template} onChange={(v) => set("prompt.context_template", v)} vars={varSets(draft).context} items={varItems(draft, "context")} rows={8}
          placeholder={"<call_context>\nToday: {today}\nCustomer: {customer_name}\nCart: {cart_summary}\n</call_context>"} />
      </Section>
    </>
  );
}

const TEMPLATED_TEXTS = [
  ["System prompt", (d) => d.prompt.system_prompt],
  ["Greeting (Hindi)", (d) => d.greeting.hindi],
  ["Greeting (English)", (d) => d.greeting.english],
  ["Refusal (Hindi)", (d) => d.guardrails.refusal_line.hindi],
  ["Refusal (English)", (d) => d.guardrails.refusal_line.english],
  ["Context template", (d) => d.prompt.context_template],
];

function usesOf(draft, key) {
  return TEMPLATED_TEXTS.filter(([, get]) => (get(draft) || "").includes(`{${key}}`)).map(([label]) => label);
}

function AddVariable({ existing, onAdd }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => !ref.current?.contains(e.target) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  const suggestions = SUGGESTED_VARIABLES.filter((x) => !existing.includes(x.key));
  const add = (v) => { onAdd(v); setOpen(false); };
  return (
    <div className="addvar" ref={ref}>
      <button type="button" className="btn btn-sm" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="menu">
        <Plus size={13} /> Add variable <Chevron size={12} dir={open ? "up" : "down"} />
      </button>
      {open && (
        <div className="addvar-menu" role="menu">
          <button type="button" role="menuitem" className="addvar-item" onClick={() => add({ key: "", value: "", description: "" })}>
            <span className="addvar-key">Blank variable</span><span className="addvar-desc">Name it and give it a value</span>
          </button>
          {suggestions.length > 0 && <div className="addvar-sep">Suggested</div>}
          {suggestions.map((x) => (
            <button type="button" role="menuitem" key={x.key} className="addvar-item" onClick={() => add({ ...x })}>
              <span className="addvar-key mono">{`{${x.key}}`}</span>
              <span className="addvar-desc">{x.value || x.description}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function VariablesTab({ draft, set, onGlobals }) {
  const vars = draft.variables || [];
  const [editGlobals, setEditGlobals] = useState(false);
  const { can } = useAuth();
  const hindi = useAutoHindi(draft.persona.agent_name, (v) => set("persona.agent_name_hindi", v));
  const update = (i, patch) => set("variables", vars.map((v, j) => (j === i ? { ...v, ...patch } : v)));
  const keys = vars.map((v) => v.key);
  const known = new Set([...RESERVED, ...keys, ...(draft._globals || []).map((g) => g.key), ...callVarsFor(draft).map(([k]) => k)]);
  const unknown = [];
  for (const [label, get] of TEMPLATED_TEXTS) {
    for (const m of (get(draft) || "").matchAll(/\{([a-z][a-z0-9_]*)\}/g)) {
      if (!known.has(m[1]) && !unknown.some((u) => u.key === m[1])) unknown.push({ key: m[1], where: label });
    }
  }
  const errorFor = (v, i) => {
    if (!v.key) return "Give it a name";
    if (!/^[a-z][a-z0-9_]{1,40}$/.test(v.key)) return "2–41 lowercase letters, digits or underscores";
    if (RESERVED.has(v.key)) return "That name is built in";
    if (keys.indexOf(v.key) !== i) return "Already defined";
    return "";
  };

  return (
    <>
      <Section title="Agent" subtitle="Who the agent is. These fill {agent_name}, {agent_name_hindi} and {company} in the prompt, greeting and refusal lines.">
        <div className="form-grid">
          <Field aside={<Dirty paths={["persona.agent_name"]} />} label="{agent_name}" hint="The agent's name, e.g. Riya.">
            <input className="input" value={draft.persona.agent_name} placeholder="Riya" onChange={(e) => set("persona.agent_name", e.target.value)} />
          </Field>
          <Field aside={<Dirty paths={["persona.agent_name_hindi"]} />} label="{agent_name_hindi}" hint={hindi.busy || hindi.error ? hindi.hint : "Written for you when the name above changes. Edit if needed."}>
            <input className="input" value={draft.persona.agent_name_hindi || ""} placeholder="रिया"
              onChange={(e) => { hindi.markManual(); set("persona.agent_name_hindi", e.target.value); }} />
          </Field>
          <Field aside={<Dirty paths={["persona.company"]} />} label="{company}" hint="The company the agent speaks for.">
            <input className="input" value={draft.persona.company} onChange={(e) => set("persona.company", e.target.value)} />
          </Field>
        </div>
      </Section>

      <Section title="Global variables" subtitle="Shared by every agent: company details, helpline, website. A variable of the same name below overrides it for this agent only."
        aside={can("usecases.edit") && <button type="button" className="btn btn-sm" onClick={() => setEditGlobals(true)}><Pencil size={13} /> Edit globals</button>}>
        {(draft._globals || []).length === 0 ? (
          <p className="hint" style={{ margin: 0 }}>None yet. Add the details every agent should know once, here, instead of in each agent.</p>
        ) : (
          <div className="var-table">
            <div className="var-row var-head ro"><span>Name</span><span>Value</span><span>Here</span></div>
            {draft._globals.map((g) => {
              const overridden = keys.includes(g.key);
              return (
                <div key={g.key} className="var-row ro">
                  <code className="var-code">{`{${g.key}}`}</code>
                  <span className="small">{g.value || <span className="faint">empty</span>}{g.description && <span className="tiny faint"> · {g.description}</span>}</span>
                  <span className="small">{overridden ? <Badge tone="warn">overridden</Badge> : <span className="dim">{usesOf(draft, g.key).join(", ") || "not used yet"}</span>}</span>
                </div>
              );
            })}
          </div>
        )}
      </Section>
      {editGlobals && <GlobalsDialog initial={draft._globals || []} onClose={() => setEditGlobals(false)} onSaved={() => { setEditGlobals(false); onGlobals?.(); }} />}

      <Section title="This agent's variables" subtitle="Define a value once and use it as {name} in any text below. Change it here and every line that uses it changes with it."
        aside={<span className="row" style={{ gap: 6 }}>
          <Dirty paths={["variables"]} />
          <AddVariable existing={keys} onAdd={(v) => set("variables", [...vars, v])} />
        </span>}>
        {vars.length === 0 ? (
          <p className="hint" style={{ margin: 0 }}>No variables yet. Use Add variable for anything you repeat, like a helpline number, an offer or a support email, e.g. <code>{"{helpline}"}</code>.</p>
        ) : (
          <div className="var-table">
            <div className="var-row var-head"><span>Name</span><span>Value</span><span>Description</span><span>Used in</span><span /></div>
            {vars.map((v, i) => {
              const err = errorFor(v, i);
              const used = v.key ? usesOf(draft, v.key) : [];
              return (
                <div key={i} className="var-row">
                  <div>
                    <div className={`var-key ${err ? "err" : ""}`}>
                      <span>{"{"}</span>
                      <input value={v.key} placeholder="helpline" aria-label="Variable name"
                        onChange={(e) => update(i, { key: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })} />
                      <span>{"}"}</span>
                    </div>
                    {err && <div className="hint field-err">{err}</div>}
                  </div>
                  <AutoTextarea value={v.value} placeholder="1800-103-xxxx" aria-label="Value" onChange={(e) => update(i, { value: e.target.value })} />
                  <AutoTextarea value={v.description} placeholder="What it is, for the team" aria-label="Description" onChange={(e) => update(i, { description: e.target.value })} />
                  <span className="small">{used.length ? used.join(", ") : <span className="faint">not used yet</span>}</span>
                  <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label={`Remove ${v.key || "variable"}`}
                    onClick={() => set("variables", vars.filter((_, j) => j !== i))}><Trash size={13} /></button>
                </div>
              );
            })}
          </div>
        )}
        {unknown.length > 0 && (
          <div className="notice warn"><Alert size={15} /><span>
            Not defined anywhere, so the agent would see the braces as-is:{" "}
            {unknown.map((u, i) => <span key={u.key}>{i > 0 && ", "}<code>{`{${u.key}}`}</code> in {u.where}</span>)}.{" "}
            Add each one with Add variable.
          </span></div>
        )}
      </Section>

      <Section title="Filled on every call" subtitle={(draft._qms || []).length
        ? "Common to every agent, plus every field of the QMS API connected on the QMS tab. Set automatically on each call; use them in the context template."
        : "Common to every agent and set automatically on each call. Nothing to edit."}>
        <div className="var-table">
          <div className="var-row var-head ro"><span>Name</span><span>What it holds</span><span>Works in</span></div>
          {callVarsFor(draft).map(([key, what, where]) => (
            <div key={key} className="var-row ro">
              <code className="var-code">{`{${key}}`}</code>
              <span className="small">{what}</span>
              <span className="small dim">{where}</span>
            </div>
          ))}
        </div>
      </Section>
    </>
  );
}

const CATEGORY_ORDER = ["knowledge", "lead", "call control", "link", "cart", "disposition", "support"];

const TOOL_FILTERS = [
  { id: "all", label: "All", test: () => true },
  { id: "builtin", label: "Factory", test: (t) => t.kind === "builtin" },
  { id: "custom", label: "HTTP APIs", test: (t) => t.kind === "custom" },
  { id: "mcp", label: "MCP servers", test: (t) => t.kind === "mcp" },
  { id: "on", label: "Switched on", test: (t, on) => on },
];

function ToolsTab({ draft, set, catalog, onOwnSettings }) {
  const defaults = useGlobalDefaults();
  const [nudge, setNudge] = useState(null);
  const enabled = new Set(draft.tools);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const allUsable = catalog.filter((t) => t.voice_eligible || t.kind !== "builtin");
  const passes = (t) => (TOOL_FILTERS.find((f) => f.id === filter) || TOOL_FILTERS[0]).test(t, enabled.has(t.name))
    && (!q || `${t.name} ${t.description}`.toLowerCase().includes(q));
  const usable = allUsable.filter(passes);
  const groups = {};
  for (const t of usable) {
    const g = t.kind === "mcp" ? "MCP servers" : t.kind === "custom" ? "Your HTTP APIs" : t.category || "other";
    (groups[g] ||= []).push(t);
  }
  const tail = ["Your HTTP APIs", "MCP servers"];
  const order = [
    ...CATEGORY_ORDER.filter((c) => groups[c]),
    ...Object.keys(groups).filter((g) => !CATEGORY_ORDER.includes(g) && !tail.includes(g)),
    ...tail.filter((g) => groups[g]),
  ];
  const toggle = (name, on) => {
    set("tools", on ? [...draft.tools, name] : draft.tools.filter((t) => t !== name));
    const group = OWN_SETTINGS.find((g) => g.tools.includes(name));
    if (on && group && !ownGroupSet(group, draft.overrides)) setNudge(group);
    if (!on && nudge && nudge.tools.includes(name)) setNudge(null);
  };
  const missing = draft.tools.filter((t) => !allUsable.some((u) => u.name === t));

  return (
    <Section title="Tools" subtitle="What this agent is allowed to do. It only ever sees the tools switched on here."
      aside={<span className="row" style={{ gap: 6 }}><Dirty paths={["tools"]} /><Link to="/tools" className="btn btn-sm"><Wrench size={13} /> Manage tools</Link></span>}>
      {!catalog.length && <div className="notice warn"><Alert size={15} /><span>The tool catalog couldn't be loaded from the brain.</span></div>}
      {nudge && (
        <div className="notice own-nudge">
          <Sparkle size={15} />
          <span>
            <strong>{nudge.title} for this agent.</strong> Until you set its own values it uses {nudge.uses(defaults)} from Settings.
          </span>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => { setNudge(null); onOwnSettings?.(); }}>Set this agent's values</button>
          <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label="Dismiss" onClick={() => setNudge(null)}><X size={13} /></button>
        </div>
      )}
      {catalog.length > 0 && (
        <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
          <div className="toolviews" role="tablist" aria-label="Filter tools" style={{ margin: 0 }}>
            {TOOL_FILTERS.map((f) => (
              <button key={f.id} type="button" role="tab" aria-selected={filter === f.id}
                className={`toolview ${filter === f.id ? "on" : ""}`} onClick={() => setFilter(f.id)}>
                {f.label}
              </button>
            ))}
          </div>
          <span className="grow" />
          <div className="searchbar" style={{ maxWidth: 240 }}>
            <Search size={14} />
            <input className="searchinput" placeholder="Search tools" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
        </div>
      )}
      {catalog.length > 0 && usable.length === 0 && (
        <p className="hint" style={{ margin: 0 }}>
          {filter === "mcp" ? "No MCP server yet. Add one on the Tools page." : filter === "custom" ? "No HTTP API tool yet. Add one on the Tools page." : "Nothing matches."}
        </p>
      )}
      {missing.length > 0 && (
        <div className="notice warn"><Alert size={15} /><span>Not in the catalog any more: {missing.join(", ")}. Saving will fail until they're removed.</span>
          <button className="btn btn-sm" onClick={() => set("tools", draft.tools.filter((t) => !missing.includes(t)))}>Remove</button></div>
      )}
      {order.map((group) => (
        <div key={group} className="stack" style={{ gap: 8 }}>
          <div className="toolgroup-title">{group}</div>
          {groups[group].map((t) => {
            const on = enabled.has(t.name);
            const off = t.enabled === false;
            const exposed = t.kind === "mcp" ? (t.tools || []).filter((x) => x.exposed) : [];
            return (
              <div key={t.name} className={`toolrow ${on ? "on" : ""}`} style={{ opacity: off ? 0.65 : 1 }}>
                <span className="toolrow-icon">{t.kind === "mcp" ? <Server size={15} /> : <Wrench size={15} />}</span>
                <div style={{ minWidth: 0 }}>
                  <div className="row" style={{ gap: 8 }}>
                    <span className="toolrow-name">{t.name}</span>
                    {t.kind === "custom" && <Badge tone="brand">HTTP</Badge>}
                    {t.kind === "mcp" && <Badge tone="violet">MCP · {exposed.length} tool{exposed.length === 1 ? "" : "s"}</Badge>}
                    {t.name === SWITCH_TOOL && <Badge>linked to language switching</Badge>}
                    {off && <Badge tone="warn">switched off on the Tools page</Badge>}
                  </div>
                  <div className="toolrow-desc">{t.description}</div>
                  {t.kind === "mcp" && exposed.length > 0 && (
                    <div className="mcp-chips">{exposed.map((x) => <code key={x.name}>{x.name}</code>)}</div>
                  )}
                </div>
                <Toggle checked={on} onChange={(v) => toggle(t.name, v)} label={`Enable ${t.name}`} />
              </div>
            );
          })}
        </div>
      ))}
    </Section>
  );
}

function GuardrailsTab({ draft, set }) {
  const { can } = useAuth();
  const g = draft.guardrails;
  const attached = g.library || [];
  const [library, setLibrary] = useState(null);

  const loadLibrary = useCallback(() => api.guardrails().then((r) => setLibrary(r.guardrails || [])).catch(() => setLibrary([])), []);
  useEffect(() => { loadLibrary(); }, [loadLibrary]);

  const toggle = (id, on) => set("guardrails.library", on ? [...attached, id] : attached.filter((x) => x !== id));
  const missing = attached.filter((id) => library && !library.some((x) => x.id === id));
  const escalates = (library || []).some((x) => attached.includes(x.id) && x.kind === "escalation");
  const refusalBrief = useMemo(() => ({
    blocked_topics: (library || []).filter((x) => attached.includes(x.id) && x.kind === "blocked_topic")
      .map((x) => (x.description ? `${x.name}: ${x.description}` : x.name)),
  }), [library, attached]);

  return (
    <>
      <Section title="Attached guardrails"
        subtitle="Pick from the shared library. Each one comes with its own description and phrases, and edits on the Guardrails page apply here too."
        aside={<div className="row" style={{ gap: 6 }}>
          <Dirty paths={["guardrails.library"]} />
          <Link to="/guardrails" className="btn btn-sm"><Shield size={13} /> Library</Link>
        </div>}>
        {!library ? <Skeleton h={120} /> : library.length === 0 ? (
          <Empty icon={<Shield size={20} />} title="The library is empty">Create guardrails on the Guardrails page, then switch them on here.</Empty>
        ) : Object.entries(KINDS).map(([kind, meta]) => {
          const rows = library.filter((x) => x.kind === kind);
          if (!rows.length) return null;
          return (
            <div key={kind} className="stack" style={{ gap: 8 }}>
              <div className="toolgroup-title">{meta.plural}</div>
              {rows.map((x) => {
                const on = attached.includes(x.id);
                return (
                  <div key={x.id} className={`toolrow ${on ? "on" : ""}`} style={{ opacity: x.enabled ? 1 : 0.6 }}>
                    <span className="toolrow-icon"><Shield size={15} /></span>
                    <div style={{ minWidth: 0 }}>
                      <div className="row" style={{ gap: 8 }}>
                        <span style={{ fontWeight: 650, fontSize: 13 }}>{x.name}</span>
                        {!x.enabled && <Badge tone="warn">switched off in library</Badge>}
                      </div>
                      <div className="toolrow-desc">{x.description || (x.phrases.length ? x.phrases.map((p) => `“${p}”`).join(", ") : "")}</div>
                    </div>
                    <Toggle checked={on} onChange={(v) => toggle(x.id, v)} label={`Attach ${x.name}`} />
                  </div>
                );
              })}
            </div>
          );
        })}
        {missing.length > 0 && (
          <div className="notice warn"><Alert size={15} /><span>No longer in the library: {missing.join(", ")}.</span>
            <button type="button" className="btn btn-sm" onClick={() => set("guardrails.library", attached.filter((id) => !missing.includes(id)))}>Remove</button></div>
        )}
        {escalates && !draft.tools.includes("voice_transfer_to_agent") && (
          <div className="notice warn"><Alert size={15} /><span>An escalation is attached but voice_transfer_to_agent is off in Tools, so the agent can only say a colleague will follow up.</span></div>
        )}
      </Section>

      <Section title="Scope & refusal" subtitle="Keep the conversation on what this agent is for, and what it says when it declines.">
        <SwitchRow paths={["guardrails.stay_on_domain"]} title="Stay on domain" checked={g.stay_on_domain} onChange={(v) => set("guardrails.stay_on_domain", v)}>
          Politely decline anything unrelated to PlaceholderWorks and this agent's goal.
        </SwitchRow>
        <div className="form-grid">
          <PersonaText paths={["guardrails.refusal_line.hindi"]} label="Refusal line (Hindi)" value={g.refusal_line.hindi} onChange={(v) => set("guardrails.refusal_line.hindi", v)}
            vars={varSets(draft).refusal} variables={allVars(draft)} items={varItems(draft, "refusal")} persona={draft.persona} />
          <PersonaText paths={["guardrails.refusal_line.english"]} label="Refusal line (English)" value={g.refusal_line.english} onChange={(v) => set("guardrails.refusal_line.english", v)}
            vars={varSets(draft).refusal} variables={allVars(draft)} items={varItems(draft, "refusal")} persona={draft.persona} />
        </div>
        <LineSuggestions kind="refusal" draft={draft} set={set} extra={refusalBrief} />
      </Section>

      <Section title="Replies" subtitle="Personal data and length, applied to every reply this agent gives.">
        <SwitchRow paths={["guardrails.mask_pii"]} title="Mask personal data" checked={g.mask_pii} onChange={(v) => set("guardrails.mask_pii", v)}>
          Never reads back full phone numbers, emails or card numbers, only the last 4 digits.
        </SwitchRow>
        <div className="form-grid">
          <Field aside={<Dirty paths={["guardrails.max_reply_sentences"]} />} label="Max sentences per reply">
            <Slider min={1} max={10} value={g.max_reply_sentences} onChange={(v) => set("guardrails.max_reply_sentences", v)} />
          </Field>
          <Field aside={<Dirty paths={["guardrails.max_reply_chars"]} />} label="Max characters per reply">
            <Slider min={80} max={2000} step={20} value={g.max_reply_chars} onChange={(v) => set("guardrails.max_reply_chars", v)} />
          </Field>
        </div>
      </Section>

    </>
  );
}

const TTS_NAMES = { murf: "Murf", gemini: "Gemini", sarvam: "Sarvam", openai: "OpenAI" };

function VoiceTab({ draft, set, llm, voices, ttsDefault, problems }) {
  const providers = llm?.providers || [{ id: "groq", models: [] }];
  const provider = providers.find((p) => p.id === draft.llm.provider) || providers[0];
  const models = [...new Set([...(provider?.models || []), draft.llm.model].filter(Boolean))];
  const engine = draft.voice.tts_provider || ttsDefault;
  const cast = voices[engine]?.voices || [];
  const voice = draft.voice.voice_id || voices[engine]?.voice || "";
  const engines = Object.keys(TTS_NAMES).map((id) => ({
    value: id,
    label: `${TTS_NAMES[id]}${voices[id] && !voices[id].keySet ? " (no API key)" : ""}`,
  }));

  return (
    <>
      <Section title="Voice" subtitle="The TTS engine and voice this agent speaks with.">
        <div className="form-grid">
          <Field label="TTS engine">
            <Select value={engine} options={engines}
              onChange={(v) => { set("voice.tts_provider", v); set("voice.voice_id", voices[v]?.voice || ""); }} />
          </Field>
          <Field aside={<Dirty paths={["voice"]} />} label="Voice" hint={cast.length ? `${cast.length} voices available on ${TTS_NAMES[engine] || engine}.` : "Type the voice id."}>
            {cast.length ? (
              <Select value={voice} options={[...new Set([...cast, voice].filter(Boolean))]}
                onChange={(v) => { set("voice.tts_provider", engine); set("voice.voice_id", v); }} />
            ) : (
              <input className="input mono" value={voice} placeholder="voice id"
                onChange={(e) => { set("voice.tts_provider", engine); set("voice.voice_id", e.target.value); }} />
            )}
          </Field>
        </div>
      </Section>

      <Section title="Model" subtitle="The language model behind this agent's replies.">
        <div className="form-grid">
          <Field aside={<Dirty paths={["llm.provider", "llm.model"]} />} label="Provider">
            <Segmented value={draft.llm.provider} onChange={(v) => { set("llm.provider", v); set("llm.model", providers.find((p) => p.id === v)?.default || providers.find((p) => p.id === v)?.models?.[0] || ""); }}
              options={providers.map((p) => ({ value: p.id, label: p.id === "groq" ? "Groq" : p.id === "openai" ? "OpenAI" : p.id }))} />
          </Field>
          <Field aside={<Dirty paths={["llm.provider", "llm.model"]} />} label="Model" required error={problems.model}>
            <Select mono value={draft.llm.model} placeholder="Choose a model" options={models} onChange={(v) => set("llm.model", v)} />
          </Field>
          <Field aside={<Dirty paths={["llm.temperature"]} />} label="Temperature" hint="Lower is steadier and more literal; higher is more varied.">
            <Slider min={0} max={1.5} step={0.05} value={draft.llm.temperature} onChange={(v) => set("llm.temperature", v)} />
          </Field>
          <Field aside={<Dirty paths={["llm.max_tokens"]} />} label="Max tokens per reply" hint="Voice replies are short; 200 to 400 is typical.">
            <Slider min={50} max={2000} step={10} value={draft.llm.max_tokens} onChange={(v) => set("llm.max_tokens", v)} />
          </Field>
          <Field aside={<Dirty paths={["llm.reasoning_effort"]} />} label="Reasoning effort" hint="Groq reasoning models only. Higher thinks longer, and the caller waits.">
            <Segmented value={draft.llm.reasoning_effort} onChange={(v) => set("llm.reasoning_effort", v)}
              options={(llm?.reasoning_efforts || ["low", "medium", "high"]).map((r) => ({ value: r, label: r[0].toUpperCase() + r.slice(1) }))} />
          </Field>
          <Field aside={<Dirty paths={["history_limit"]} />} label="Conversation memory" hint="How many past messages the model sees each turn.">
            <Slider min={0} max={50} value={draft.history_limit} unit="msgs" onChange={(v) => set("history_limit", v)} />
          </Field>
        </div>
      </Section>
    </>
  );
}

const CHANNELS = [
  { id: "acefone", label: "Phone · Acefone", desc: "Outbound and inbound telephony." },
  { id: "website", label: "Website widget", desc: "The browser voice bot." },
];

function ChannelsTab({ draft, set, problems, onQms }) {
  const toggle = (id) => set("channels", draft.channels.includes(id) ? draft.channels.filter((c) => c !== id) : [...draft.channels, id]);
  const duration = draft.call.max_call_duration_secs;
  return (
    <>
      <Section title="Channels" subtitle="Where this agent may run. A channel's default, a QMS intake or the test pages can then pick it."
        aside={<Dirty paths={["channels"]} />}>
        <div className="chan-pick">
          {CHANNELS.map((c) => {
            const on = draft.channels.includes(c.id);
            return (
              <button type="button" key={c.id} className={`chan ${on ? "on" : ""}`} onClick={() => toggle(c.id)} aria-pressed={on}>
                <span className="chan-box">{on && <Check size={12} />}</span>
                <span><strong style={{ display: "block", fontSize: 13 }}>{c.label}</strong><span className="hint">{c.desc}</span></span>
              </button>
            );
          })}
        </div>
        {problems.channels && <p className="hint field-err">{problems.channels}</p>}
      </Section>

      <Section title="Call behaviour">
        <SwitchRow paths={["call.is_phone"]} title="Phone call behaviour" checked={draft.call.is_phone} onChange={(v) => set("call.is_phone", v)}>
          Phone pacing and hold lines, handoff to a human, and the call-length budget. Turn on for telephony agents.
        </SwitchRow>
        <div className="switchrow">
          <div className="switchrow-text">
            <strong>Call data</strong>
            <span>
              {(draft._qms || []).length
                ? <>Comes from {(draft._qms || []).map((i, n) => <span key={i.id}>{n > 0 && ", "}<strong>{i.name}</strong> ({(i.allFields || []).length} fields)</span>)}. Every field is told to the agent on the call, and the test pages ask for exactly these.</>
                : <>No QMS API is connected, so calls carry only the customer's name, number and reference.</>}
            </span>
          </div>
          {onQms && <button type="button" className="btn btn-sm" onClick={onQms}><Inbox size={13} /> QMS tab</button>}
        </div>
        <Field aside={<Dirty paths={["call.max_call_duration_secs"]} />} label="Maximum call length" hint="Wrap-up starts before this. Off uses the pipeline's limit.">
          <div className="row" style={{ gap: 14 }}>
            <Toggle checked={!!duration} onChange={(v) => set("call.max_call_duration_secs", v ? 300 : null)} label="Custom call length" />
            <div style={{ flex: 1 }}>
              <Slider min={60} max={1800} step={30} value={duration || 300} disabled={!duration}
                format={(v) => `${Math.floor(v / 60)}m ${String(v % 60).padStart(2, "0")}s`}
                onChange={(v) => set("call.max_call_duration_secs", v)} />
            </div>
          </div>
        </Field>
      </Section>
      <AgentOwnSettings draft={draft} set={set} />
    </>
  );
}

function PreviewTab({ slug, dirty }) {
  const [language, setLanguage] = useState("hindi");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const toast = useToast();

  useEffect(() => {
    setData(null);
    api.previewUsecase(slug, language).then(setData).catch((e) => setError(e.message));
  }, [slug, language]);

  return (
    <Section title="What the model receives" subtitle="The fully rendered prompt for a sample call, exactly as the brain builds it."
      aside={<Segmented size="sm" value={language} onChange={setLanguage} options={[{ value: "hindi", label: "Hindi" }, { value: "english", label: "English" }]} />}>
      {dirty && <div className="notice warn"><Alert size={15} /><span>Showing the saved version. Save to preview your changes.</span></div>}
      {error && <div className="notice halt"><Alert size={15} /><span>{error}</span></div>}
      {!data && !error && <Skeleton h={300} r={9} />}
      {data && (
        <>
          <Field label="Greeting"><div className="preview-pre">{data.greeting || "None set. The model opens the call."}</div></Field>
          <Field label="System prompt" aside={
            <button className="btn btn-ghost btn-xs" onClick={() => { navigator.clipboard?.writeText(data.system_prompt); toast.ok("Copied"); }}><Copy size={12} /> Copy</button>}>
            <div className="preview-pre">{data.system_prompt}</div>
          </Field>
          <Field label="Per-turn context (sample)"><div className="preview-pre">{data.context_block}</div></Field>
          <Field label="Tools offered"><div className="var-chips">{(data.tools || []).map((t) => <span key={t} className="tag mono">{t}</span>)}</div></Field>
        </>
      )}
    </Section>
  );
}


function GlobalsDialog({ initial, onClose, onSaved }) {
  const toast = useToast();
  const [rows, setRows] = useState(() => initial.map((g) => ({ key: g.key, value: g.value || "", description: g.description || "" })));
  const [busy, setBusy] = useState(false);
  const update = (i, patch) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const keys = rows.map((r) => r.key);
  const errorFor = (r, i) => {
    if (!/^[a-z][a-z0-9_]{1,40}$/.test(r.key)) return "2–41 lowercase letters, digits or underscores";
    if (RESERVED.has(r.key)) return "That name is built in";
    if (keys.indexOf(r.key) !== i) return "Already defined";
    return "";
  };
  const valid = rows.every((r, i) => !errorFor(r, i));

  const save = async () => {
    setBusy(true);
    try {
      await api.saveGlobals(rows);
      toast.ok("Global variables saved. Every agent uses them from its next call.");
      onSaved();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open title="Global variables" width={820} onClose={onClose}
      subtitle="Available to every agent as {name}. An agent's own variable with the same name wins for that agent."
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={save} disabled={busy || !valid}>{busy ? "Saving…" : "Save for every agent"}</button>
      </>}>
      <div className="var-table">
        <div className="var-row var-head g"><span>Name</span><span>Value</span><span>Description</span><span /></div>
        {rows.map((r, i) => {
          const err = r.key ? errorFor(r, i) : "Give it a name";
          return (
            <div key={i} className="var-row g">
              <div>
                <div className={`var-key ${err ? "err" : ""}`}>
                  <span>{"{"}</span>
                  <input value={r.key} placeholder="helpline" aria-label="Variable name"
                    onChange={(e) => update(i, { key: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })} />
                  <span>{"}"}</span>
                </div>
                {err && <div className="hint field-err">{err}</div>}
              </div>
              <AutoTextarea value={r.value} placeholder="1800-103-xxxx" aria-label="Value" onChange={(e) => update(i, { value: e.target.value })} />
              <AutoTextarea value={r.description} placeholder="What it is" aria-label="Description" onChange={(e) => update(i, { description: e.target.value })} />
              <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label={`Remove ${r.key || "variable"}`}
                onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}><Trash size={13} /></button>
            </div>
          );
        })}
      </div>
      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        <button className="btn btn-sm" onClick={() => setRows((rs) => [...rs, { key: "", value: "", description: "" }])}><Plus size={13} /> Add variable</button>
        {GLOBAL_SUGGESTIONS.filter((g) => !keys.includes(g.key)).map((g) => (
          <button key={g.key} className="btn btn-ghost btn-sm" onClick={() => setRows((rs) => [...rs, { ...g }])}>+ {`{${g.key}}`}</button>
        ))}
      </div>
    </Modal>
  );
}

const GLOBAL_SUGGESTIONS = [
  { key: "helpline", value: "", description: "Customer care number" },
  { key: "website", value: "www.placeholderworks.com", description: "Website to send customers to" },
  { key: "support_email", value: "", description: "Customer care email" },
  { key: "brand_tagline", value: "", description: "One line about the company" },
];

const OWN_SETTINGS = [
  { id: "discount", title: "Retention discount", tools: ["voice_apply_discount"],
    fields: ["retention_discount_percent", "retention_discount_min_inr", "retention_discount_max_inr"],
    uses: (d) => `${d.RETENTION_DISCOUNT_PERCENT ?? "3"}% of the cart, at least ₹${d.RETENTION_DISCOUNT_MIN_INR ?? "200"} and at most ₹${d.RETENTION_DISCOUNT_MAX_INR ?? "1000"}` },
  { id: "whatsapp", title: "WhatsApp message", tools: ["voice_share_booking_link", "voice_offer_booking_link"],
    fields: ["whatsapp_event_name", "whatsapp_template_name"],
    uses: (d) => `the "${d.VOICE_WHATSAPP_EVENT_NAME || "abandoned_cart_booking_link"}" message` },
  { id: "transfer", title: "Transfer number", tools: ["voice_transfer_to_agent"],
    fields: ["transfer_number"],
    uses: (d) => `the line ${d.CALL_TRANSFER_NUMBER || "set in Settings"}` },
];
const ownGroupOn = (group, tools) => group.tools.some((t) => tools.has(t));
const ownGroupSet = (group, own) => group.fields.some((f) => own?.[f] !== null && own?.[f] !== undefined && own?.[f] !== "");

function useGlobalDefaults() {
  const [defaults, setDefaults] = useState({});
  useEffect(() => {
    const pick = (data) => Object.fromEntries(Object.entries(data?.values || {}).map(([k, v]) => [k, v?.value ?? ""]));
    Promise.all([api.brainSettings().catch(() => null), api.settings().catch(() => null)])
      .then(([brain, pipeline]) => setDefaults({ ...pick(pipeline), ...pick(brain) }));
  }, []);
  return defaults;
}

function AgentOwnSettings({ draft, set }) {
  const defaults = useGlobalDefaults();
  const own = draft.overrides || {};
  const tools = new Set(draft.tools || []);
  const shown = Object.fromEntries(OWN_SETTINGS.map((g) => [g.id, ownGroupOn(g, tools)]));
  if (!Object.values(shown).some(Boolean)) return null;
  const num = (path) => (e) => set(path, e.target.value === "" ? null : Number(e.target.value));
  const text = (path) => (e) => set(path, e.target.value);
  const fallback = (key) => (defaults[key] === undefined ? "Settings default" : defaults[key] === "" ? "none (default)" : `${defaults[key]} (default)`);

  return (
    <Section title="This agent's settings" aside={<Dirty paths={["overrides"]} />}
      subtitle="Values the tools switched on for this agent use. Empty uses the value from Settings, shown greyed in each box.">
      <div className="own-grid" id="own-settings">
        {shown.discount && <div className="own-block">
          <div className="own-head"><strong>Retention discount</strong><span className="tiny faint">What this agent may take off when a customer hesitates on price.</span></div>
          <div className="own-fields">
            <Field label="Discount">
              <div className="numwrap"><input className="input mono" type="number" min="0" max="50" step="0.5" value={own.retention_discount_percent ?? ""}
                placeholder={fallback("RETENTION_DISCOUNT_PERCENT")} onChange={num("overrides.retention_discount_percent")} /><span className="numunit mono">%</span></div>
            </Field>
            <Field label="Floor">
              <div className="numwrap"><input className="input mono" type="number" min="0" step="50" value={own.retention_discount_min_inr ?? ""}
                placeholder={fallback("RETENTION_DISCOUNT_MIN_INR")} onChange={num("overrides.retention_discount_min_inr")} /><span className="numunit mono">₹</span></div>
            </Field>
            <Field label="Ceiling">
              <div className="numwrap"><input className="input mono" type="number" min="0" step="50" value={own.retention_discount_max_inr ?? ""}
                placeholder={fallback("RETENTION_DISCOUNT_MAX_INR")} onChange={num("overrides.retention_discount_max_inr")} /><span className="numunit mono">₹</span></div>
            </Field>
          </div>
        </div>}

        {shown.whatsapp && <div className="own-block">
          <div className="own-head"><strong>WhatsApp message</strong><span className="tiny faint">Which message the WhatsApp service sends for this agent's booking link.</span></div>
          <div className="own-fields two">
            <Field label="Event name">
              <input className="input mono" value={own.whatsapp_event_name || ""} placeholder={fallback("VOICE_WHATSAPP_EVENT_NAME")} onChange={text("overrides.whatsapp_event_name")} />
            </Field>
            <Field label="Template name">
              <input className="input mono" value={own.whatsapp_template_name || ""} placeholder={fallback("VOICE_WHATSAPP_TEMPLATE_NAME")} onChange={text("overrides.whatsapp_template_name")} />
            </Field>
          </div>
        </div>}

        {shown.transfer && <div className="own-block">
          <div className="own-head"><strong>Transfer to a human</strong><span className="tiny faint">The team line this agent hands calls to. Live calls shows them on this line.</span></div>
          <div className="own-fields two">
            <Field label="Transfer number">
              <input className="input mono" inputMode="tel" value={own.transfer_number || ""} placeholder={fallback("CALL_TRANSFER_NUMBER")} onChange={text("overrides.transfer_number")} />
            </Field>
          </div>
        </div>}
      </div>
    </Section>
  );
}
