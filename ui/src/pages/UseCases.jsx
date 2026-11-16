import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Alert, Bot, Check, Copy, Plus, Refresh, Search, Trash, X } from "../components/Icons";
import { Badge, Confirm, Empty, Field, Modal, PageHeader, Segmented, Select, Skeleton, AutoTextarea } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { relativeTime } from "../lib/format";
import { useToast } from "../lib/toast";
import { SUGGESTED_VARIABLES } from "../lib/variables";
import useAutoHindi from "../lib/useAutoHindi";

export const STATUS_TONE = { active: "ok", draft: "warn", archived: "" };
const CHANNEL_LABEL = { acefone: "Phone · Acefone", website: "Website widget" };

export function channelLabel(id) {
  return CHANNEL_LABEL[id] || id;
}

export function initials(name = "") {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";
}

export default function UseCases({ startNew = false }) {
  const { can } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [del, setDel] = useState(null);
  const [busy, setBusy] = useState(false);
  const [defaultsOpen, setDefaultsOpen] = useState(false);
  const [creating, setCreating] = useState(startNew);

  const load = useCallback(async () => {
    try {
      setData(await api.usecases());
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const list = useMemo(() => {
    const all = data?.usecases || [];
    const q = query.trim().toLowerCase();
    return all
      .filter((u) => filter === "all" || u.status === filter)
      .filter((u) => !q || `${u.name} ${u.slug} ${u.description}`.toLowerCase().includes(q))
      .sort((a, b) => (a.status === "archived") - (b.status === "archived") || a.name.localeCompare(b.name));
  }, [data, filter, query]);

  const defaults = data?.defaults || {};
  const defaultFor = (slug) => Object.entries(defaults).filter(([, s]) => s === slug).map(([c]) => c);
  const counts = useMemo(() => {
    const all = data?.usecases || [];
    return { all: all.length, active: all.filter((u) => u.status === "active").length,
      draft: all.filter((u) => u.status === "draft").length, archived: all.filter((u) => u.status === "archived").length };
  }, [data]);

  const remove = async () => {
    setBusy(true);
    try {
      await api.deleteUsecase(del.slug);
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
        title="Agents"
        subtitle="Each agent is complete on its own: its prompt, greeting, tools, guardrails, voice and the channels it runs on. Calls pick one by channel default or by naming it."
        actions={
          <>
            <button className="btn btn-sm" onClick={load}><Refresh size={14} /> Refresh</button>
            {can("usecases.edit") && (
              <button className="btn btn-sm" onClick={() => setDefaultsOpen(true)} disabled={!data}>Channel defaults</button>
            )}
            {can("usecases.edit") && (
              <button className="btn btn-primary btn-sm" onClick={() => setCreating(true)}><Plus size={14} /> New agent</button>
            )}
          </>
        }
      />

      {error && (
        <div className="notice halt" style={{ marginBottom: 16 }}>
          <Alert size={15} /><span>{error}</span>
        </div>
      )}

      <div className="row" style={{ gap: 12, marginBottom: 18, flexWrap: "wrap" }}>
        <Segmented
          size="sm"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: `All ${counts.all}` },
            { value: "active", label: `Active ${counts.active}` },
            { value: "draft", label: `Draft ${counts.draft}` },
            { value: "archived", label: `Archived ${counts.archived}` },
          ]}
        />
        <div className="searchbar" style={{ maxWidth: 300, flex: 1 }}>
          <Search size={15} />
          <input className="searchinput" placeholder="Search agents" value={query} onChange={(e) => setQuery(e.target.value)} />
          {query && <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setQuery("")} aria-label="Clear"><X size={13} /></button>}
        </div>
      </div>

      {!data && !error ? (
        <div className="uc-grid">
          {[0, 1, 2].map((i) => <Skeleton key={i} h={200} r={12} />)}
        </div>
      ) : list.length === 0 && data ? (
        <div className="card">
          <Empty icon={<Bot size={22} />} title={query || filter !== "all" ? "Nothing matches" : "No agents yet"}>
            {query || filter !== "all" ? "Try another filter or search." : "An agent answers calls on a phone line or the website. Use New agent above to create one."}
          </Empty>
        </div>
      ) : (
        <div className="uc-grid">
          {list.map((u) => (
            <div key={u.slug} className="uc-card" role="button" tabIndex={0}
              onClick={() => navigate(`/agents/${u.slug}`)}
              onKeyDown={(e) => e.key === "Enter" && navigate(`/agents/${u.slug}`)}>
              <div className="uc-card-top">
                <span className={`uc-icon ${u.status}`}>{initials(u.name)}</span>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div className="uc-name">{u.name}</div>
                  <div className="uc-slug">{u.slug}</div>
                </div>
                <Badge tone={STATUS_TONE[u.status]} dot>{u.status}</Badge>
              </div>
              <div className="uc-desc">{u.description || <span className="faint">No description</span>}</div>
              <div className="uc-meta">
                {(u.channels || []).map((c) => <Badge key={c}>{channelLabel(c)}</Badge>)}
                {defaultFor(u.slug).map((c) => <Badge key={`d-${c}`} tone="brand">Default · {c}</Badge>)}
                {u.builtin && <Badge tone="brand">Built-in</Badge>}
              </div>
              <div className="uc-foot">
                <span>{(u.tools || []).length} tools</span>
                <span>·</span>
                <span>v{u.version}</span>
                <span>·</span>
                <span className="ellipsis">{relativeTime(u.updated_at)}{u.updated_by ? ` by ${u.updated_by}` : ""}</span>
                <span className="grow" />
                {can("usecases.delete") && !u.builtin && (
                  <button className="btn btn-ghost btn-icon btn-xs" title="Delete" aria-label="Delete"
                    onClick={(e) => { e.stopPropagation(); setDel(u); }}>
                    <Trash size={13} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {creating && data && (
        <NewUseCaseDialog usecases={data.usecases || []} channels={data.channels || ["acefone", "website"]}
          onClose={() => { setCreating(false); if (startNew) navigate("/agents", { replace: true }); }}
          onDone={(slug) => navigate(`/agents/${slug}`)} />
      )}
      <Confirm
        open={!!del}
        danger
        busy={busy}
        title={`Delete ${del?.name}?`}
        confirmLabel="Delete agent"
        body={<>This removes <code>{del?.slug}</code> and its version history. Calls that name it will fall back to the channel default. Archive it instead if you might need it again.</>}
        onConfirm={remove}
        onClose={() => setDel(null)}
      />
      {data && (
        <DefaultsDialog open={defaultsOpen} data={data} onClose={() => setDefaultsOpen(false)} onSaved={load} />
      )}
    </div>
  );
}

export function slugify(text) {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").replace(/^(\d)/, "uc_$1").slice(0, 40);
}

function DefaultsDialog({ open, data, onClose, onSaved }) {
  const toast = useToast();
  const [draft, setDraft] = useState(data.defaults || {});
  const [busy, setBusy] = useState(false);

  useEffect(() => setDraft(data.defaults || {}), [data, open]);

  const save = async () => {
    setBusy(true);
    try {
      await api.setUsecaseDefaults(draft);
      toast.ok("Channel defaults saved. The next call uses them");
      onSaved();
      onClose();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Channel defaults" width={520}
      subtitle="The agent a channel runs when the call or QMS record doesn't name one."
      footer={<><button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save defaults"}</button></>}>
      {(data.channels || []).map((channel) => {
        const options = (data.usecases || [])
          .filter((u) => u.status !== "archived" && (u.channels || []).includes(channel))
          .map((u) => ({ value: u.slug, label: `${u.name} (${u.slug})${u.status === "draft" ? " (draft)" : ""}` }));
        return (
          <Field key={channel} label={channelLabel(channel)} hint={options.length ? "" : "No agent is enabled for this channel yet."}>
            <Select value={draft[channel]} onChange={(v) => setDraft({ ...draft, [channel]: v })} options={options} />
          </Field>
        );
      })}
    </Modal>
  );
}

function NewUseCaseDialog({ usecases, channels, onClose, onDone }) {
  const toast = useToast();
  const [form, setForm] = useState({
    name: "", slug: "", description: "", channels: ["website"],
    agentName: "", agentNameHindi: "", vars: ["helpline", "website"],
  });
  const [slugTouched, setSlugTouched] = useState(false);
  const hindi = useAutoHindi(form.agentName, (v) => setForm((f) => ({ ...f, agentNameHindi: v })));
  const [busy, setBusy] = useState(false);
  const slugOk = /^[a-z][a-z0-9_]{2,40}$/.test(form.slug);
  const taken = usecases.some((u) => u.slug === form.slug);
  const valid = form.name.trim() && slugOk && !taken && form.channels.length > 0;

  const variables = SUGGESTED_VARIABLES.filter((v) => form.vars.includes(v.key)).map((v) => ({ ...v }));
  const persona = { agent_name: form.agentName.trim(), agent_name_hindi: form.agentNameHindi.trim(), company: "PlaceholderWorks" };

  const create = async () => {
    setBusy(true);
    try {
      {
        const options = await api.llmOptions().catch(() => null);
        await api.createUsecase({
          slug: form.slug,
          name: form.name.trim(),
          description: form.description.trim(),
          status: "draft",
          channels: form.channels,
          persona,
          variables,
          tools: ["voice_end_call", "voice_log_disposition"],
          llm: { provider: options?.default?.provider || "groq", model: options?.default?.model || "" },
          call: { is_phone: form.channels.includes("acefone"), needs_cart: false },
        });
      }
      toast.ok(`${form.name.trim()} created as a draft`);
      onDone(form.slug);
    } catch (e) {
      toast.error(e.message);
      setBusy(false);
    }
  };

  const toggleChannel = (id) =>
    setForm((f) => ({ ...f, channels: f.channels.includes(id) ? f.channels.filter((c) => c !== id) : [...f.channels, id] }));

  return (
    <Modal open title="New agent" width={560} onClose={onClose}
      subtitle="It's created as a blank draft, so you can write its prompt and test it before switching it on."
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={create} disabled={!valid || busy}>{busy ? "Creating…" : "Create agent"}</button>
      </>}>
      <Field label="Name" required hint="What your team calls this agent.">
        <input className="input" autoFocus value={form.name} placeholder="Demo request follow-up"
          onChange={(e) => setForm({ ...form, name: e.target.value, slug: slugTouched ? form.slug : slugify(e.target.value) })} />
      </Field>
      <Field label="Identifier" required
        error={form.slug && !slugOk ? "3–41 lowercase letters, digits or underscores, starting with a letter" : taken ? "An agent already uses this identifier" : ""}
        hint="QMS records and channel defaults refer to it. Can't be changed later.">
        <input className="input mono" value={form.slug} placeholder="demo_followup"
          onChange={(e) => { setSlugTouched(true); setForm({ ...form, slug: slugify(e.target.value) }); }} />
      </Field>
      <Field label="Description" hint="Optional: what this agent is for.">
        <AutoTextarea value={form.description} placeholder="Calls people who requested a demo on the website"
          onChange={(e) => setForm({ ...form, description: e.target.value })} />
      </Field>
      <div className="form-grid">
        <Field label="Agent name" hint="The name it introduces itself with. Optional.">
          <input className="input" value={form.agentName} placeholder="Priya" onChange={(e) => setForm({ ...form, agentName: e.target.value })} />
        </Field>
        <Field label="Agent name (Hindi)" hint={form.agentName.trim() ? hindi.hint : "Written for you from the name."}>
          <input className="input" value={form.agentNameHindi} placeholder="प्रिया"
            onChange={(e) => { hindi.markManual(); setForm({ ...form, agentNameHindi: e.target.value }); }} />
        </Field>
      </div>
      <Field label="Variables" hint="Pick the ones this agent needs. Pre-filled values can be changed later on its Variables tab.">
        <div className="var-picks">
          {SUGGESTED_VARIABLES.map((v) => {
            const on = form.vars.includes(v.key);
            return (
              <button type="button" key={v.key} className={`var-pick ${on ? "on" : ""}`} aria-pressed={on} title={v.description}
                onClick={() => setForm((f) => ({ ...f, vars: on ? f.vars.filter((k) => k !== v.key) : [...f.vars, v.key] }))}>
                <span className="chan-box">{on && <Check size={11} />}</span>
                <span className="mono">{`{${v.key}}`}</span>
                {v.value && <span className="var-pick-val">{v.value}</span>}
              </button>
            );
          })}
        </div>
      </Field>
      <Field label="Channels" required>
        <div className="chan-pick">
          {channels.map((id) => {
            const on = form.channels.includes(id);
            return (
              <button type="button" key={id} className={`chan ${on ? "on" : ""}`} onClick={() => toggleChannel(id)} aria-pressed={on}>
                <span className="chan-box">{on && <Check size={12} />}</span>
                <strong style={{ fontSize: 13 }}>{channelLabel(id)}</strong>
              </button>
            );
          })}
        </div>
      </Field>
    </Modal>
  );
}
