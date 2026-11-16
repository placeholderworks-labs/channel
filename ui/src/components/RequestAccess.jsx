import { useEffect, useState } from "react";
import { Check, Lock, Mail } from "./Icons";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { relativeTime } from "../lib/format";
import { useToast } from "../lib/toast";

let cache = null;
function loadMine() {
  cache = cache || api.myAccessRequests().catch(() => ({ requests: [], catalog: [] }));
  return cache;
}
export function forgetAccessRequests() {
  cache = null;
}

export default function RequestAccess({ perm, title, compact = false }) {
  const { user } = useAuth();
  const toast = useToast();
  const [mine, setMine] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    loadMine().then((r) => live && setMine(r));
    return () => { live = false; };
  }, []);

  const info = (mine?.catalog || []).find((p) => p.key === perm);
  const label = info?.label || perm;
  const pending = (mine?.requests || []).find((r) => r.permission === perm && r.status === "pending");
  const where = title || label;

  const ask = async () => {
    setBusy(true);
    try {
      const r = await api.requestAccess(perm, where, note);
      forgetAccessRequests();
      setMine(await loadMine());
      toast.ok(r.alreadyPending ? "Already requested. Your admin has it." : "Request sent to your admins");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const action = pending ? (
    <span className="ra-pending"><Check size={14} /> Requested {relativeTime(pending.createdAt)}, waiting for an admin</span>
  ) : (
    <button className={`btn btn-primary ${compact ? "btn-sm" : ""}`} onClick={ask} disabled={busy || !mine}>
      <Mail size={14} /> {busy ? "Sending…" : "Request access"}
    </button>
  );

  if (compact) {
    return (
      <div className="ra-compact">
        <span className="ra-compact-text"><Lock size={13} /> Needs <strong>{label}</strong></span>
        {action}
      </div>
    );
  }

  return (
    <div className="page">
      <div className="ra-card">
        <span className="ra-icon"><Lock size={22} /></span>
        <h2>You don't have access to {where}</h2>
        <p>
          This needs the <strong>{label}</strong> permission
          {user?.roleLabel ? <>, which your role <strong>{user.roleLabel}</strong> does not include</> : ""}.
          {info?.description ? ` ${info.description}` : ""}
        </p>
        {!pending && (
          <textarea className="input ra-note" rows={2} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)}
            placeholder="Why you need it (optional)" />
        )}
        {action}
        <p className="tiny faint" style={{ margin: 0 }}>Your admins get an email, and you get one when they decide.</p>
      </div>
    </div>
  );
}
