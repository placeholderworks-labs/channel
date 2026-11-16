import { Activity } from "./Icons";

const LEGS = [
  {
    key: "sttMs",
    label: "STT",
    tone: "stt",
    what: "nova-3: silence to the final transcript · Flux: time to first transcript",
  },
  { key: "llmMs", label: "LLM", tone: "llm", what: "the chatbot composing the reply" },
  { key: "ttsMs", label: "TTS", tone: "tts", what: "the voice engine's first audio chunk" },
  {
    key: "silenceMs",
    label: "SIL",
    tone: "silence",
    what: "dead air padded onto the head of the first audio chunk: heard, not measured by TTFB",
  },
];

function ms(value) {
  if (value === undefined || value === null) return "-";
  return value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${Math.round(value)} ms`;
}

function median(list) {
  if (!list.length) return null;
  const sorted = [...list].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

export default function LatencyPanel({ turns = [], live }) {
  const measured = turns.filter((t) => t.e2eMs !== undefined);
  const timed = turns.filter((t) => t.totalMs !== undefined);

  const e2e = measured.map((t) => t.e2eMs);
  const scale = Math.max(600, ...turns.map((t) => Math.max(t.e2eMs || 0, t.totalMs || 0)));

  const legMedians = LEGS.map((leg) => ({
    ...leg,
    value: median(timed.map((t) => t[leg.key]).filter((v) => v !== undefined && v !== null)),
  }));

  return (
    <section className="card latency">
      <div className="card-head">
        <div style={{ flex: 1 }}>
          <h3>
            <Activity size={15} />
            Latency
          </h3>
          <p>
            The four server legs are timed inside the pipeline. SIL is the silence the
            voice pads onto its first chunk, which lands after the turn is timed. End to end
            is measured in this tab, from when you stop speaking to the first audio sample playing,
            so it also carries both network hops and the playback lead.
          </p>
        </div>
      </div>

      <div className="latency-summary">
        <Stat
          label="End to end"
          hint={`median of ${measured.length || 0}`}
          value={ms(median(e2e))}
          tone="live"
        />
        {legMedians.map((leg) => (
          <Stat
            key={leg.key}
            label={leg.label}
            hint="median"
            value={ms(leg.value)}
            swatch={leg.tone}
            title={leg.what}
          />
        ))}
        <Stat label="Best" value={ms(e2e.length ? Math.min(...e2e) : null)} />
        <Stat label="Worst" value={ms(e2e.length ? Math.max(...e2e) : null)} />
      </div>

      {turns.length === 0 ? (
        <div className="empty">
          <h4>{live ? "Waiting for your first turn" : "No turns yet"}</h4>
          <p>
            {live
              ? "Say something. Each turn lands here as soon as the reply starts playing."
              : "Start a session and every turn's breakdown appears here."}
          </p>
        </div>
      ) : (
        <div className="latency-rows">
          <div className="latency-row latency-head tiny faint">
            <span>turn</span>
            <span>STT · LLM · TTS · SIL</span>
            <span className="latency-legs">breakdown</span>
            <span className="latency-total">end to end</span>
          </div>
          {[...turns].reverse().map((turn) => (
            <div key={turn.id} className="latency-row">
              <span className="latency-turn mono">#{turn.id}</span>

              <div className="latency-bar">
                {turn.totalMs !== undefined ? (
                  LEGS.map((leg) => (
                    <span
                      key={leg.key}
                      className={`latency-seg seg-${leg.tone}`}
                      style={{ width: `${((turn[leg.key] || 0) / scale) * 100}%` }}
                      title={`${leg.label} ${ms(turn[leg.key])}: ${leg.what}`}
                    />
                  ))
                ) : (
                  <span
                    className="latency-seg seg-pending"
                    style={{ width: `${((turn.e2eMs || 0) / scale) * 100}%` }}
                    title="server breakdown has not arrived yet"
                  />
                )}
                {turn.e2eMs !== undefined && (
                  <span
                    className="latency-mark"
                    style={{ left: `${Math.min(100, (turn.e2eMs / scale) * 100)}%` }}
                    title={`end to end ${ms(turn.e2eMs)}`}
                  />
                )}
              </div>

              <span className="latency-legs mono tiny">
                {turn.totalMs !== undefined
                  ? LEGS.map((leg) =>
                      turn[leg.key] == null ? "-" : Math.round(turn[leg.key])
                    ).join(" · ")
                  : "pending"}
              </span>

              <span className="latency-total mono">
                {ms(turn.e2eMs ?? turn.totalMs)}
                {turn.held && (
                  <span
                    className="held-tag tiny"
                    title="A hold line was spoken first, so this times the filler, not the answer"
                  >
                    hold
                  </span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="latency-key">
        {LEGS.map((leg) => (
          <span key={leg.key} className="row" style={{ gap: 6 }} title={leg.what}>
            <span className={`swatch seg-${leg.tone}`} />
            {leg.label}
          </span>
        ))}
        <span className="row" style={{ gap: 6 }}>
          <span className="swatch-mark" />
          end to end
        </span>
        <span className="grow" />
        <span className="tiny faint">
          the gap between the bar and the tick is network + playback lead; a row marked{" "}
          <span className="held-tag tiny">hold</span> heard a filler line first
        </span>
      </div>
    </section>
  );
}

function Stat({ label, value, hint, tone, swatch, title }) {
  return (
    <div className="latency-stat" title={title}>
      <div className="eyebrow row" style={{ gap: 5 }}>
        {swatch && <span className={`swatch seg-${swatch}`} />}
        {label}
      </div>
      <div className={`latency-stat-value mono ${tone || ""}`}>{value}</div>
      {hint && <div className="tiny faint">{hint}</div>}
    </div>
  );
}
