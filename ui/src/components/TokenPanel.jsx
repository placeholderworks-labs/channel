import { Database } from "./Icons";

function n(value) {
  if (value === undefined || value === null) return "-";
  return Number(value).toLocaleString();
}

export default function TokenPanel({ turns = [], usage, live }) {
  const timed = turns.filter((t) => t.totalTokens !== undefined);
  const hit = usage?.promptTokens ? (usage.cachedTokens / usage.promptTokens) * 100 : null;
  const perTurn = usage?.turns ? Math.round(usage.totalTokens / usage.turns) : null;

  return (
    <section className="card latency">
      <div className="card-head">
        <div style={{ flex: 1 }}>
          <h3>
            <Database size={15} />
            LLM tokens
          </h3>
          <p>
            Counted by the chatbot and sent back with each turn. The model runs there, so
            the pipeline has no usage of its own to report. The whole prompt is re-sent
            every turn, which is what makes the cache hit the number worth watching.
          </p>
        </div>
      </div>

      <div className="latency-summary">
        <Stat label="Total" value={n(usage?.totalTokens)} hint="this session" tone="live" />
        <Stat label="Input" value={n(usage?.promptTokens)} hint="prompt" swatch="stt" />
        <Stat
          label="Cached"
          value={hit === null ? "-" : `${hit.toFixed(0)}%`}
          hint={usage ? `${n(usage.cachedTokens)} of input` : "of input"}
          swatch="tts"
        />
        <Stat label="Output" value={n(usage?.completionTokens)} hint="completion" swatch="llm" />
        <Stat label="Per turn" value={n(perTurn)} hint="average" />
      </div>

      {timed.length === 0 ? (
        <div className="empty">
          <h4>{live ? "Waiting for the first turn" : "No turns yet"}</h4>
          <p>Each turn's token usage lands here as soon as the reply arrives.</p>
        </div>
      ) : (
        <div className="latency-rows">
          <div className="latency-row tok-row latency-head tiny faint">
            <span>turn</span>
            <span>input</span>
            <span>cached</span>
            <span>output</span>
            <span className="latency-total">total</span>
          </div>
          {[...timed].reverse().map((turn) => (
            <div key={turn.id} className="latency-row tok-row">
              <span className="latency-turn mono">#{turn.id}</span>
              <span className="mono tiny">{n(turn.promptTokens)}</span>
              <span className="mono tiny tok-cached">{n(turn.cachedTokens)}</span>
              <span className="mono tiny">{n(turn.completionTokens)}</span>
              <span className="latency-total mono">{n(turn.totalTokens)}</span>
            </div>
          ))}
        </div>
      )}

      {usage?.ttsCharacters > 0 && (
        <div className="latency-key">
          <span className="tiny faint">
            {n(usage.ttsCharacters)} characters sent to the voice engine this session
          </span>
        </div>
      )}
    </section>
  );
}

function Stat({ label, value, hint, tone, swatch }) {
  return (
    <div className="latency-stat">
      <div className="eyebrow row" style={{ gap: 5 }}>
        {swatch && <span className={`swatch seg-${swatch}`} />}
        {label}
      </div>
      <div className={`latency-stat-value mono ${tone || ""}`}>{value}</div>
      {hint && <div className="tiny faint">{hint}</div>}
    </div>
  );
}
