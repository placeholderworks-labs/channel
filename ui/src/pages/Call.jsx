import { useCallback, useEffect, useMemo, useState } from "react";
import AgentPicker from "../components/AgentPicker";
import RecordForm, { missingFields, testFields, toRecord } from "../components/RecordForm";
import InlineSettings from "../components/InlineSettings";
import { Alert, Check, Chevron, Info, PhoneOut, Refresh } from "../components/Icons";
import { api } from "../lib/api";
import { relativeTime } from "../lib/format";
import { useToast } from "../lib/toast";


const BASIC_FIELDS = [
  { key: "customer_name", label: "Customer name", type: "text", required: true, description: "Used in the greeting." },
  { key: "phone_number", label: "Phone number", type: "phone", required: true, description: "10-digit mobile; +91 or 0 is stripped." },
];
const TEST_ONLY_HIDDEN = ["scheduled_at", "reference_id"];

export default function Call({ status, reload }) {
  const [options, setOptions] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setOptions(await api.playground());
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    return (
      <div className="page">
        <div className="notice halt">
          <Alert size={15} />
          <span>{error}</span>
        </div>
      </div>
    );
  }

  if (!options) {
    return (
      <div className="page stack">
        <div className="skeleton" style={{ height: 30, width: 200 }} />
        <div className="skeleton" style={{ height: 420 }} />
      </div>
    );
  }

  return (
    <Dialer
      options={options}
      status={status}
      reload={async () => {
        await load();
        await reload?.();
      }}
    />
  );
}

function Dialer({ options, reload, status }) {
  const toast = useToast();
  const channels = options.call.channels;

  const [channel, setChannel] = useState(
    channels.find((c) => c.enabled && !c.missing.length)?.id ||
      channels.find((c) => c.enabled)?.id ||
      channels[0]?.id ||
      ""
  );
  const [record, setRecord] = useState({});
  const [delaySecs, setDelaySecs] = useState("");
  const [touched, setTouched] = useState(false);
  const [serverErrors, setServerErrors] = useState({});
  const [agent, setAgent] = useState(null);
  const [intakes, setIntakes] = useState(null);
  const [intakeId, setIntakeId] = useState("");
  const intake = (intakes || []).find((i) => i.id === intakeId) || null;
  const fields = testFields(intake, (intake ? intake.allFields : BASIC_FIELDS).filter((f) => !TEST_ONLY_HIDDEN.includes(f.key)));

  useEffect(() => {
    if (!agent?.slug) return;
    setIntakes(null);
    api.qmsForAgent(agent.slug)
      .then((r) => { setIntakes(r.intakes || []); setIntakeId((r.intakes || [])[0]?.id || ""); })
      .catch(() => { setIntakes([]); setIntakeId(""); });
  }, [agent?.slug]);

  useEffect(() => {
    setRecord((current) => ({ customer_name: current.customer_name, phone_number: current.phone_number }));
    setServerErrors({});
    setTouched(false);
  }, [intakeId]);
  const [showSetup, setShowSetup] = useState(false);
  const [placing, setPlacing] = useState(false);
  const [result, setResult] = useState(null);
  const [recent, setRecent] = useState([]);

  const selected = useMemo(
    () => channels.find((c) => c.id === channel),
    [channels, channel]
  );

  const loadRecent = useCallback(
    () =>
      api
        .calls(10)
        .then((r) => setRecent(r.calls || []))
        .catch(() => setRecent([])),
    []
  );

  useEffect(() => {
    loadRecent();
  }, [loadRecent]);

  useEffect(() => {
    if (selected && (!selected.enabled || selected.missing.length)) setShowSetup(true);
  }, [selected]);

  const blocked = !selected?.enabled || (selected?.missing.length ?? 0) > 0;
  const missing = missingFields(fields, record);

  async function placeCall(event) {
    event.preventDefault();
    setTouched(true);
    if (missing.length) {
      toast.error(`Fill in: ${missing.map((f) => f.label || f.key).join(", ")}`);
      return;
    }
    setPlacing(true);
    setResult(null);
    try {
      const response = await api.placeCall({
        channel,
        delay_secs: delaySecs === "" ? null : Number(delaySecs),
        use_case: agent?.slug || "",
        intake: intake?.id || "",
        record: toRecord(fields, record),
      });
      setResult({ ok: true, ...response });
      toast.ok(response.message);
      loadRecent();
      reload?.();
    } catch (e) {
      const byField = {};
      for (const err of e.errors || []) if (err.field) byField[err.field] = err.error;
      setServerErrors(byField);
      setResult({ ok: false, message: e.message });
      toast.error(e.message);
      loadRecent();
    } finally {
      setPlacing(false);
    }
  }

  return (
    <div className="page">
      <div className="page-head page-head-row">
        <div style={{ flex: 1, minWidth: 260 }}>
          <h1>Phone test</h1>
          <p>
            Dial a real phone through the provider you pick. It uses the same scheduler and
            dialer an ingested record goes through. Everything the provider needs is editable right here.
          </p>
        </div>
        <div className="row">
          <button className="btn btn-ghost btn-icon btn-sm" onClick={reload} aria-label="Reload">
            <Refresh size={14} />
          </button>
        </div>
      </div>

      <div className="call-layout">
        <div className="call-main">
          <div className="provider-bar">
            <span className="provider-bar-label">Dial through</span>
            <div className="provider-chips" role="radiogroup" aria-label="Provider">
              {channels.map((item) => {
                const unavailable = !item.enabled;
                const incomplete = item.enabled && item.missing.length > 0;
                return (
                  <button
                    type="button"
                    role="radio"
                    aria-checked={channel === item.id}
                    key={item.id}
                    className={`provider-chip ${channel === item.id ? "on" : ""}`}
                    onClick={() => setChannel(item.id)}
                    title={item.path}
                  >
                    <span className={`lamp ${unavailable ? "" : incomplete ? "warn" : "live"}`} />
                    {item.name}
                    <span className={`tiny ${unavailable ? "faint" : incomplete ? "tone-warn" : "tone-ok"}`}>
                      {unavailable ? "off" : incomplete ? `missing ${item.missing.length}` : "ready"}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {blocked && selected && (
            <div className="notice warn">
              <Alert size={15} />
              <span>
                {!selected.enabled
                  ? `${selected.name} is switched off. Turn it on in Setup below. It applies to the next call, no restart.`
                  : `${selected.name} is missing ${selected.missing.join(", ")}. Fill that in under Setup below.`}
              </span>
            </div>
          )}

          <section className="card">
            <div className="card-head">
              <div style={{ flex: 1 }}>
                <h3>Agent</h3>
                <p>Who answers this call. The form below follows the QMS API connected to this agent.</p>
              </div>
            </div>
            <div className="card-body">
              <AgentPicker
                channel={channel}
                value={agent?.slug || ""}
                onChange={setAgent}
                preferred={status?.integrations?.ingestion?.agent || ""}
                defaultTts={status?.stack?.tts || {}}
                customer={record.customer_name || ""}
              />
            </div>
          </section>

          <form className="card" onSubmit={placeCall}>
            <div className="card-head">
              <div style={{ flex: 1 }}>
                <h3>Call data</h3>
                <p>Exactly what the QMS API would send for this agent. The agent hears all of it as the call's details.</p>
              </div>
            </div>

            <div className="card-body stack" style={{ gap: 14 }}>
              {intakes === null ? (
                <div className="skeleton" style={{ height: 120 }} />
              ) : (
                <>
                  {intakes.length > 1 && (
                    <div className="field" style={{ margin: 0 }}>
                      <label className="label">QMS API</label>
                      <select className="input select" value={intakeId} onChange={(e) => setIntakeId(e.target.value)}>
                        {intakes.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
                      </select>
                    </div>
                  )}
                  {intake ? (
                    <div className="notice">
                      <Info size={15} />
                      <span>Fields from <strong>{intake.name}</strong>. Every field marked <span className="req-star">*</span> is required, the same rule the live API follows, and nothing is dialled until they are all valid.</span>
                    </div>
                  ) : (
                    <div className="notice warn">
                      <Info size={15} />
                      <span>No QMS API is connected to {agent?.name || "this agent"}, so a call carries only the name and number. Connect one on the agent's QMS tab to give it real data.</span>
                    </div>
                  )}
                  <RecordForm fields={fields} value={record} touched={touched} errors={serverErrors}
                    onChange={(next) => { setRecord(next); setServerErrors({}); }} />
                  <div className="row" style={{ gap: 6, alignItems: "flex-end" }}>
                    <div className="field" style={{ margin: 0, width: 220 }}>
                      <label className="label">Delay before dialling</label>
                      <div className="numwrap">
                        <input className="input mono" type="number" min="0" step="1" value={delaySecs} onChange={(e) => setDelaySecs(e.target.value)} placeholder="0" />
                        <span className="numunit mono">s</span>
                      </div>
                    </div>
                  </div>
                </>
              )}

              {missing.length > 0 ? (
                <div className="notice warn">
                  <Info size={15} />
                  <span>Can't call yet. Still needed: <strong>{missing.map((f) => f.label || f.key).join(", ")}</strong>.</span>
                </div>
              ) : (
                <div className="notice ok"><Check size={15} /><span>Every required field is filled in.</span></div>
              )}

              <div className="row" style={{ gap: 10 }}>
                <button className="btn btn-live" type="submit"
                  disabled={placing || !channel || !agent || blocked || missing.length > 0 || intakes === null}
                  title={missing.length ? "Fill in every required field first" : undefined}>
                  <PhoneOut size={15} />
                  {placing ? "Placing…" : delaySecs ? "Schedule the call" : "Call now"}
                </button>
                <button type="button" className="btn btn-ghost btn-sm"
                  onClick={() => { setRecord({}); setTouched(false); setServerErrors({}); setResult(null); }}>
                  Clear
                </button>
              </div>

              {result && (
                <div className={`notice ${result.ok ? "ok" : "halt"}`}>
                  {result.ok ? <Check size={15} /> : <Alert size={15} />}
                  <div style={{ minWidth: 0 }}>
                    <div>{result.message}</div>
                    {result.providerResponse && (
                      <pre className="prewrap">{JSON.stringify(result.providerResponse, null, 2)}</pre>
                    )}
                  </div>
                </div>
              )}
            </div>
          </form>

          <section className="card">
            <div className="card-head">
              <div style={{ flex: 1 }}>
                <h3>Recent calls</h3>
                <p>Placed from here, or by a QMS intake.</p>
              </div>
              <button
                className="btn btn-ghost btn-icon btn-sm"
                onClick={loadRecent}
                aria-label="Refresh"
              >
                <Refresh size={14} />
              </button>
            </div>
            {recent.length === 0 ? (
              <div className="empty">
                <h4>No calls yet</h4>
                <p>Every call this server places shows up here.</p>
              </div>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <tbody>
                    {recent.map((call) => (
                      <tr key={call.id}>
                        <td>
                          <span className={`pill ${call.error ? "halt" : "ok"}`}>
                            {call.error ? "failed" : call.status}
                          </span>
                        </td>
                        <td className="mono">{call.phone}</td>
                        <td className="small dim">{call.channel}</td>
                        <td className="small dim">{relativeTime(call.createdAt)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>

        <aside className="call-side">
          <button
            type="button"
            className="disclose disclose-card"
            onClick={() => setShowSetup((v) => !v)}
            aria-expanded={showSetup}
          >
            <Chevron size={14} dir={showSetup ? "up" : "right"} />
            {selected?.name || "Provider"} setup
            <span className="grow" />
            <span className="tiny faint">
              {blocked ? "needs attention" : `${selected?.settings.length || 0} settings`}
            </span>
          </button>

          {showSetup && selected && (
            <InlineSettings
              title={`${selected.name} connection`}
              blurb="Credentials and the WebSocket path this provider streams audio to. Applies to the next call."
              settings={selected.settings}
              editable={options.editable}
              columns={1}
              onSaved={reload}
            />
          )}

          <InlineSettings
            title="During the call"
            blurb="The handful that actually change how a live call behaves."
            settings={options.call.settings}
            editable={options.editable}
            columns={1}
            onSaved={reload}
          />
        </aside>
      </div>
    </div>
  );
}

