import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Chevron, Eye, Info, Refresh, Search, X } from "../components/Icons";
import { Badge, FieldActions, PageHeader, SecretInput, Segmented, Select, Skeleton, Slider, Toggle } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { relativeTime } from "../lib/format";
import { useToast } from "../lib/toast";

const CLEAR = "__clear__";

const STORES = {
  pipeline: { load: () => api.settings(), save: (v) => api.saveSettings(v, true), reset: (k) => api.resetSettings(k) },
  brain: { load: () => api.brainSettings(), save: (v) => api.saveBrainSettings(v), reset: (k) => api.resetBrainSettings(k) },
};

export default function Settings({ reload }) {
  const { can } = useAuth();
  const toast = useToast();
  const editable = can("settings.edit");
  const [stores, setStores] = useState({});
  const [errors, setErrors] = useState({});
  const [draft, setDraft] = useState({ pipeline: {}, brain: {} });
  const [active, setActive] = useState(null);
  const [query, setQuery] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    await Promise.all(
      Object.entries(STORES).map(async ([id, store]) => {
        try {
          const data = await store.load();
          setStores((s) => ({ ...s, [id]: data }));
          setErrors((e) => ({ ...e, [id]: "" }));
        } catch (e) {
          setErrors((er) => ({ ...er, [id]: e.message }));
        }
      })
    );
  }, []);

  useEffect(() => { load(); }, [load]);

  const nav = useMemo(() => {
    const out = [];
    for (const [storeId, data] of Object.entries(stores)) {
      for (const section of data.sections || []) {
        const label = storeId === "brain" ? "Brain" : section.name;
        for (const group of section.groups || []) {
          out.push({ id: `${storeId}:${group.id}`, storeId, section: label, group });
        }
      }
    }
    return out;
  }, [stores]);

  useEffect(() => {
    if (active || !nav.length) return;
    const wanted = new URLSearchParams(window.location.search).get("group");
    setActive((nav.find((n) => n.group.id === wanted) || nav[0]).id);
  }, [nav, active]);

  const dirtyCount = Object.values(draft).reduce((n, d) => n + Object.keys(d).length, 0);

  const save = async () => {
    setSaving(true);
    try {
      for (const [storeId, values] of Object.entries(draft)) {
        if (!Object.keys(values).length) continue;
        const r = await STORES[storeId].save(values);
        if (r?.restartRequired?.length) toast.ok(`Saved. Restart needed for: ${r.restartRequired.join(", ")}`);
      }
      toast.ok(`${dirtyCount} setting${dirtyCount === 1 ? "" : "s"} saved and applied`);
      setDraft({ pipeline: {}, brain: {} });
      await load();
      reload?.();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const [savingKey, setSavingKey] = useState("");

  const saveOne = async (storeId, key) => {
    setSavingKey(`${storeId}:${key}`);
    try {
      const r = await STORES[storeId].save({ [key]: draft[storeId][key] });
      toast.ok(r?.restartRequired?.length ? `${key} saved. It applies after a restart` : `${key} saved and applied`);
      setDraft((d) => { const n = { ...d[storeId] }; delete n[key]; return { ...d, [storeId]: n }; });
      await load();
      reload?.();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSavingKey("");
    }
  };

  const revertOne = (storeId, key) =>
    setDraft((d) => { const n = { ...d[storeId] }; delete n[key]; return { ...d, [storeId]: n }; });

  const resetKey = async (storeId, key) => {
    try {
      await STORES[storeId].reset([key]);
      toast.ok(`${key} reset to its default`);
      setDraft((d) => { const n = { ...d[storeId] }; delete n[key]; return { ...d, [storeId]: n }; });
      load();
    } catch (e) {
      toast.error(e.message);
    }
  };

  const q = query.trim().toLowerCase();
  const matches = (s) => !q || `${s.key} ${s.label} ${s.help}`.toLowerCase().includes(q);
  const shownGroups = q ? nav.filter((n) => n.group.settings.some(matches)) : nav.filter((n) => n.id === active);

  let lastSection = "";

  return (
    <div className="page wide">
      <PageHeader
        eyebrow="Admin"
        title="Settings"
        subtitle="Every voice setting for both services. The database is the single source: values saved here are final and apply to the next call. Settings marked restart apply after a server restart."
        actions={<>
          {dirtyCount > 1 && (
            <span className="unsaved-group">
              {dirtyCount} unsaved
              <FieldActions dirty saving={saving} label="all changes" onSave={save} onRevert={() => setDraft({ pipeline: {}, brain: {} })} />
            </span>
          )}
          <button className="btn btn-sm" onClick={load}><Refresh size={14} /> Refresh</button>
        </>}
      />

      {Object.entries(errors).filter(([, e]) => e).map(([id, e]) => (
        <div key={id} className="notice halt" style={{ marginBottom: 12 }}><Alert size={15} />
          <span>{id === "brain" ? "Brain settings" : "Pipeline settings"} couldn't load: {e}</span></div>
      ))}
      {stores.pipeline && !stores.pipeline.editable && (
        <div className="notice warn" style={{ marginBottom: 12 }}><Info size={15} /><span>The database isn't in use (USE_DB=false), so settings are read-only.</span></div>
      )}

      {!nav.length && !Object.values(errors).some(Boolean) ? <Skeleton h={480} r={12} /> : (
        <div className="set-layout">
          <nav className="set-nav">
            <div className="searchbar" style={{ marginBottom: 6 }}>
              <Search size={14} />
              <input className="searchinput" placeholder="Find a setting" value={query} onChange={(e) => setQuery(e.target.value)} />
              {query && <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setQuery("")} aria-label="Clear"><X size={13} /></button>}
            </div>
            {nav.map((n) => {
              const header = n.section !== lastSection ? n.section : null;
              lastSection = n.section;
              const groupDirty = n.group.settings.some((s) => s.key in draft[n.storeId]);
              const hits = q ? n.group.settings.filter(matches).length : null;
              if (q && !hits) return null;
              return (
                <div key={n.id}>
                  {header && <div className="set-nav-sec">{header}</div>}
                  <button className={!q && n.id === active ? "on" : ""} onClick={() => { setQuery(""); setActive(n.id); }}>
                    {n.group.title}
                    {groupDirty ? <span className="dirty-dot" /> : <span className="count">{hits ?? n.group.settings.length}</span>}
                  </button>
                </div>
              );
            })}
          </nav>

          <div className="stack-lg">
            {shownGroups.map((n) => (
              <GroupCard
                key={n.id}
                entry={n}
                store={stores[n.storeId]}
                draft={draft[n.storeId]}
                filter={q ? matches : null}
                editable={editable && stores[n.storeId]?.editable !== false}
                reveal={can("secrets.reveal") ? (n.storeId === "brain" ? api.revealBrainSetting : api.revealSetting) : null}
                onChange={(key, value) => setDraft((d) => {
                  const next = { ...d[n.storeId] };
                  const live = stores[n.storeId].values[key]?.value ?? "";
                  if (String(value) === String(live) && value !== CLEAR) delete next[key];
                  else next[key] = value;
                  return { ...d, [n.storeId]: next };
                })}
                onReset={(key) => resetKey(n.storeId, key)}
                onSaveOne={(key) => saveOne(n.storeId, key)}
                onRevertOne={(key) => revertOne(n.storeId, key)}
                savingKey={savingKey.startsWith(`${n.storeId}:`) ? savingKey.slice(n.storeId.length + 1) : ""}
              />
            ))}
            {q && !shownGroups.length && <div className="card"><div className="empty2"><h4>No setting matches “{query}”</h4></div></div>}
          </div>
        </div>
      )}


    </div>
  );
}

function GroupCard({ entry, store, draft, filter, editable, onChange, onReset, reveal, onSaveOne, onRevertOne, savingKey }) {
  const [advanced, setAdvanced] = useState(false);
  const { group } = entry;
  const valueOf = (s) => (s.key in draft ? draft[s.key] : store.values[s.key]?.value ?? "");
  const visible = (s) => {
    if (!s.dependsOn) return true;
    const [key, want] = s.dependsOn;
    const other = group.settings.find((x) => x.key === key);
    const v = other ? valueOf(other) : store.values[key]?.value;
    return String(v).toLowerCase() === String(want).toLowerCase();
  };
  const settings = group.settings.filter((s) => (!filter || filter(s)) && visible(s));
  const basic = settings.filter((s) => !s.advanced || filter);
  const adv = filter ? [] : settings.filter((s) => s.advanced);

  const rows = (list) => {
    let lastSub = "";
    return list.map((s) => {
      const sub = s.sub && s.sub !== lastSub ? s.sub : null;
      lastSub = s.sub || lastSub;
      return (
        <div key={s.key}>
          {sub && <div className="set-sub">{sub}</div>}
          <SettingRow setting={s} meta={store.values[s.key] || {}} value={valueOf(s)} changed={s.key in draft}
            editable={editable} reveal={reveal} restart={(store.restartKeys || []).includes(s.key)}
            onChange={(v) => onChange(s.key, v)} onReset={() => onReset(s.key)}
            onSave={() => onSaveOne(s.key)} onRevert={() => onRevertOne(s.key)} saving={savingKey === s.key} />
        </div>
      );
    });
  };

  return (
    <section className="section">
      <div className="section-head" style={{ paddingBottom: 12, borderBottom: "1px solid var(--line)" }}>
        <div style={{ flex: 1 }}>
          <div className="phead-eyebrow" style={{ marginBottom: 2 }}>{entry.section}{group.category ? ` · ${group.category}` : ""}</div>
          <h3>{group.title}</h3>
          {group.blurb && <p>{group.blurb}</p>}
        </div>
      </div>
      <div>{rows(basic)}</div>
      {adv.length > 0 && (
        <>
          <button className="disclose" style={{ width: "100%", borderTop: "1px solid var(--line)", padding: "12px 20px", borderRadius: 0 }}
            onClick={() => setAdvanced((v) => !v)} aria-expanded={advanced}>
            <Chevron size={14} dir={advanced ? "up" : "right"} /> Advanced <span className="grow" />
            <span className="tiny faint">{adv.length} settings</span>
          </button>
          {advanced && <div>{rows(adv)}</div>}
        </>
      )}
    </section>
  );
}

function SettingRow({ setting: s, meta, value, changed, editable, restart, onChange, onReset, reveal, onSave, onRevert, saving }) {
  return (
    <div className={`setrow2 ${changed ? "changed" : ""}`}>
      <div style={{ minWidth: 0 }}>
        <div className="setrow2-label">
          {s.label}
          {restart && <Badge tone="warn">restart</Badge>}
          {s.secret && <Badge>secret</Badge>}
        </div>
        <div className="setrow2-key">{s.key}{meta.updatedAt ? ` · changed ${relativeTime(meta.updatedAt)}${meta.updatedBy ? ` by ${meta.updatedBy === "env-seed" ? "initial import" : meta.updatedBy}` : ""}` : ""}</div>
        {s.help && <div className="setrow2-help">{s.help}</div>}
      </div>
      <div className="setrow2-control" style={{ flexDirection: "column", alignItems: "stretch", gap: 4 }}>
        <div className="row" style={{ gap: 8, alignItems: "center" }}>
          <div style={{ flex: 1, minWidth: 0, display: "flex", justifyContent: "flex-end" }}>
            <div style={{ width: "100%" }}>
              <Control s={s} meta={meta} value={value} editable={editable} onChange={onChange} reveal={reveal} />
            </div>
          </div>
          <FieldActions dirty={changed} saving={saving} label={s.label} onSave={onSave} onRevert={onRevert} />
        </div>
        {editable && meta.source === "database" && !s.secret && (
          <button className="auth-link" style={{ alignSelf: "flex-end", fontSize: 11.5, fontWeight: 500, color: "var(--muted)" }} onClick={onReset}>Reset to default</button>
        )}
      </div>
    </div>
  );
}

function Control({ s, meta, value, editable, onChange, reveal: revealFn }) {
  const disabled = !editable;
  const options = (s.options || []).map((o) => (typeof o === "string" ? { value: o, label: o === "" ? "Off / default" : o } : o));

  if (s.type === "bool") {
    const on = String(value).toLowerCase() === "true";
    return <div style={{ display: "flex", justifyContent: "flex-end" }}><Toggle checked={on} disabled={disabled} label={s.label} onChange={(v) => onChange(v ? "true" : "false")} /></div>;
  }

  if (options.length) {
    const short = options.length <= 4 && options.every((o) => String(o.label).length <= 12);
    if (short) {
      return <div style={{ display: "flex", justifyContent: "flex-end" }}><Segmented size="sm" value={value} disabled={disabled} options={options} onChange={onChange} /></div>;
    }
    return <Select value={value} disabled={disabled} options={options} onChange={onChange} />;
  }

  if (s.type === "number") {
    const hasRange = s.min !== null && s.min !== undefined && s.max !== null && s.max !== undefined;
    const step = s.step || 1;
    if (hasRange && (s.max - s.min) / step <= 5000) {
      return <Slider min={s.min} max={s.max} step={step} unit={s.unit} disabled={disabled}
        value={value === "" ? (meta.inheritedValue ?? s.default ?? s.min) : Number(value)} onChange={(v) => onChange(String(v))} />;
    }
    return (
      <div className="numwrap">
        <input className="input mono" type="number" disabled={disabled} min={s.min ?? undefined} max={s.max ?? undefined} step={step}
          value={value} placeholder={meta.inheritedValue || s.placeholder || s.default} onChange={(e) => onChange(e.target.value)} />
        {s.unit && <span className="numunit mono">{s.unit}</span>}
      </div>
    );
  }

  if (s.secret || s.type === "password") {
    return (
      <div className="secret-wrap">
        <SecretInput value={value} onChange={onChange} hasValue={meta.hasValue} clearValue={CLEAR} disabled={disabled}
          reveal={revealFn ? () => revealFn(s.key) : null} />
        {meta.hasValue && editable && value !== CLEAR && <button className="btn btn-sm" onClick={() => onChange(CLEAR)} title="Clear this secret">Clear</button>}
      </div>
    );
  }

  if (s.type === "json" || s.type === "textarea") {
    return <textarea className="textarea code" rows={4} disabled={disabled} value={value} placeholder={s.placeholder} onChange={(e) => onChange(e.target.value)} />;
  }

  return <input className="input" disabled={disabled} value={value} placeholder={meta.inheritedValue ? `inherits: ${meta.inheritedValue}` : s.placeholder || s.default}
    onChange={(e) => onChange(e.target.value)} />;
}
