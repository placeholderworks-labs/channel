import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Alert, Pencil, Plus, Search, Shield, Trash, X } from "../components/Icons";
import { Badge, Confirm, Empty, Field, Modal, PageHeader, Segmented, Skeleton, TagInput, Toggle, AutoTextarea } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { relativeTime } from "../lib/format";
import { useToast } from "../lib/toast";
import { slugify } from "./UseCases";

export const KINDS = {
  blocked_topic: {
    label: "Blocked topic",
    plural: "Blocked topics",
    tone: "halt",
    blurb: "The agent never discusses it and answers with the agent's refusal line.",
    phrasesLabel: "How a customer might bring it up",
    phrasesHint: "Optional examples that help the model recognise the topic. Not matched literally.",
    namePlaceholder: "Competitor prices",
    descPlaceholder: "Prices or offers from other AI agencies or vendors. Never compare PlaceholderWorks with a competitor.",
    examples: ["doosri agency sasta bana degi", "what does another vendor charge"],
  },
  banned_phrase: {
    label: "Banned phrase",
    plural: "Banned phrases",
    tone: "warn",
    blurb: "Exact wording the agent must never say. A sentence containing one is never spoken.",
    phrasesLabel: "Exact phrases",
    phrasesHint: "Matched literally, ignoring case. Add the Hindi form too, since the agent speaks Hindi in Devanagari.",
    namePlaceholder: "Price or timeline promises",
    descPlaceholder: "Every project is scoped after Discovery, so the agent must never promise a price or a date.",
    examples: ["guaranteed delivery date", "fixed price", "पक्की deadline"],
  },
  escalation: {
    label: "Escalation",
    plural: "Escalations",
    tone: "brand",
    blurb: "When this comes up the agent offers a human, and transfers if the agent has the transfer tool.",
    phrasesLabel: "How a customer might say it",
    phrasesHint: "Optional examples that help the model recognise the situation.",
    namePlaceholder: "Production system is down",
    descPlaceholder: "A client reports that a live agent or bot built by the team has stopped working.",
    examples: ["hamara bot kaam nahi kar raha", "the calling agent is down"],
  },
};

const BLANK = { id: "", name: "", kind: "blocked_topic", description: "", phrases: [], enabled: true };

const PLATFORM = [
  ["Leaked tool calls & JSON", "A line that looks like a tool call, tool name or JSON arguments is muted before it reaches the voice."],
  ["Stage notes & tags", "Bracketed notes, <tags> and stage directions are never spoken."],
  ["Leaked reasoning", "Phrases like “according to the guidelines” or “the assistant” are muted."],
  ["Unfilled placeholders", "A reply still carrying {PLACEHOLDER} text is muted instead of read out."],
  ["Spoken-text sanitiser", "Strips invisible characters, raw timestamps and currency symbols; spells digits in Hindi."],
  ["Duplicate speech", "The same line is never spoken twice in a row."],
];

export default function Guardrails() {
  const { can } = useAuth();
  const toast = useToast();
  const [list, setList] = useState(null);
  const [usecases, setUsecases] = useState([]);
  const [error, setError] = useState("");
  const [kind, setKind] = useState("all");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(null);
  const [del, setDel] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [g, u] = await Promise.all([api.guardrails(), api.usecases().catch(() => ({ usecases: [] }))]);
      setList(g.guardrails || []);
      setUsecases(u.usecases || []);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const nameOf = (slug) => usecases.find((u) => u.slug === slug)?.name || slug;
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (list || [])
      .filter((g) => kind === "all" || g.kind === kind)
      .filter((g) => !q || `${g.name} ${g.description} ${g.phrases.join(" ")}`.toLowerCase().includes(q));
  }, [list, kind, query]);
  const count = (k) => (list || []).filter((g) => g.kind === k).length;

  const toggle = async (g, enabled) => {
    try {
      await api.updateGuardrail(g.id, { enabled });
      toast.ok(`${g.name} ${enabled ? "switched on" : "switched off"} everywhere it is used`);
      load();
    } catch (e) {
      toast.error(e.message);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await api.deleteGuardrail(del.id);
      toast.ok(`${del.name} deleted`);
      setDel(null);
      load();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page wide">
      <PageHeader
        eyebrow="Build"
        title="Guardrails"
        subtitle="Create a guardrail once, with a name, a description and example phrases, then attach it to any agent on its Guardrails tab. Editing it here updates every agent that uses it."
        actions={can("usecases.edit") && (
          <button className="btn btn-primary btn-sm" onClick={() => setEditing({ ...BLANK })}><Plus size={14} /> New guardrail</button>
        )}
      />

      {error && <div className="notice halt" style={{ marginBottom: 16 }}><Alert size={15} /><span>{error}</span></div>}

      <div className="gr-kinds">
        {Object.entries(KINDS).map(([k, meta]) => (
          <button key={k} className={`gr-kind ${kind === k ? "on" : ""}`} onClick={() => setKind(kind === k ? "all" : k)}>
            <span className={`gr-kind-dot k-${meta.tone}`} />
            <span style={{ minWidth: 0 }}>
              <strong>{meta.plural} <span className="faint">{list ? count(k) : "-"}</span></strong>
              <span>{meta.blurb}</span>
            </span>
          </button>
        ))}
      </div>

      <div className="row" style={{ gap: 12, margin: "18px 0 14px", flexWrap: "wrap" }}>
        <Segmented size="sm" value={kind} onChange={setKind} options={[
          { value: "all", label: `All ${list?.length ?? ""}` },
          ...Object.entries(KINDS).map(([k, m]) => ({ value: k, label: m.plural })),
        ]} />
        <div className="searchbar" style={{ maxWidth: 300, flex: 1 }}>
          <Search size={15} />
          <input className="searchinput" placeholder="Search guardrails" value={query} onChange={(e) => setQuery(e.target.value)} />
          {query && <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setQuery("")} aria-label="Clear"><X size={13} /></button>}
        </div>
      </div>

      {!list && !error ? <Skeleton h={260} r={12} /> : shown.length === 0 ? (
        <div className="card">
          <Empty icon={<Shield size={20} />} title={list?.length ? "Nothing matches" : "No guardrails yet"}
>
            {list?.length ? "Try another filter or search." : "A guardrail is a rule you write once and attach to any agent. Use New guardrail above to create one."}
          </Empty>
        </div>
      ) : (
        <div className="gr-grid">
          {shown.map((g) => {
            const meta = KINDS[g.kind];
            return (
              <article key={g.id} className={`gr-card ${g.enabled ? "" : "off"}`}>
                <header className="gr-card-head">
                  <Badge tone={meta.tone}>{meta.label}</Badge>
                  <span className="grow" />
                  {can("usecases.edit") && <Toggle size="sm" checked={g.enabled} onChange={(v) => toggle(g, v)} label="Enabled" />}
                </header>
                <h3>{g.name}</h3>
                <p className="gr-desc">{g.description || <span className="faint">No description</span>}</p>
                {g.phrases.length > 0 && (
                  <div className="var-chips">
                    {g.phrases.slice(0, 6).map((p) => <span key={p} className="tag">{p}</span>)}
                    {g.phrases.length > 6 && <span className="tiny faint">+{g.phrases.length - 6} more</span>}
                  </div>
                )}
                <footer className="gr-card-foot">
                  <span className="ellipsis">
                    {g.used_by?.length
                      ? <>Used by {g.used_by.map((s, i) => <span key={s}>{i > 0 && ", "}<Link to={`/agents/${s}`}>{nameOf(s)}</Link></span>)}</>
                      : <span className="faint">Not attached to any agent</span>}
                  </span>
                  <span className="grow" />
                  <span className="tiny faint">{relativeTime(g.updated_at)}</span>
                  {can("usecases.edit") && (
                    <button className="btn btn-ghost btn-icon btn-xs" onClick={() => setEditing({ ...g })} aria-label={`Edit ${g.name}`}><Pencil size={13} /></button>
                  )}
                  {can("usecases.delete") && (
                    <button className="btn btn-ghost btn-icon btn-xs" onClick={() => setDel(g)} aria-label={`Delete ${g.name}`}><Trash size={13} /></button>
                  )}
                </footer>
              </article>
            );
          })}
        </div>
      )}

      <div className="section" style={{ marginTop: 22 }}>
        <div className="section-head">
          <div style={{ flex: 1 }}>
            <h3>Platform rules</h3>
            <p>Always on for every agent and channel. Enforced on the reply after the model and before the voice.</p>
          </div>
          <Badge tone="ok" dot>enforced</Badge>
        </div>
        <div className="section-body" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10 }}>
          {PLATFORM.map(([title, body]) => (
            <div key={title} className="switchrow" style={{ alignItems: "flex-start" }}>
              <span className="toolrow-icon" style={{ background: "var(--ok-wash)", color: "var(--ok)" }}><Shield size={15} /></span>
              <div className="switchrow-text"><strong>{title}</strong><span>{body}</span></div>
            </div>
          ))}
        </div>
      </div>

      {editing && <GuardrailEditor initial={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}

      <Confirm open={!!del} danger busy={busy} title={`Delete ${del?.name}?`} confirmLabel="Delete guardrail"
        body={del?.used_by?.length
          ? <>It's attached to <strong>{del.used_by.map(nameOf).join(", ")}</strong>. Detach it there first, or switch it off here to pause it everywhere.</>
          : "No agent uses it. This can't be undone."}
        onConfirm={remove} onClose={() => setDel(null)} />
    </div>
  );
}

export function GuardrailEditor({ initial, onClose, onSaved }) {
  const toast = useToast();
  const isNew = !initial.id || initial._new;
  const [g, setG] = useState({ ...initial, phrases: [...(initial.phrases || [])] });
  const [idTouched, setIdTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const meta = KINDS[g.kind];

  const problems = [];
  if (!g.name.trim()) problems.push("Give it a name");
  if (isNew && !/^[a-z][a-z0-9_]{2,40}$/.test(g.id)) problems.push("Identifier: 3–41 lowercase letters, digits or underscores");
  if (g.kind === "banned_phrase" && !g.phrases.length) problems.push("Add at least one exact phrase");
  if (g.kind !== "banned_phrase" && !g.description.trim() && !g.phrases.length) problems.push("Describe it, or add example phrases");

  const save = async () => {
    setBusy(true);
    try {
      const body = { id: g.id, name: g.name.trim(), kind: g.kind, description: g.description.trim(), phrases: g.phrases, enabled: g.enabled };
      const saved = isNew ? await api.createGuardrail(body) : await api.updateGuardrail(g.id, body);
      toast.ok(isNew ? `${saved.name} created. Attach it from any agent` : `${saved.name} saved${saved.used_by?.length ? ` · ${saved.used_by.length} agent(s) updated` : ""}`);
      onSaved(saved);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open title={isNew ? "New guardrail" : `Edit ${initial.name}`} onClose={onClose} width={640}
      subtitle="Written once, attached to any agent. The description and phrases are what the agent is told."
      footer={<>
        <span className="row" style={{ gap: 8, marginRight: "auto" }}>
          <Toggle checked={g.enabled} onChange={(v) => setG({ ...g, enabled: v })} label="Enabled" />
          <span className="small">{g.enabled ? "On" : "Off everywhere"}</span>
        </span>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={save} disabled={busy || problems.length > 0} title={problems[0]}>
          {busy ? "Saving…" : isNew ? "Create guardrail" : "Save guardrail"}
        </button>
      </>}>
      <Field label="Type">
        <Segmented value={g.kind} onChange={(k) => setG({ ...g, kind: k })}
          options={Object.entries(KINDS).map(([k, m]) => ({ value: k, label: m.label }))} />
        <p className="hint" style={{ margin: 0 }}>{meta.blurb}</p>
      </Field>
      <div className="form-grid">
        <Field label="Name" required>
          <input className="input" value={g.name} placeholder={meta.namePlaceholder}
            onChange={(e) => setG({ ...g, name: e.target.value, id: isNew && !idTouched ? slugify(e.target.value) : g.id })} />
        </Field>
        <Field label="Identifier" hint={isNew ? "Fixed once created." : "Can't be changed."}>
          <input className="input mono" value={g.id} disabled={!isNew}
            onChange={(e) => { setIdTouched(true); setG({ ...g, id: slugify(e.target.value) }); }} />
        </Field>
      </div>
      <Field label="Description" required={g.kind !== "banned_phrase"}
        hint={g.kind === "banned_phrase" ? "Why these are banned. The agent is told the reason too." : "Explain it in a sentence or two: exactly what is covered and why. This is what the agent reads."}>
        <AutoTextarea minRows={2} value={g.description} placeholder={meta.descPlaceholder}
          onChange={(e) => setG({ ...g, description: e.target.value })} />
      </Field>
      <Field label={meta.phrasesLabel} required={g.kind === "banned_phrase"} hint={meta.phrasesHint}>
        <TagInput value={g.phrases} onChange={(v) => setG({ ...g, phrases: v })}
          placeholder={`e.g. ${meta.examples[0]}, then press Enter`} />
      </Field>
      <div className="gr-preview">
        <div className="eyebrow" style={{ marginBottom: 6 }}>The agent will read</div>
        <code>{previewLine(g)}</code>
      </div>
      {problems.length > 0 && <p className="hint" style={{ margin: 0 }}>{problems[0]}.</p>}
    </Modal>
  );
}

function previewLine(g) {
  const name = g.name.trim() || "…";
  const desc = g.description.trim().replace(/\.$/, "");
  if (g.kind === "banned_phrase") {
    return `Never say: ${g.phrases.map((p) => `"${p}"`).join("; ") || "…"}.${desc ? ` Why: ${name}: ${desc}.` : ""}`;
  }
  const examples = g.phrases.length ? ` (the customer may put it as: ${g.phrases.slice(0, 8).map((p) => `"${p}"`).join(", ")})` : "";
  const lead = g.kind === "blocked_topic" ? "Never discuss" : "Offer a human agent when the customer raises";
  return `${lead}: ${name}${desc ? `: ${desc}` : ""}${examples}`;
}
