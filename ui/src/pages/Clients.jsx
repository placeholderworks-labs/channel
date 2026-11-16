import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Alert, Bot, Building, Copy, Pencil, Plus, Refresh, Trash, Users } from "../components/Icons";
import { Avatar, Badge, Confirm, Empty, Field, Modal, PageHeader, Select, Skeleton, Toggle } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { relativeTime } from "../lib/format";
import { useToast } from "../lib/toast";

const CLIENT_ROLES = ["client"];

export default function Clients() {
  const { can } = useAuth();
  const toast = useToast();
  const manage = can("team.manage");
  const [data, setData] = useState(null);
  const [agents, setAgents] = useState([]);
  const [roles, setRoles] = useState([]);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(null);
  const [adding, setAdding] = useState(null);
  const [removing, setRemoving] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [handover, setHandover] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [c, u, r] = await Promise.all([api.clients(), api.usecases(), api.roles()]);
      setData(c);
      setAgents((u.usecases || []).filter((a) => a.status !== "archived"));
      setRoles(r.roles || []);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const agentName = useMemo(() => Object.fromEntries(agents.map((a) => [a.slug, a.name])), [agents]);
  const roleOptions = roles
    .filter((r) => CLIENT_ROLES.includes(r.name))
    .map((r) => ({ value: r.name, label: r.label || r.name }));
  const clients = data?.clients || [];
  const people = clients.reduce((n, c) => n + c.members.length, 0);

  const removeMember = async () => {
    setBusy(true);
    try {
      await api.deleteUser(removing.id);
      toast.ok(`${removing.email} removed`);
      setRemoving(null);
      load();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const deleteClient = async () => {
    setBusy(true);
    try {
      await api.deleteClient(deleting.id);
      toast.ok(`${deleting.name} deleted`);
      setDeleting(null);
      load();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="Admin"
        title="Clients"
        subtitle="Each client is an organization: give it the pre-made agents it may use, then invite its people. They only ever see and test their own agents, calls and leads."
        actions={
          <>
            <Link className="btn btn-sm" to="/team"><Users size={14} /> Internal team</Link>
            {manage && <button className="btn btn-primary btn-sm" onClick={() => setEditing({})}><Plus size={14} /> New client</button>}
          </>
        }
      />

      {error && <div className="notice halt" style={{ marginBottom: 16 }}><Alert size={15} /><span>{error}</span></div>}

      <div className="stat-row" style={{ marginBottom: 18 }}>
        <div className="stat"><div className="stat-label">Clients</div><div className="stat-value">{data ? clients.length : "-"}</div><div className="stat-foot">organizations</div></div>
        <div className="stat"><div className="stat-label">Client people</div><div className="stat-value">{data ? people : "-"}</div><div className="stat-foot">with dashboard access</div></div>
        <div className="stat"><div className="stat-label">Agents shared</div><div className="stat-value">{data ? new Set(clients.flatMap((c) => c.agents)).size : "-"}</div><div className="stat-foot">of {agents.length} available</div></div>
        <div className="stat"><div className="stat-label">Internal team</div><div className="stat-value">{data ? (data.internal || []).length : "-"}</div><div className="stat-foot">PlaceholderWorks staff</div></div>
      </div>

      {!data && !error && <div className="card"><div style={{ padding: 20 }}><Skeleton height={80} /></div></div>}

      {data && clients.length === 0 && (
        <div className="card">
          <Empty icon={<Building size={22} />} title="No clients yet"
            action={manage && <button className="btn btn-primary btn-sm" onClick={() => setEditing({})}><Plus size={14} /> New client</button>}>
            Create an organization for a client, pick the agents they get, and invite their people.
          </Empty>
        </div>
      )}

      <div className="client-grid">
        {clients.map((c) => (
          <div className="card client-card" key={c.id}>
            <div className="card-head">
              <div className="client-mark"><Building size={16} /></div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <h3 style={{ margin: 0 }}>{c.name}</h3>
                <div className="tiny faint">Created {relativeTime(c.createdAt)}{c.createdBy ? ` by ${c.createdBy}` : ""}</div>
              </div>
              {manage && (
                <>
                  <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setEditing(c)} aria-label="Edit client"><Pencil size={14} /></button>
                  <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setDeleting(c)} aria-label="Delete client"><Trash size={14} /></button>
                </>
              )}
            </div>
            <div className="client-section">
              <div className="client-label">Agents</div>
              <div className="client-chips">
                {c.agents.length === 0 && <span className="tiny faint">No agents yet: edit the client to give it some.</span>}
                {c.agents.map((slug) => (
                  <Badge key={slug} tone="brand"><Bot size={11} /> {agentName[slug] || slug}</Badge>
                ))}
              </div>
            </div>
            <div className="client-section">
              <div className="client-label" style={{ display: "flex", alignItems: "center" }}>
                <span style={{ flex: 1 }}>People</span>
                {manage && <button className="btn btn-ghost btn-sm" onClick={() => setAdding(c)}><Plus size={13} /> Add person</button>}
              </div>
              {c.members.length === 0 && <div className="tiny faint">Nobody invited yet.</div>}
              {c.members.map((m) => (
                <div className="client-member" key={m.id}>
                  <Avatar name={m.name} email={m.email} size={30} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="client-member-name">{m.name || m.email}</div>
                    <div className="tiny faint">{m.email}</div>
                  </div>
                  {m.mustChangePassword && <Badge tone="warn">invited</Badge>}
                  <Badge>{m.roleLabel || m.role}</Badge>
                  {manage && <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setRemoving(m)} aria-label="Remove person"><Trash size={13} /></button>}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {data && (
        <div style={{ marginTop: 14, display: "flex", justifyContent: "flex-end" }}>
          <button className="btn btn-ghost btn-sm" onClick={load}><Refresh size={13} /> Refresh</button>
        </div>
      )}

      {editing && (
        <ClientDialog client={editing} agents={agents} onClose={() => setEditing(null)}
          onDone={() => { setEditing(null); load(); }} />
      )}
      {adding && (
        <MemberDialog client={adding} roles={roleOptions} onClose={() => setAdding(null)}
          onDone={(r) => { setAdding(null); if (!r.emailed) setHandover({ email: r.user.email, password: r.tempPassword, reason: r.emailError }); load(); }} />
      )}
      <Confirm open={!!removing} title="Remove this person?" danger busy={busy} confirmLabel="Remove"
        body={removing ? `${removing.email} will lose access to the dashboard straight away.` : ""}
        onConfirm={removeMember} onClose={() => setRemoving(null)} />
      <Confirm open={!!deleting} title="Delete this client?" danger busy={busy} confirmLabel="Delete"
        body={deleting ? `${deleting.name} will be deleted. Remove its people first.` : ""}
        onConfirm={deleteClient} onClose={() => setDeleting(null)} />
      <Modal open={!!handover} title="Hand over this temporary password" onClose={() => setHandover(null)} width={460}
        footer={<button className="btn btn-primary" onClick={() => setHandover(null)}>Done</button>}>
        {handover?.reason && <div className="notice warn" style={{ marginBottom: 12 }}><Alert size={14} /><span>The email did not go out: {handover.reason}</span></div>}
        <Field label={handover?.email}>
          <div style={{ display: "flex", gap: 8 }}>
            <input className="input mono" readOnly value={handover?.password || ""} />
            <button className="btn" onClick={() => { navigator.clipboard?.writeText(handover?.password || ""); toast.ok("Copied"); }}><Copy size={14} /></button>
          </div>
        </Field>
      </Modal>
    </div>
  );
}

function ClientDialog({ client, agents, onClose, onDone }) {
  const toast = useToast();
  const isNew = !client.id;
  const [name, setName] = useState(client.name || "");
  const [chosen, setChosen] = useState(new Set(client.agents || []));
  const [busy, setBusy] = useState(false);

  const toggle = (slug) => {
    const next = new Set(chosen);
    next.has(slug) ? next.delete(slug) : next.add(slug);
    setChosen(next);
  };

  const submit = async () => {
    setBusy(true);
    try {
      const body = { name: name.trim(), agents: [...chosen] };
      if (isNew) await api.createClient(body);
      else await api.updateClient(client.id, body);
      toast.ok(isNew ? `${body.name} created` : `${body.name} updated`);
      onDone();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open title={isNew ? "New client" : `Edit ${client.name}`}
      subtitle="Pick the pre-made agents this organization may see and test." onClose={onClose} width={520}
      footer={<><button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={submit} disabled={!name.trim() || busy}>{busy ? "Saving…" : isNew ? "Create client" : "Save"}</button></>}>
      <Field label="Organization name" required>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. SmileCare Dental" autoFocus />
      </Field>
      <Field label="Agents" hint={`${chosen.size} selected`}>
        <div className="client-agent-list">
          {agents.length === 0 && <div className="tiny faint">No agents yet.</div>}
          {agents.map((a) => (
            <label key={a.slug} className={`client-agent ${chosen.has(a.slug) ? "on" : ""}`}>
              <input type="checkbox" checked={chosen.has(a.slug)} onChange={() => toggle(a.slug)} />
              <div style={{ minWidth: 0 }}>
                <div className="client-member-name">{a.name}</div>
                <div className="tiny faint">{a.description || a.slug}</div>
              </div>
            </label>
          ))}
        </div>
      </Field>
    </Modal>
  );
}

function MemberDialog({ client, roles, onClose, onDone }) {
  const toast = useToast();
  const [form, setForm] = useState({ email: "", name: "", role: "client", sendInvite: true });
  const [busy, setBusy] = useState(false);
  const valid = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email.trim()) && form.role;

  const submit = async () => {
    setBusy(true);
    try {
      const r = await api.addClientMember(client.id, { ...form, email: form.email.trim().toLowerCase(), name: form.name.trim() });
      if (r.emailed) toast.ok(`Invite sent to ${r.user.email}`);
      onDone(r);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open title={`Add a person to ${client.name}`} subtitle="They get an email with a temporary password and only see this client's agents." onClose={onClose} width={480}
      footer={<><button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={submit} disabled={!valid || busy}>{busy ? "Inviting…" : form.sendInvite ? "Send invite" : "Create account"}</button></>}>
      <Field label="Email" required><input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="name@company.com" autoFocus /></Field>
      <Field label="Name"><input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
      <Field label="Role" hint="Clients can view and test their organization's agents, calls and leads. Nothing else.">
        <Select value={form.role} options={roles.length ? roles : [{ value: "client", label: "Client" }]} onChange={(v) => setForm({ ...form, role: v })} />
      </Field>
      <div className="switchrow">
        <div className="switchrow-text"><strong>Email the invite</strong><span>Off shows you the temporary password to hand over yourself.</span></div>
        <Toggle checked={form.sendInvite} onChange={(v) => setForm({ ...form, sendInvite: v })} label="Email the invite" />
      </div>
    </Modal>
  );
}
