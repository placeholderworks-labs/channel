import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import AgentPicker from "../components/AgentPicker";
import RecordForm, { missingFields, testFields, toRecord } from "../components/RecordForm";
import LatencyPanel from "../components/LatencyPanel";
import TokenPanel from "../components/TokenPanel";
import MicBar from "../components/MicBar";
import ResultFeed from "../components/ResultFeed";
import { Alert, Refresh, Sliders, Waves } from "../components/Icons";
import { api } from "../lib/api";
import { duration } from "../lib/format";
import useVoiceSession from "../hooks/useVoiceSession";

const TTS_PROVIDERS = ["murf", "gemini", "sarvam", "openai"];

export default function WebRTC({ status }) {
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
        <div className="skeleton" style={{ height: 30, width: 220 }} />
        <div className="skeleton" style={{ height: 420 }} />
      </div>
    );
  }

  return <Console webrtc={options.webrtc} status={status} reload={load} />;
}

function Console({ webrtc, status, reload }) {
  const live_channel = status?.channels?.find((c) => c.id === "website");
  const path = live_channel?.path || webrtc.path;
  const armed = live_channel?.enabled ?? webrtc.enabled;

  const [rate, setRate] = useState(webrtc.sampleRate);
  const [provider, setProvider] = useState(webrtc.ttsProvider);
  const [voice, setVoice] = useState(webrtc.tts[webrtc.ttsProvider]?.voice || "");
  const [model, setModel] = useState(webrtc.tts[webrtc.ttsProvider]?.model || "");

  const [params] = useSearchParams();
  const [picked, setPicked] = useState(null);
  const [testData, setTestData] = useState(null);
  const useCase = picked?.slug || "";

  const base = (() => {
    const p = picked?.voice?.tts_provider || webrtc.ttsProvider;
    return {
      provider: p,
      voice: picked?.voice?.voice_id || webrtc.tts[p]?.voice || "",
      model: webrtc.tts[p]?.model || "",
    };
  })();

  function pickAgent(agent) {
    setPicked(agent);
    const p = agent?.voice?.tts_provider || webrtc.ttsProvider;
    setProvider(p);
    setVoice(agent?.voice?.voice_id || webrtc.tts[p]?.voice || "");
    setModel(webrtc.tts[p]?.model || "");
  }

  const ttsCustom = provider !== base.provider || voice !== base.voice || model !== base.model;

  const session = useVoiceSession({
    wsPath: path,
    sampleRate: rate,
    tts: ttsCustom ? { provider, voice, model } : {},
    useCase,
    testRecord: testData?.reference || "",
  });

  const [elapsed, setElapsed] = useState(0);

  const live = session.status === "live";
  const busy = session.status === "requesting-mic" || session.status === "connecting";
  const locked = live || busy;

  useEffect(() => {
    if (!session.startedAt) {
      setElapsed(0);
      return;
    }
    const id = setInterval(
      () => setElapsed(Math.floor((Date.now() - session.startedAt) / 1000)),
      500
    );
    return () => clearInterval(id);
  }, [session.startedAt]);

  function pickProvider(next) {
    setProvider(next);
    setVoice(webrtc.tts[next]?.voice || "");
    setModel(webrtc.tts[next]?.model || "");
  }

  const dirty = rate !== webrtc.sampleRate || ttsCustom;
  const agentLanguage = picked?.language?.default || webrtc.language;

  const mode = !live
    ? "idle"
    : session.muted
    ? "muted"
    : session.botSpeaking
    ? "speaking"
    : "listening";

  const stateText = !live
    ? busy
      ? session.status === "requesting-mic"
        ? "Waiting for the microphone"
        : "Connecting"
      : "Ready when you are"
    : session.muted
    ? "Microphone off"
    : session.botSpeaking
    ? `${picked?.persona?.agent_name || "एजेंट"} बोल रही हैं`
    : session.workingOn
    ? session.workingOn
    : "बोलिए, मैं सुन रही हूँ";

  const hint = live
    ? session.botSpeaking
      ? "Speak over it and it stops to listen"
      : "No time limit here; talk as long as you like"
    : `${picked?.persona?.agent_name || "The agent"} greets you first, in ${agentLanguage === "english" ? "English" : "Hindi"}`;

  const keyMissing = !webrtc.tts[provider]?.keySet;
  const voiceChoices = webrtc.tts[provider]?.voices || [];

  return (
    <div className="page">
      <div className="page-head page-head-row">
        <div style={{ flex: 1, minWidth: 260 }}>
          <h1>Browser test</h1>
          <p>
            The website voicebot, in this tab. Pick what this one session runs on, then talk
            to it. Every turn is timed end to end.
          </p>
        </div>
        <div className="row">
          {live && (
            <span className="pill live">
              <span className="lamp live" />
              {duration(elapsed)}
            </span>
          )}
          <button className="btn btn-ghost btn-icon btn-sm" onClick={reload} aria-label="Reload">
            <Refresh size={14} />
          </button>
        </div>
      </div>

      {!armed && (
        <div className="notice warn" style={{ marginBottom: 14 }}>
          <Alert size={15} />
          <span>
            The website channel is off, so there is nothing to connect to.{" "}
            <Link to="/settings" style={{ fontWeight: 600 }}>
              Turn it on under Database
            </Link>{" "}
            . It applies to the next connection, no restart.
          </span>
        </div>
      )}

      <div className="rtc-layout">
        <div className="rtc-main">
          <section className="card play-card">
            <div className="card-head">
              <div style={{ flex: 1 }}>
                <h3>
                  <Waves size={15} />
                  Session
                </h3>
                <p>Ask about PlaceholderWorks out loud; anything the agent shows renders here.</p>
              </div>
            </div>

            <ResultFeed
              results={session.results}
              live={live}
              empty={
                live
                  ? "Voice agents, WhatsApp bots या pricing: बोलकर पूछिए, जो दिखाना हो यहीं दिखेगा।"
                  : "Start the session and ask what PlaceholderWorks builds. Anything the agent shows appears here."
              }
            />

            <MicBar
              session={session}
              mode={mode}
              live={live}
              busy={busy}
              armed={armed}
              stateText={stateText}
              hint={hint}
              onRestart={() => {
                session.stop();
                setTimeout(session.start, 300);
              }}
            />
          </section>

          <LatencyPanel turns={session.turns} live={live} />

          <TokenPanel turns={session.turns} usage={session.usage} live={live} />
        </div>

        <aside className="rtc-side">
          <section className="card rtc-panel">
            <div className="card-head">
              <div style={{ flex: 1 }}>
                <h3>This session only</h3>
                <p>
                  Applied when you press start. Real visitors are unaffected; their defaults
                  live in <Link to="/settings">Settings</Link>.
                </p>
              </div>
              {dirty && !locked && <span className="pill live">overridden</span>}
            </div>

            <div className="card-body stack" style={{ gap: 16 }}>
              <AgentPicker
                channel="website"
                value={useCase}
                onChange={pickAgent}
                preferred={params.get("use_case") || ""}
                defaultTts={{ provider: webrtc.ttsProvider, voice: webrtc.tts[webrtc.ttsProvider]?.voice }}
                disabled={locked}
              />

              <TestCallData agent={picked} locked={locked} value={testData} onChange={setTestData} />

              <div className="field">
                <span className="label">
                  Sample rate
                  <span className="label-note mono">{webrtc.sampleRate} default</span>
                </span>
                <div className="chipset">
                  {webrtc.sampleRates.map((value) => (
                    <button
                      key={value}
                      type="button"
                      className={`chip ${rate === value ? "on" : ""}`}
                      disabled={locked}
                      onClick={() => setRate(value)}
                    >
                      {value >= 1000 ? `${value / 1000}k` : value}
                    </button>
                  ))}
                </div>
                <p className="hint">
                  8k is what a phone line actually gives you, so it's the honest test. The pipeline
                  still listens at <span className="mono">{webrtc.pipelineRate}</span>; Silero
                  VAD takes nothing else.
                </p>
              </div>

              <div className="field">
                <label className="label" htmlFor="rtc-tts">
                  Voice engine
                  <span className="label-note mono">{base.provider} for this agent</span>
                </label>
                <select
                  id="rtc-tts"
                  className="input select"
                  value={provider}
                  disabled={locked}
                  onChange={(e) => pickProvider(e.target.value)}
                >
                  {TTS_PROVIDERS.map((name) => (
                    <option key={name} value={name}>
                      {name}
                      {webrtc.tts[name]?.keySet ? "" : " (no key)"}
                    </option>
                  ))}
                </select>
                {keyMissing && (
                  <p className="hint" style={{ color: "var(--warn)" }}>
                    No API key for {provider}. The session cannot start until one is set under
                    Settings → Common → Voice.
                  </p>
                )}
              </div>

              <div className="grid grid-2" style={{ gap: 10 }}>
                <div className="field">
                  <label className="label" htmlFor="rtc-voice">
                    Voice
                  </label>
                  {voiceChoices.length > 0 ? (
                    <select
                      id="rtc-voice"
                      className="input select"
                      value={voice}
                      disabled={locked}
                      onChange={(e) => setVoice(e.target.value)}
                    >
                      {voiceChoices.map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      id="rtc-voice"
                      className="input mono"
                      value={voice}
                      disabled={locked}
                      onChange={(e) => setVoice(e.target.value)}
                      placeholder={webrtc.tts[provider]?.voice || "default"}
                    />
                  )}
                </div>
                <div className="field">
                  <label className="label" htmlFor="rtc-model">
                    Model
                  </label>
                  <input
                    id="rtc-model"
                    className="input mono"
                    value={model}
                    disabled={locked}
                    onChange={(e) => setModel(e.target.value)}
                    placeholder={webrtc.tts[provider]?.model || "default"}
                  />
                </div>
              </div>

              <div className="rtc-summary">
                <Fact label="Agent" value={useCase || "-"} />
                <Fact label="Language" value={agentLanguage} />
                <Fact label="Listening" value={`${webrtc.pipelineRate} Hz`} />
                <Fact label="Playing" value={`${rate} Hz`} />
              </div>

              <div className="field">
                <span className="label">Connecting to</span>
                <code className="codeline codeline-sm">
                  {path}?sample_rate={rate}
                  {useCase ? `&use_case=${useCase}` : ""}
                  {ttsCustom && provider !== base.provider ? `&tts_provider=${provider}` : ""}
                </code>
                {locked && (
                  <p className="hint">Fixed for the life of a session. Hang up to change it.</p>
                )}
              </div>

              <Link className="btn btn-sm" to="/settings">
                <Sliders size={14} />
                Website defaults
              </Link>
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

function Fact({ label, value }) {
  return (
    <div className="rtc-fact">
      <span className="tiny faint">{label}</span>
      <span className="mono">{value}</span>
    </div>
  );
}

function TestCallData({ agent, locked, value, onChange }) {
  const [intakes, setIntakes] = useState([]);
  const [intakeId, setIntakeId] = useState("");
  const [record, setRecord] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    onChange(null);
    setRecord({});
    if (!agent?.slug) return;
    api.qmsForAgent(agent.slug)
      .then((r) => { setIntakes(r.intakes || []); setIntakeId((r.intakes || [])[0]?.id || ""); })
      .catch(() => setIntakes([]));
  }, [agent?.slug]);

  const intake = intakes.find((i) => i.id === intakeId);
  if (!agent || !intakes.length) return null;
  const fields = testFields(intake, intake.allFields.filter((f) => !["reference_id", "phone_number", "scheduled_at"].includes(f.key)));
  const missing = missingFields(fields, record);

  const use = async () => {
    setTouched(true);
    if (missing.length) return;
    setBusy(true);
    setError("");
    try {
      const r = await api.createTestRecord({ intake: intake.id, agent: agent.slug, record: toRecord(fields, record) });
      onChange({ reference: r.testRecord, intake: intake.name, facts: r.facts });
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="testdata">
      <div className="testdata-head">
        <strong>Call data</strong>
        <span className="tiny faint">optional · as the {intake.name} would send it</span>
      </div>
      {value ? (
        <>
          <div className="notice ok"><span>The next session starts with this data. The agent knows {value.facts.length} details.</span></div>
          <button className="btn btn-sm" disabled={locked} onClick={() => onChange(null)}>Edit or clear</button>
        </>
      ) : (
        <>
          {intakes.length > 1 && (
            <select className="input select" value={intakeId} onChange={(e) => { setIntakeId(e.target.value); setRecord({}); }}>
              {intakes.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
            </select>
          )}
          <RecordForm fields={fields} value={record} onChange={setRecord} touched={touched} />
          {error && <div className="notice halt"><span>{error}</span></div>}
          <button className="btn btn-primary btn-sm" disabled={busy || locked} onClick={use}>
            {busy ? "Checking…" : "Use this data"}
          </button>
        </>
      )}
    </div>
  );
}
