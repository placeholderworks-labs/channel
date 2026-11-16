import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Alert, Clock, Copy, External, Inbox, Plus, X } from "./Icons";
import { Badge, Confirm, Modal, Skeleton, Toggle } from "./ui";
import { api } from "../lib/api";
import { endpointOf, span, stateOf, TYPE_LABELS } from "../lib/qms";
import { useToast } from "../lib/toast";

export default function AgentQms({ slug, agentName, editable, live, channels = [], onChange }) {
  const toast = useToast();
  const [catalog, setCatalog] = useState(null);
  const [error, setError] = useState("");
  const [pick, setPick] = useState("");
  const [asking, setAsking] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () =>
    api.qmsCatalog()
      .then((r) => { setCatalog(r); setError(""); })
      .catch((e) => setError(e.message));

  useEffect(() => { load(); }, [slug]);

  if (error) return <div className="notice halt"><Alert size={15} /><span>{error}</span></div>;
  if (!catalog) return <Skeleton h={260} r={14} />;

  const intakes = catalog.intakes || [];
  const mine = intakes.filter((i) => i.agent === slug);
  const others = intakes.filter((i) => i.agent !== slug);

  const liveOn = (intake) => !!live && channels.includes(intake.channel || "acefone");

  const connect = async (intake, agent, trigger = {}, pending = "") => {
    setBusy(true);
    try {
      const r = await api.connectIntake(intake.id, {
        agent,
        pending,
        delaySecs: trigger.delaySecs ?? intake.delaySecs,
        dedupeWindowSecs: trigger.dedupeWindowSecs ?? intake.dedupeWindowSecs,
        callHoursStart: trigger.callHoursStart ?? intake.callHoursStart,
        callHoursEnd: trigger.callHoursEnd ?? intake.callHoursEnd,
      });
      toast.ok(agent ? `${intake.name} now calls ${agentName || slug}` : `${intake.name} disconnected`);
      if (r.released?.released) toast.ok(`${r.released.released} held record${r.released.released === 1 ? "" : "s"} queued for calling`);
      else if (pending === "call" && intake.awaiting) toast.ok(`${intake.awaiting} held record${intake.awaiting === 1 ? "" : "s"} will be called once ${agentName || slug} is live`);
      setPick("");
      await load();
      onChange?.();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
      setAsking(null);
    }
  };

  const release = async (intake) => {
    setBusy(true);
    try {
      const r = await api.releaseIntake(intake.id);
      toast.ok(`${r.released} queued for calling${r.duplicate ? ` · ${r.duplicate} duplicate` : ""}${r.rejected ? ` · ${r.rejected} no longer valid` : ""}`);
      await load();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const startConnect = () => {
    const intake = intakes.find((i) => i.id === pick);
    if (!intake) return;
    if ((intake.agent && intake.agent !== slug) || intake.awaiting > 0) setAsking(intake);
    else connect(intake, slug);
  };

  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="aq-intro">
        <span className="aq-intro-icon"><Inbox size={18} /></span>
        <div>
          <strong>Where this agent's calls come from</strong>
          <p>Connect the QMS API that sends this agent its customers. Each record that API receives is checked against its payload, then called by this agent on the schedule below, and the agent hears every field on the call.</p>
        </div>
      </div>

      {mine.length === 0 && (
        <div className="aq-empty">
          <strong>No QMS API connected</strong>
          <span className="small faint">Calls to this agent come only from the Phone and Browser tests until one is connected.</span>
        </div>
      )}

      {mine.map((intake) => (
        <Connection key={intake.id} intake={intake} base={catalog.baseUrl} editable={editable} busy={busy}
          live={liveOn(intake)} onRelease={() => release(intake)}
          defaults={{ delay: catalog.delayDefault, dedupe: catalog.dedupeDefault }}
          onSave={(trigger) => connect(intake, slug, trigger)}
          onDisconnect={() => connect(intake, "")} />
      ))}

      {editable && (
        <div className="aq-connect">
          <select className="input select" value={pick} onChange={(e) => setPick(e.target.value)} aria-label="QMS API to connect">
            <option value="">{others.length ? "Choose a QMS API to connect…" : "Every QMS API is already connected here"}</option>
            {others.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name} · {i.path}{i.agent ? ` · currently calls ${i.agent}` : ""}{i.awaiting ? ` · ${i.awaiting} held` : ""}
              </option>
            ))}
          </select>
          <button className="btn btn-primary" disabled={!pick || busy} onClick={startConnect}><Plus size={14} /> Connect</button>
          <Link className="btn btn-ghost" to="/qms">Create a new API</Link>
        </div>
      )}

      {asking && (
        <ConnectDialog intake={asking} agentName={agentName || slug} live={liveOn(asking)} busy={busy}
          onConfirm={(pending) => connect(asking, slug, {}, pending)} onClose={() => setAsking(null)} />
      )}
    </div>
  );
}

const UNITS = [["h", 3600], ["min", 60], ["s", 1]];
function split(secs) {
  const n = Math.max(0, Math.round(Number(secs) || 0));
  const [unit, size] = UNITS.find(([, size]) => n % size === 0 && n >= size) || ["s", 1];
  return { n: String(n / size), unit };
}
const join = ({ n, unit }) => Math.round(Number(n || 0) * (UNITS.find(([u]) => u === unit) || UNITS[2])[1]);

function Duration({ value, onChange, disabled, label }) {
  return (
    <div className="aq-dur">
      <input className="input mono" type="number" min="0" step="1" value={value.n} disabled={disabled} aria-label={label}
        onChange={(e) => onChange({ ...value, n: e.target.value })} />
      <select className="input select" value={value.unit} disabled={disabled} aria-label={`${label} unit`}
        onChange={(e) => onChange({ ...value, unit: e.target.value })}>
        <option value="s">sec</option><option value="min">min</option><option value="h">hours</option>
      </select>
    </div>
  );
}

function Connection({ intake, base, editable, busy, live, defaults, onSave, onDisconnect, onRelease }) {
  const toast = useToast();
  const url = endpointOf(intake, base);
  const st = stateOf(intake);
  const initial = () => ({
    delay: split(intake.delaySecs ?? defaults.delay),
    hoursOn: !!(intake.callHoursStart && intake.callHoursEnd),
    start: intake.callHoursStart || "09:00",
    end: intake.callHoursEnd || "21:00",
    dedupe: split(intake.dedupeWindowSecs ?? defaults.dedupe),
  });
  const [form, setForm] = useState(initial);
  const [confirmOff, setConfirmOff] = useState(false);
  useEffect(() => { setForm(initial()); }, [intake.updatedAt]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const trigger = {
    delaySecs: join(form.delay),
    dedupeWindowSecs: join(form.dedupe),
    callHoursStart: form.hoursOn ? form.start : "",
    callHoursEnd: form.hoursOn ? form.end : "",
  };
  const was = initial();
  const dirty = JSON.stringify(form) !== JSON.stringify(was);
  const invalid = Number(form.delay.n) < 0 || Number(form.dedupe.n) < 0 || (form.hoursOn && (!form.start || !form.end || form.start === form.end));
  const own = (intake.allFields || []).filter((f) => !f.base);

  return (
    <section className="aq-card">
      <div className="aq-head">
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <strong className="aq-name">{intake.name}</strong>
            <Badge tone={st.tone} dot>{st.label}</Badge>
          </div>
          {intake.description && <div className="small faint">{intake.description}</div>}
        </div>
        <Link className="btn btn-ghost btn-sm" to={`/qms?api=${intake.id}`}><External size={13} /> Open in QMS</Link>
      </div>

      <div className="aq-endpoint">
        <span className="method">POST</span>
        <code className="mono ellipsis grow" title={url}>{url}</code>
        <button className="btn btn-ghost btn-icon btn-sm" aria-label="Copy endpoint"
          onClick={() => { navigator.clipboard?.writeText(url); toast.ok("Endpoint copied"); }}><Copy size={13} /></button>
      </div>
      {intake.awaiting > 0 && (
        <div className="aq-held">
          <Clock size={15} />
          <span>
            <strong>{intake.awaiting} record{intake.awaiting === 1 ? "" : "s"} trigger pending.</strong>{" "}
            {live ? "This agent is live, so they can be called now." : intake.releaseAfter
              ? "Records chosen for calling go out as soon as this agent is live (Active, on its channel)."
              : "Held; call them from here once this agent is live."}
          </span>
          {live && editable && <button className="btn btn-primary btn-sm" disabled={busy} onClick={onRelease}>Call {intake.awaiting} now</button>}
        </div>
      )}
      {!intake.tokenSet && <div className="notice warn"><Alert size={15} /><span>This API has no token yet, so it refuses every request. <Link to={`/qms?api=${intake.id}`}>Create one in QMS</Link>.</span></div>}

      <div>
        <div className="eyebrow" style={{ marginBottom: 8 }}>What the agent receives</div>
        <div className="aq-fields">
          <span className="aq-chip base">customer_name</span>
          <span className="aq-chip base">phone_number</span>
          <span className="aq-chip base">reference_id</span>
          {own.map((f) => (
            <span key={f.key} className={`aq-chip ${f.required ? "req" : ""}`} title={`${f.label || f.key} · ${TYPE_LABELS[f.type] || f.type}${f.required ? " · required" : ""}`}>
              {f.key}{f.required && <b>*</b>}
            </span>
          ))}
        </div>
        <p className="hint" style={{ margin: "8px 0 0" }}>
          On the call the agent gets these as <code>{"<call_details>"}</code>, and each is a placeholder in the context template. The Phone and Browser tests ask for the same fields.
        </p>
      </div>

      <div className="aq-trigger">
        <div className="eyebrow">When to call</div>
        <div className="aq-grid">
          <div className="aq-cell">
            <span className="small" style={{ fontWeight: 650 }}>Delay after a record arrives</span>
            <Duration value={form.delay} disabled={!editable} label="Delay" onChange={(v) => set("delay", v)} />
            <span className="tiny faint">{trigger.delaySecs > 0 ? `Rings ${span(trigger.delaySecs)} after it arrives.` : "Rings straight away."} A record's scheduled_at wins.</span>
          </div>
          <div className="aq-cell">
            <span className="row" style={{ gap: 8 }}>
              <Toggle size="sm" checked={form.hoursOn} disabled={!editable} onChange={(v) => set("hoursOn", v)} label="Calling hours" />
              <span className="small" style={{ fontWeight: 650 }}>Only call between</span>
            </span>
            <div className="aq-hours">
              <input className="input mono" type="time" value={form.start} disabled={!editable || !form.hoursOn} onChange={(e) => set("start", e.target.value)} aria-label="Calling hours start" />
              <span className="faint">to</span>
              <input className="input mono" type="time" value={form.end} disabled={!editable || !form.hoursOn} onChange={(e) => set("end", e.target.value)} aria-label="Calling hours end" />
            </div>
            <span className="tiny faint"><Clock size={11} /> IST. {form.hoursOn ? "A record outside these hours waits for them to open." : "Off: calls at any hour."}</span>
          </div>
          <div className="aq-cell">
            <span className="small" style={{ fontWeight: 650 }}>Skip duplicates within</span>
            <Duration value={form.dedupe} disabled={!editable} label="Duplicate window" onChange={(v) => set("dedupe", v)} />
            <span className="tiny faint">Same number or reference already queued or called in this window is not called again.</span>
          </div>
        </div>
      </div>

      {editable && (
        <div className="aq-actions">
          <button className="btn btn-ghost btn-sm aq-off" onClick={() => setConfirmOff(true)} disabled={busy}><X size={13} /> Disconnect</button>
          <span style={{ flex: 1 }} />
          {dirty && <button className="btn btn-ghost btn-sm" onClick={() => setForm(was)} disabled={busy}>Revert</button>}
          <button className="btn btn-primary btn-sm" disabled={!dirty || invalid || busy} onClick={() => onSave(trigger)}>Save timing</button>
        </div>
      )}

      <Confirm open={confirmOff} danger busy={busy} title={`Disconnect ${intake.name}?`} confirmLabel="Disconnect"
        body="Records it receives are still checked and logged in QMS, but nobody is called until an agent is connected again."
        onConfirm={() => { setConfirmOff(false); onDisconnect(); }} onClose={() => setConfirmOff(false)} />
    </section>
  );
}

function ConnectDialog({ intake, agentName, live, busy, onConfirm, onClose }) {
  const [choice, setChoice] = useState("call");
  const held = intake.awaiting || 0;
  const n = `${held} record${held === 1 ? "" : "s"}`;
  return (
    <Modal open width={560} onClose={onClose} title={`Connect ${intake.name}`}
      subtitle={`Its records will be called by ${agentName}.`}
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" disabled={busy} onClick={() => onConfirm(held ? choice : "")}>{busy ? "Connecting…" : "Connect"}</button>
      </>}>
      {intake.agent && (
        <div className="notice warn"><Alert size={15} /><span>It calls <strong>{intake.agent}</strong> today. From now on {agentName} calls its records instead.</span></div>
      )}
      {held > 0 && (
        <div className="stack" style={{ gap: 8 }}>
          <div className="small">
            <strong>{n} {held === 1 ? "is" : "are"} trigger pending.</strong> {held === 1 ? "It" : "They"} arrived valid while no live agent was connected.
          </div>
          <label className={`aq-choice ${choice === "call" ? "on" : ""}`}>
            <input type="radio" name="held" checked={choice === "call"} onChange={() => setChoice("call")} />
            <span>
              <strong>Call {held === 1 ? "it" : "them"} {live ? "now" : `as soon as ${agentName} is live`}</strong>
              <span className="tiny faint">On this API's schedule (delay and calling hours), spaced out so they ring one by one. Each record is checked again first; one no longer valid is not called.</span>
            </span>
          </label>
          <label className={`aq-choice ${choice === "hold" ? "on" : ""}`}>
            <input type="radio" name="held" checked={choice === "hold"} onChange={() => setChoice("hold")} />
            <span>
              <strong>Keep {held === 1 ? "it" : "them"} held</strong>
              <span className="tiny faint">Only new records are called. The held ones stay in QMS and can be called later from there.</span>
            </span>
          </label>
        </div>
      )}
    </Modal>
  );
}
