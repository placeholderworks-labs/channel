import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Key, Lock, Plus, Trash } from "../components/Icons";
import { Badge, Confirm, Field, FieldActions, Modal, PageHeader, Skeleton, Toggle, AutoTextarea } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { relativeTime } from "../lib/format";
import { useToast } from "../lib/toast";

export default function Roles() {
  const { user: me, can, refresh } = useAuth();
  const toast = useToast();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState("");
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [del, setDel] = useState(null);
  const [busy, setBusy] = useState(false);
  const manage = can("roles.manage");

  const load = useCallback(async (keep) => {
    try {
      const r = await api.roles();
      setData(r);
      setError("");
      const pick = keep || selected || r.roles?.[0]?.name;
      setSelected(pick);
      const role = r.roles.find((x) => x.name === pick) || r.roles[0];
      setDraft(role ? { ...role, permissions: [...role.permissions] } : null);
    } catch (e) {
      setError(e.message);
    }
  }, [selected]);

  useEffect(() => { load(); }, []);

  const role = data?.roles.find((r) => r.name === selected);
  const groups = useMemo(() => {
    const out = {};
    for (const p of data?.catalog || []) (out[p.group] ||= []).push(p);
    return out;
  }, [data]);

  const locked = !manage || role?.name === "super_admin" || (role?.name === "admin" && me?.role !== "super_admin");
  const mine = new Set(me?.permissions || []);
  const dirty = draft && role && (draft.label !== role.label || draft.description !== role.description
    || [...draft.permissions].sort().join() !== [...role.permissions].sort().join());

  const pick = (name) => {
    if (dirty && !window.confirm("Discard your unsaved changes to this role?")) return;
    const r = data.roles.find((x) => x.name === name);
    setSelected(name);
    setDraft({ ...r, permissions: [...r.permissions] });
  };

  const togglePerm = (key, on) =>
    setDraft((d) => ({ ...d, permissions: on ? [...new Set([...d.permissions, key])] : d.permissions.filter((p) => p !== key) }));

  const save = async () => {
    setSaving(true);
    try {
      await api.updateRole(draft.name, { label: draft.label, description: draft.description, permissions: draft.permissions });
      toast.ok(`${draft.label} saved. It applies to everyone with it right away`);
      await load(draft.name);
      if (draft.name === me?.role) refresh().catch(() => {});
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await api.deleteRole(del.name);
      toast.ok(`${del.label} deleted`);
      setDel(null);
      setSelected("");
      load(data.roles.find((r) => r.name !== del.name)?.name);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page wide">
      <PageHeader
        eyebrow="Admin"
        title="Roles & access"
        subtitle="A role is a set of permissions. Super admin can do everything and can't be changed; admin can do everything except manage roles. Create custom roles for anything in between."
        actions={manage && <button className="btn btn-primary btn-sm" onClick={() => setCreating(true)} disabled={!data}><Plus size={14} /> New role</button>}
      />

      {error && <div className="notice halt" style={{ marginBottom: 16 }}><Alert size={15} /><span>{error}</span></div>}

      {!data && !error ? <Skeleton h={420} r={12} /> : data && (
        <div className="set-layout" style={{ gridTemplateColumns: "280px minmax(0, 1fr)" }}>
          <div className="role-list">
            {data.roles.map((r) => (
              <button key={r.name} className={`role-item ${r.name === selected ? "on" : ""}`} onClick={() => pick(r.name)}>
                <div className="role-item-top">
                  <span className="role-item-name">{r.label}</span>
                  {r.isSystem && <Lock size={12} />}
                  <span className="grow" />
                  <Badge>{r.userCount} {r.userCount === 1 ? "member" : "members"}</Badge>
                </div>
                <span className="small dim">{r.description || <span className="faint">No description</span>}</span>
                <span className="tiny faint">{r.permissions.length} of {data.catalog.length} permissions</span>
              </button>
            ))}
          </div>

          {draft && (
            <div className="stack-lg">
              <div className="section">
                <div className="section-head">
                  <div style={{ flex: 1 }}>
                    <h3 className="row" style={{ gap: 8 }}>{role?.label} <span className="mono small faint">{role?.name}</span>
                      {role?.isSystem && <Badge tone="brand">system</Badge>}</h3>
                    <p>{role?.updatedAt ? `Updated ${relativeTime(role.updatedAt)}${role.updatedBy ? ` by ${role.updatedBy}` : ""}` : "Built in"}</p>
                  </div>
                  {dirty && !locked && (
                    <span className="unsaved-group">
                      Unsaved changes
                      <FieldActions dirty saving={saving} label={`changes to ${role?.label}`} onSave={save}
                        onRevert={() => setDraft({ ...role, permissions: [...role.permissions] })} />
                    </span>
                  )}
                  {manage && !role?.isSystem && (
                    <button className="btn btn-sm btn-danger" onClick={() => setDel(role)}><Trash size={13} /> Delete</button>
                  )}
                </div>
                <div className="section-body">
                  {locked && (
                    <div className="notice"><Lock size={15} /><span>
                      {role?.name === "super_admin" ? "Super admin always has every permission." :
                        !manage ? "Viewing only. Managing roles needs the “Manage roles” permission." :
                        "Only a super admin can change the admin role."}
                    </span></div>
                  )}
                  <div className="form-grid">
                    <Field label="Display name"><input className="input" value={draft.label} disabled={locked} onChange={(e) => setDraft({ ...draft, label: e.target.value })} /></Field>
                    <Field label="Description"><AutoTextarea value={draft.description || ""} disabled={locked} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></Field>
                  </div>
                </div>
              </div>

              {Object.entries(groups).map(([group, perms]) => {
                const allOn = perms.every((p) => draft.permissions.includes(p.key));
                return (
                  <div key={group} className="perm-group">
                    <div className="perm-group-head">
                      <span style={{ flex: 1 }}>{group}</span>
                      {!locked && (
                        <button className="btn btn-ghost btn-xs" onClick={() => perms.forEach((p) => (mine.has(p.key) || allOn) && togglePerm(p.key, !allOn))}>
                          {allOn ? "Clear all" : "Allow all"}
                        </button>
                      )}
                    </div>
                    {perms.map((p) => {
                      const on = draft.permissions.includes(p.key);
                      const cantGrant = !on && !mine.has(p.key);
                      return (
                        <div key={p.key} className="perm-row">
                          <div className="perm-row-text">
                            <strong>{p.label} <span className="perm-key">{p.key}</span></strong>
                            <span>{p.description}</span>
                          </div>
                          <Toggle checked={on} disabled={locked || cantGrant} label={p.label} onChange={(v) => togglePerm(p.key, v)} />
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}


      {creating && <CreateRole catalog={data.catalog} mine={mine} onClose={() => setCreating(false)}
        onDone={(name) => { setCreating(false); load(name); }} />}

      <Confirm open={!!del} danger busy={busy} title={`Delete the ${del?.label} role?`} confirmLabel="Delete role"
        body={del?.userCount ? <>{del.userCount} member(s) still have it. Move them to another role on the Team page first.</> : "No one has this role. It can be recreated later."}
        onConfirm={remove} onClose={() => setDel(null)} />
    </div>
  );
}

function CreateRole({ catalog, mine, onClose, onDone }) {
  const toast = useToast();
  const [form, setForm] = useState({ label: "", name: "", description: "", permissions: ["overview.view"] });
  const [busy, setBusy] = useState(false);
  const valid = /^[a-z][a-z0-9_]{1,30}$/.test(form.name) && form.label.trim();

  const submit = async () => {
    setBusy(true);
    try {
      await api.createRole(form);
      toast.ok(`${form.label} created`);
      onDone(form.name);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open title="New role" subtitle="Start with view access. You can fine-tune permissions after creating it." onClose={onClose} width={480}
      footer={<><button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={submit} disabled={!valid || busy}>{busy ? "Creating…" : "Create role"}</button></>}>
      <Field label="Display name" required>
        <input className="input" value={form.label} placeholder="Campaign manager"
          onChange={(e) => setForm({ ...form, label: e.target.value, name: e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").replace(/^\d+/, "").slice(0, 31) })} />
      </Field>
      <Field label="Identifier" hint="lowercase_with_underscores"><input className="input mono" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
      <Field label="Description"><AutoTextarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
      <Field label="Start from" hint="Copies view-only access; adjust after.">
        <div className="row" style={{ gap: 8 }}>
          <button type="button" className="btn btn-sm" onClick={() => setForm({ ...form, permissions: catalog.filter((p) => p.key.endsWith(".view") && mine.has(p.key)).map((p) => p.key) })}>
            <Key size={13} /> All view permissions
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setForm({ ...form, permissions: ["overview.view"] })}>Overview only</button>
        </div>
        <span className="hint">{form.permissions.length} permission(s) selected</span>
      </Field>
    </Modal>
  );
}
