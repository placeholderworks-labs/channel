import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Alert, Check, Copy, Key, Mail, Plus, Refresh, Search, Trash, Users, X } from "../components/Icons";
import { Avatar, Badge, Confirm, Empty, Field, Modal, PageHeader, Select, Skeleton, Toggle } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { relativeTime } from "../lib/format";
import { useToast } from "../lib/toast";

export default function Team() {
  const { user: me, can } = useAuth();
  const toast = useToast();
  const [users, setUsers] = useState(null);
  const [roles, setRoles] = useState([]);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [inviting, setInviting] = useState(false);
  const [del, setDel] = useState(null);
  const [reset, setReset] = useState(null);
  const [handover, setHandover] = useState(null);
  const [busy, setBusy] = useState(false);
  const manage = can("team.manage");

  const load = useCallback(async () => {
    try {
      const [u, r] = await Promise.all([api.users(), api.roles()]);
      setUsers(u.users || []);
      setRoles(r.roles || []);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (users || []).filter((u) => !q || `${u.name} ${u.email} ${u.roleLabel}`.toLowerCase().includes(q));
  }, [users, query]);

  const roleOptions = roles
    .filter((r) => r.name !== "super_admin" || me?.role === "super_admin")
    .map((r) => ({ value: r.name, label: r.label || r.name }));

  const patch = async (u, body, okMsg) => {
    try {
      await api.updateUser(u.id, body);
      toast.ok(okMsg);
      load();
    } catch (e) {
      toast.error(e.message);
    }
  };

  const doReset = async () => {
    setBusy(true);
    try {
      const r = await api.resetUserPassword(reset.id);
      setReset(null);
      if (r.emailed) toast.ok(`Temporary password emailed to ${reset.email}`);
      else setHandover({ email: reset.email, password: r.tempPassword, reason: r.emailError });
      load();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async () => {
    setBusy(true);
    try {
      await api.deleteUser(del.id);
      toast.ok(`${del.email} removed`);
      setDel(null);
      load();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const active = (users || []).filter((u) => u.isActive).length;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Admin"
        title="Team"
        subtitle="Who can open Voice Studio and what their role lets them do. Invited people get an email with a temporary password and must set their own on first sign-in."
        actions={
          <>
            <Link className="btn btn-sm" to="/roles"><Key size={14} /> Roles & access</Link>
            {manage && <button className="btn btn-primary btn-sm" onClick={() => setInviting(true)}><Plus size={14} /> Invite member</button>}
          </>
        }
      />

      {error && <div className="notice halt" style={{ marginBottom: 16 }}><Alert size={15} /><span>{error}</span></div>}

      <div className="stat-row" style={{ marginBottom: 18 }}>
        <div className="stat"><div className="stat-label">Members</div><div className="stat-value">{users ? users.length : "-"}</div><div className="stat-foot">{active} active</div></div>
        <div className="stat"><div className="stat-label">Roles</div><div className="stat-value">{roles.length || "-"}</div><div className="stat-foot">{roles.filter((r) => !r.isSystem).length} custom</div></div>
        <div className="stat"><div className="stat-label">Waiting on first sign-in</div><div className="stat-value">{(users || []).filter((u) => u.mustChangePassword).length}</div><div className="stat-foot">temporary password set</div></div>
        <div className="stat"><div className="stat-label">You</div><div className="stat-value" style={{ fontSize: 18, marginTop: 10 }}>{me?.roleLabel || me?.role}</div><div className="stat-foot">{me?.permissions?.length || 0} permissions</div></div>
      </div>

      <AccessRequests manage={manage} />

      <div className="card">
        <div className="card-head">
          <h3 style={{ flex: 1 }}>Members</h3>
          <div className="searchbar" style={{ maxWidth: 260 }}>
            <Search size={14} />
            <input className="searchinput" placeholder="Search people" value={query} onChange={(e) => setQuery(e.target.value)} />
            {query && <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setQuery("")} aria-label="Clear"><X size={13} /></button>}
          </div>
          <button className="btn btn-ghost btn-icon btn-sm" onClick={load} aria-label="Refresh"><Refresh size={14} /></button>
        </div>
        {!users && !error ? <div className="card-body"><Skeleton h={160} /></div> : shown.length === 0 ? (
          <Empty icon={<Users size={20} />} title="No one matches">Try another search.</Empty>
        ) : (
          <div className="people">
            {shown.map((u) => {
              const self = u.id === me?.id;
              const locked = self || (u.role === "super_admin" && me?.role !== "super_admin");
              return (
                <div key={u.id} className="person2" style={{ opacity: u.isActive ? 1 : 0.6 }}>
                  <Avatar name={u.name} email={u.email} size={34} tone={u.role === "super_admin" ? "super" : ""} />
                  <div style={{ minWidth: 0 }}>
                    <div className="person2-name">
                      {u.name || u.email.split("@")[0]}
                      {self && <span className="faint small"> · you</span>}
                    </div>
                    <div className="person2-mail ellipsis">{u.email}</div>
                    <div className="row" style={{ gap: 6, marginTop: 4 }}>
                      {!u.isActive && <Badge tone="halt">deactivated</Badge>}
                      {u.mustChangePassword && <Badge tone="warn">temporary password</Badge>}
                      <span className="tiny faint">{u.lastLoginAt ? `last seen ${relativeTime(u.lastLoginAt)}` : "never signed in"}</span>
                    </div>
                  </div>
                  <div style={{ width: 170 }}>
                    {manage && !locked ? (
                      <Select value={u.role} options={roleOptions} onChange={(v) => patch(u, { role: v }, `${u.email} is now ${roles.find((r) => r.name === v)?.label || v}`)} />
                    ) : (
                      <Badge tone={u.role === "super_admin" ? "solid" : u.role === "admin" ? "brand" : ""}>{u.roleLabel || u.role}</Badge>
                    )}
                  </div>
                  <div className="row" style={{ gap: 8 }} title={u.isActive ? "Active" : "Deactivated"}>
                    {manage && !locked && (
                      <Toggle size="sm" checked={u.isActive} label="Active"
                        onChange={(v) => patch(u, { isActive: v }, v ? `${u.email} reactivated` : `${u.email} deactivated`)} />
                    )}
                  </div>
                  <div className="row" style={{ gap: 2 }}>
                    {manage && !locked && (
                      <>
                        <button className="btn btn-ghost btn-icon btn-sm" title="Reset password" aria-label="Reset password" onClick={() => setReset(u)}><Mail size={14} /></button>
                        <button className="btn btn-ghost btn-icon btn-sm" title="Remove" aria-label="Remove" onClick={() => setDel(u)}><Trash size={14} /></button>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {inviting && (
        <InviteDialog roles={roleOptions} onClose={() => setInviting(false)}
          onDone={(r) => { setInviting(false); load(); if (!r.emailed) setHandover({ email: r.user.email, password: r.tempPassword, reason: r.emailError }); }} />
      )}

      <Confirm open={!!reset} title={`Reset ${reset?.email}'s password?`} confirmLabel="Email a temporary password" busy={busy}
        body="Their current password stops working right away. They'll get a temporary one by email and must change it when they sign in."
        onConfirm={doReset} onClose={() => setReset(null)} />
      <Confirm open={!!del} danger title={`Remove ${del?.email}?`} confirmLabel="Remove member" busy={busy}
        body="They lose access immediately. To keep their history visible, deactivate them instead."
        onConfirm={doDelete} onClose={() => setDel(null)} />
      <HandoverDialog info={handover} onClose={() => setHandover(null)} />
    </div>
  );
}

function InviteDialog({ roles, onClose, onDone }) {
  const toast = useToast();
  const [form, setForm] = useState({ email: "", name: "", role: "operator", sendInvite: true });
  const [busy, setBusy] = useState(false);
  const valid = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email.trim()) && form.role;

  const submit = async () => {
    setBusy(true);
    try {
      const r = await api.addUser({ ...form, email: form.email.trim().toLowerCase(), name: form.name.trim() });
      if (r.emailed) toast.ok(`Invite sent to ${r.user.email}`);
      onDone(r);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open title="Invite a team member" subtitle="They'll receive an email with a temporary password and the Studio link." onClose={onClose} width={480}
      footer={<><button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={submit} disabled={!valid || busy}>{busy ? "Inviting…" : form.sendInvite ? "Send invite" : "Create account"}</button></>}>
      <Field label="Work email" required><input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="name@placeholderworks.com" /></Field>
      <Field label="Name"><input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
      <Field label="Role" hint="Pick the least access they need. You can change it any time.">
        <Select value={form.role} options={roles} onChange={(v) => setForm({ ...form, role: v })} />
      </Field>
      <div className="switchrow">
        <div className="switchrow-text"><strong>Email the invite</strong><span>Off shows you the temporary password to hand over yourself.</span></div>
        <Toggle checked={form.sendInvite} onChange={(v) => setForm({ ...form, sendInvite: v })} label="Email the invite" />
      </div>
    </Modal>
  );
}

function HandoverDialog({ info, onClose }) {
  const toast = useToast();
  return (
    <Modal open={!!info} title="Hand over this temporary password" onClose={onClose} width={460}
      subtitle={info?.reason ? `The email wasn't sent: ${info.reason}` : "No email was sent."}
      footer={<button className="btn btn-primary" onClick={onClose}>Done</button>}>
      <div className="notice warn"><Alert size={15} /><span>It's shown once. Share it privately. They'll be asked to replace it at first sign-in.</span></div>
      <Field label={info?.email}>
        <div className="row" style={{ gap: 6 }}>
          <code className="codeline grow">{info?.password}</code>
          <button className="btn btn-sm" onClick={() => { navigator.clipboard?.writeText(info?.password || ""); toast.ok("Copied"); }}><Copy size={13} /> Copy</button>
        </div>
      </Field>
    </Modal>
  );
}

function AccessRequests({ manage }) {
  const toast = useToast();
  const [requests, setRequests] = useState(null);
  const [busy, setBusy] = useState(0);

  const load = useCallback(() => {
    api.accessRequests().then((r) => setRequests(r.requests || [])).catch(() => setRequests([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const resolve = async (req, status) => {
    setBusy(req.id);
    try {
      await api.resolveAccessRequest(req.id, status);
      toast.ok(status === "granted" ? `Marked granted. ${req.name || req.email} has been emailed.` : "Request dismissed");
      load();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(0);
    }
  };

  if (!requests || requests.length === 0) return null;
  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div className="card-head">
        <div style={{ flex: 1 }}>
          <h3>Access requests <span className="badge warn">{requests.length} pending</span></h3>
          <p>Grant by adding the permission to their role in Roles & access, or by giving them a role that has it below. Then mark it granted so they are told.</p>
        </div>
        <Link className="btn btn-sm" to="/roles"><Key size={14} /> Roles & access</Link>
      </div>
      <div className="people">
        {requests.map((r) => (
          <div key={r.id} className="person2">
            <Avatar name={r.name} email={r.email} size={34} />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 650 }}>{r.name || r.email} <span className="tiny faint">{r.roleLabel || r.role}</span></div>
              <div className="small">
                wants <strong>{r.permissionLabel}</strong>{r.page ? <> for {r.page}</> : null}
                <span className="faint"> · {relativeTime(r.createdAt)}</span>
              </div>
              {r.note && <div className="tiny dim">"{r.note}"</div>}
            </div>
            {manage && (
              <div className="row" style={{ gap: 6, justifyContent: "flex-end" }}>
                <button className="btn btn-ghost btn-sm" disabled={busy === r.id} onClick={() => resolve(r, "dismissed")}>Dismiss</button>
                <button className="btn btn-primary btn-sm" disabled={busy === r.id} onClick={() => resolve(r, "granted")}><Check size={13} /> Mark granted</button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
