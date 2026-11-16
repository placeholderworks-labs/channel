import { createContext, useContext } from "react";

const T = {
  line: "var(--line-strong)",
  ink: "var(--ink)",
  muted: "var(--muted)",
  faint: "var(--faint)",
  surface: "var(--surface)",
  sunk: "var(--surface-sunk)",
  brand: "var(--brand)",
  brandWash: "var(--brand-wash)",
  brandLine: "var(--brand-line)",
  live: "var(--live)",
  liveWash: "var(--live-wash)",
  liveLine: "var(--live-line)",
  ok: "var(--ok)",
  okWash: "var(--ok-wash)",
  okLine: "var(--ok-line)",
  warn: "var(--warn)",
  warnWash: "var(--warn-wash)",
  warnLine: "var(--warn-line)",
};

const TONE = { line: T.line, brand: T.brand, live: T.live, ok: T.ok, warn: T.warn };

const FILL = {
  plain: { fill: T.surface, stroke: T.line },
  sunk: { fill: T.sunk, stroke: T.line },
  brand: { fill: T.brandWash, stroke: T.brandLine },
  live: { fill: T.liveWash, stroke: T.liveLine },
  ok: { fill: T.okWash, stroke: T.okLine },
  warn: { fill: T.warnWash, stroke: T.warnLine },
};

const FrameCtx = createContext("fig");

function Defs({ id }) {
  return (
    <defs>
      {Object.entries(TONE).map(([name, color]) => (
        <marker
          key={name}
          id={`${id}-${name}`}
          markerWidth="9"
          markerHeight="7"
          refX="8"
          refY="3.5"
          orient="auto"
        >
          <polygon points="0 0, 9 3.5, 0 7" fill={color} />
        </marker>
      ))}
    </defs>
  );
}

function Frame({ id, children, width, height, label, caption }) {
  return (
    <FrameCtx.Provider value={id}>
      <figure className="docs-figure">
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
          <Defs id={id} />
          {children}
        </svg>
        {caption && <figcaption className="docs-figcap tiny">{caption}</figcaption>}
      </figure>
    </FrameCtx.Provider>
  );
}

function Box({
  x,
  y,
  w,
  h,
  title,
  sub,
  tone = "plain",
  r = 8,
  titleSize = 12.5,
  mono = false,
  dashed = false,
}) {
  const { fill, stroke } = FILL[tone] || FILL.plain;
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={r}
        fill={fill}
        stroke={stroke}
        strokeDasharray={dashed ? "4 3" : undefined}
      />
      <text
        x={x + w / 2}
        y={sub ? y + h / 2 - 3 : y + h / 2 + 4}
        textAnchor="middle"
        fill={T.ink}
        fontSize={titleSize}
        fontWeight="600"
        fontFamily={mono ? "var(--mono)" : "var(--body)"}
      >
        {title}
      </text>
      {sub && (
        <text
          x={x + w / 2}
          y={y + h / 2 + 13}
          textAnchor="middle"
          fill={T.muted}
          fontSize="10.5"
          fontFamily="var(--mono)"
        >
          {sub}
        </text>
      )}
    </g>
  );
}

function Zone({ x, y, w, h, label, tone = "line" }) {
  const color = TONE[tone];
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={10}
        fill="none"
        stroke={color}
        strokeDasharray="4 4"
      />
      <text
        x={x + w / 2}
        y={y - 9}
        textAnchor="middle"
        fill={color}
        fontSize="10.5"
        fontWeight="600"
        fontFamily="var(--mono)"
      >
        {label}
      </text>
    </g>
  );
}

function Arrow({ from, to, label, dashed, tone = "line", labelAbove = true, flow = 0 }) {
  const frameId = useContext(FrameCtx);
  const color = TONE[tone] || T.line;
  const [x1, y1] = from;
  const [x2, y2] = to;
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  return (
    <g>
      <line
        x1={x1}
        y1={y1}
        x2={x2}
        y2={y2}
        stroke={color}
        strokeWidth="1.6"
        strokeDasharray={dashed ? "4 3" : undefined}
        markerEnd={`url(#${frameId}-${tone})`}
      />
      {flow > 0 && (
        <line
          className="flowline"
          style={{ "--delay": `${flow * 0.4}s` }}
          x1={x1}
          y1={y1}
          x2={x2}
          y2={y2}
          stroke={color}
          strokeWidth="2.6"
          strokeLinecap="round"
        />
      )}
      {label && (
        <text
          x={mx}
          y={labelAbove ? my - 6 : my + 14}
          textAnchor="middle"
          fill={T.faint}
          fontSize="10"
          fontFamily="var(--mono)"
        >
          {label}
        </text>
      )}
    </g>
  );
}

function Caption({ x, y, children, anchor = "start", tone = T.faint, size = 10.5 }) {
  return (
    <text x={x} y={y} textAnchor={anchor} fill={tone} fontSize={size} fontFamily="var(--mono)">
      {children}
    </text>
  );
}


export function SystemDiagram() {
  return (
    <Frame
      id="sys"
      width={900}
      height={470}
      label="System context: the three services and the vendors behind them"
      caption="Everything audible is owned by pipecat-v2v. Everything said is decided by pw-llm-layer. Neither one reaches into the other's database."
    >
      <Zone x={14} y={62} w={160} h={200} label="CUSTOMER" />
      <Box x={28} y={84} w={132} h={52} tone="sunk" title="Phone call" sub="PSTN 8k" />
      <Box x={28} y={180} w={132} h={52} tone="sunk" title="Browser tab" sub="mic + speaker" />

      <Zone x={228} y={62} w={252} h={252} label="PIPECAT-V2V" tone="brand" />
      <Box x={242} y={80} w={224} h={46} tone="brand" title="Channel + serializer" sub="5 wire formats" />
      <Box x={242} y={136} w={224} h={46} tone="brand" title="Media pipeline" sub="STT, engine, TTS" />
      <Box x={242} y={192} w={224} h={46} tone="brand" title="Action executor" sub="transfer, end, language" />
      <Box x={242} y={248} w={224} h={46} tone="brand" title="Console + settings" sub="dashboard, logs, drift" />

      <Zone x={570} y={62} w={220} h={130} label="PW-LLM-LAYER" tone="ok" />
      <Box x={584} y={80} w={192} h={44} tone="ok" title="/voice/chat" sub="callvoice, webvoice" />
      <Box x={584} y={134} w={192} h={44} tone="ok" title="prompt + model" sub="layered, tool bound" />

      <Zone x={570} y={220} w={220} h={94} label="TOOL-ECOSYSTEM" tone="live" />
      <Box x={584} y={238} w={192} h={40} tone="live" title="voice_* tools" sub="cart, discount, link" />
      <Box x={584} y={284} w={192} h={24} tone="live" title="inventory tools" titleSize={11} />

      <Arrow from={[162, 110]} to={[240, 96]} label="mu-law" flow={1} />
      <Arrow from={[162, 200]} to={[240, 112]} label="PCM" labelAbove={false} flow={1} />
      <Arrow from={[468, 156]} to={[582, 104]} label="HTTPS turn" flow={2} />
      <Arrow from={[680, 180]} to={[680, 234]} flow={3} />
      <Arrow from={[582, 262]} to={[468, 214]} label="voice_action" tone="live" flow={4} />

      <line x1="20" y1="352" x2="880" y2="352" stroke={T.line} strokeDasharray="3 4" />
      <Caption x={20} y={344}>EXTERNAL SERVICES</Caption>
      <Box x={20} y={372} w={158} h={48} tone="sunk" title="Deepgram" sub="STT" />
      <Box x={196} y={372} w={158} h={48} tone="sunk" title="Murf" sub="TTS" />
      <Box x={372} y={372} w={158} h={48} tone="sunk" title="Groq" sub="LLM" />
      <Box x={548} y={372} w={158} h={48} tone="sunk" title="Acefone" sub="PSTN + control" />
      <Box x={724} y={372} w={156} h={48} tone="sunk" title="Postgres x2" sub="state" />
      <Caption x={20} y={442}>
        pipeline owns Deepgram, Murf and Acefone; the chatbot owns Groq; each service owns one database
      </Caption>
    </Frame>
  );
}

export function DeploymentDiagram() {
  return (
    <Frame
      id="dep"
      width={880}
      height={400}
      label="Runtime topology: what listens where"
      caption="One FastAPI process serves the telephony sockets, the webhooks, the console API and the console itself. The route table is rebuilt from config rather than frozen at import."
    >
      <Zone x={14} y={44} w={196} h={272} label="INBOUND" />
      <Box x={26} y={62} w={172} h={44} tone="sunk" title="/ws/<channel>" sub="5 media sockets" mono />
      <Box x={26} y={118} w={172} h={44} tone="sunk" title="/webhooks/*" sub="acefone" mono />
      <Box x={26} y={174} w={172} h={44} tone="sunk" title="/api/admin/*" sub="console API" mono />
      <Box x={26} y={230} w={172} h={44} tone="sunk" title="/" sub="static console" mono />

      <Zone x={256} y={44} w={248} h={272} label="PIPECAT-V2V :8410" tone="brand" />
      <Box x={268} y={62} w={224} h={44} tone="brand" title="Dynamic route table" sub="rebuilt on reload" />
      <Box x={268} y={118} w={224} h={44} tone="brand" title="Channel handler" sub="transport + serializer" />
      <Box x={268} y={174} w={224} h={44} tone="brand" title="Pipeline task" sub="one per live call" />
      <Box x={268} y={230} w={224} h={44} tone="brand" title="Settings watcher" sub="re-reads every 15s" />

      <Zone x={556} y={44} w={218} h={124} label="PW-LLM-LAYER :8000" tone="ok" />
      <Box x={568} y={62} w={194} h={44} tone="ok" title="/voice/chat" mono />
      <Box x={568} y={118} w={194} h={40} tone="ok" title="/voice/settings" mono titleSize={11.5} />

      <Box x={256} y={330} w={248} h={46} tone="plain" title="pw_voicebot" sub="settings, calls, users" mono titleSize={11.5} />
      <Box x={556} y={196} w={218} h={46} tone="plain" title="pw-llm-layer" sub="voice_history" mono titleSize={11.5} />

      <Arrow from={[200, 84]} to={[266, 136]} />
      <Arrow from={[200, 140]} to={[266, 142]} />
      <Arrow from={[200, 196]} to={[266, 240]} />
      <Arrow from={[496, 190]} to={[566, 90]} label="turn" />
      <Arrow from={[496, 252]} to={[566, 134]} label="settings" dashed />
      <line x1="380" y1="316" x2="380" y2="328" stroke={T.line} strokeDasharray="3 3" />
      <line x1="665" y1="168" x2="665" y2="194" stroke={T.line} strokeDasharray="3 3" />
      <Caption x={524} y={352}>neither service can read</Caption>
      <Caption x={524} y={366}>the other's database</Caption>
    </Frame>
  );
}

export function ChannelDiagram() {
  const rows = [
    { name: "Acefone", wire: "mu-law 8k, JSON media", ser: "AcefoneFrameSerializer", tone: "brand" },
    { name: "Website", wire: "raw PCM, client rate", ser: "RawPCMFrameSerializer", tone: "ok" },
  ];
  const top = 46;
  const step = 50;
  return (
    <Frame
      id="chan"
      width={880}
      height={240}
      label="Two wire formats converge on one pipeline"
      caption="A channel owns its handshake, its serializer and its sample rates. Nothing below the serializer knows which provider is on the line. Adding one means a channel module and a serializer, nothing more."
    >
      <Caption x={20} y={32}>CHANNEL</Caption>
      <Caption x={250} y={32}>WIRE FORMAT</Caption>
      <Caption x={480} y={32}>SERIALIZER</Caption>
      {rows.map((row, i) => {
        const y = top + i * step;
        return (
          <g key={row.name}>
            <Box x={20} y={y} w={140} h={38} tone={row.tone || "sunk"} title={row.name} titleSize={12} />
            <text x={250} y={y + 23} fill={T.muted} fontSize="11" fontFamily="var(--mono)">
              {row.wire}
            </text>
            <Box x={470} y={y} w={210} h={38} tone="plain" title={row.ser} titleSize={10.5} mono />
            <Arrow from={[684, y + 19]} to={[734, 76 + i * 16]} tone="line" />
          </g>
        );
      })}
      <Box x={738} y={46} w={124} h={92} tone="brand" title="Shared" sub="pipeline core" />
      <Caption x={800} y={162} anchor="middle">
        identical for
      </Caption>
      <Caption x={800} y={176} anchor="middle">
        both
      </Caption>
      <line x1="20" y1="196" x2="860" y2="196" stroke={T.line} strokeDasharray="3 4" />
      <Caption x={20} y={216}>
        phone legs run 8k in and 8k out; the website runs 16k in (Silero) and 24k out (Murf)
      </Caption>
    </Frame>
  );
}


const STAGES = [
  { name: "transport.input()", note: "audio off the wire" },
  { name: "AudioRechunkerProcessor", note: "re-frame for Flux", optional: true },
  { name: "STTConnectGateProcessor", note: "hold audio until Deepgram answers", optional: true },
  { name: "stt", note: "Deepgram v1 or Flux", accent: "brand" },
  { name: "TranscriptRelayProcessor", note: "website only, user side", optional: true },
  { name: "user_aggregator", note: "turn strategies close the turn" },
  { name: "VoiceEngineProcessor", note: "HTTP to the brain", accent: "live" },
  { name: "ActionGateProcessor", note: "watches the audio drain" },
  { name: "TranscriptRelayProcessor", note: "website only, bot side", optional: true },
  { name: "LLMTextProcessor", note: "split into sentences" },
  { name: "SpokenTextSanitizer", note: "strip strays, spell digits" },
  { name: "GuardrailFilter", note: "mute leaked tool syntax" },
  { name: "_DuplicateSpeechFilter", note: "no repeats, one sign-off" },
  { name: "tts", note: "Murf, Gemini, Sarvam, OpenAI", accent: "brand" },
  { name: "OutputGainProcessor", note: "BOT_OUTPUT_GAIN_DB", optional: true },
  { name: "AmbienceMixerProcessor", note: "call-centre bed", optional: true },
  { name: "transport.output()", note: "audio back on the wire" },
  { name: "assistant_aggregator", note: "record what was said" },
];

export function PipelineDiagram() {
  const rowH = 32;
  const height = STAGES.length * rowH + 40;
  return (
    <Frame
      id="pipe"
      width={640}
      height={height}
      label="Pipeline processor order"
      caption="Dashed rows are conditional: they exist only when the channel or the configuration asks for them. Everything else is present on every call."
    >
      <Caption x={16} y={14}>PROCESSOR</Caption>
      <Caption x={330} y={14}>WHAT IT IS THERE FOR</Caption>
      {STAGES.map((stage, i) => {
        const y = 26 + i * rowH;
        const tone = stage.accent === "live" ? "live" : stage.accent === "brand" ? "brand" : "plain";
        const { fill, stroke } = FILL[tone];
        return (
          <g key={`${stage.name}-${i}`}>
            {i > 0 && (
              <>
                <line x1="40" y1={y - 10} x2="40" y2={y} stroke={T.line} strokeWidth="1.4" />
                <line
                  className="flowline"
                  style={{ "--delay": `${i * 0.14}s`, "--dur": "4s" }}
                  x1="40"
                  y1={y - 10}
                  x2="40"
                  y2={y}
                  stroke={T.brand}
                  strokeWidth="2.4"
                  strokeLinecap="round"
                />
              </>
            )}
            <rect
              x="16"
              y={y}
              width="300"
              height="24"
              rx="6"
              fill={fill}
              stroke={stroke}
              strokeDasharray={stage.optional ? "4 3" : undefined}
            />
            <text x="28" y={y + 16} fill={T.ink} fontSize="11" fontFamily="var(--mono)">
              {stage.name}
            </text>
            <text x="330" y={y + 16} fill={T.muted} fontSize="11" fontFamily="var(--body)">
              {stage.note}
            </text>
          </g>
        );
      })}
    </Frame>
  );
}

export function TurnDiagram() {
  const lanes = [
    { x: 78, label: "customer" },
    { x: 238, label: "STT" },
    { x: 410, label: "VoiceEngine" },
    { x: 610, label: "chatbot" },
    { x: 790, label: "TTS" },
  ];
  const steps = [
    { from: 0, to: 1, label: "speech", order: 1 },
    { from: 1, to: 2, label: "final transcript, turn closed", order: 2 },
    { from: 2, to: 3, label: "POST turn_kind=user", tone: "brand", order: 3 },
    { from: 2, to: 3, label: "POST turn_kind=hold, in parallel", dashed: true, order: 3 },
    { from: 3, to: 2, label: "hold line", order: 4 },
    { from: 2, to: 4, label: "speak the hold line", dashed: true, order: 5 },
    { from: 3, to: 2, label: "reply + voice_action", tone: "live", order: 6 },
    { from: 2, to: 4, label: "speak the answer", tone: "brand", order: 7 },
    { from: 4, to: 0, label: "audio", tone: "ok", order: 8 },
  ];
  const top = 80;
  const step = 34;
  const height = top + steps.length * step + 46;
  return (
    <Frame
      id="turn"
      width={880}
      height={height}
      label="One turn from air to air, including the hold race"
      caption="The hold request and the real request leave together. If the answer lands inside the hold delay the filler is dropped unheard and costs only its own tokens."
    >
      {lanes.map((lane) => (
        <g key={lane.label}>
          <rect x={lane.x - 62} y="16" width="124" height="30" rx="6" fill={T.sunk} stroke={T.line} />
          <text
            x={lane.x}
            y="36"
            textAnchor="middle"
            fill={T.ink}
            fontSize="11.5"
            fontWeight="600"
            fontFamily="var(--body)"
          >
            {lane.label}
          </text>
          <line
            x1={lane.x}
            y1="50"
            x2={lane.x}
            y2={height - 34}
            stroke={T.line}
            strokeDasharray="3 4"
          />
        </g>
      ))}
      {steps.map((s, i) => (
        <Arrow
          key={`${s.label}-${i}`}
          from={[lanes[s.from].x, top + i * step]}
          to={[lanes[s.to].x, top + i * step]}
          label={s.label}
          tone={s.tone || "line"}
          dashed={s.dashed}
          flow={s.order}
        />
      ))}
      <Caption x={440} y={height - 14} anchor="middle">
        a reply older than one already delivered is dropped by the watermark, however late it arrives
      </Caption>
    </Frame>
  );
}

export function ActionDiagram() {
  const lanes = [
    { x: 90, label: "chatbot" },
    { x: 260, label: "VoiceEngine" },
    { x: 430, label: "ActionGate" },
    { x: 600, label: "TTS + wire" },
    { x: 770, label: "Acefone" },
  ];
  const steps = [
    { y: 78, from: 0, to: 1, label: "reply + voice_action", order: 1 },
    { y: 116, from: 1, to: 3, label: "speak the handoff line", order: 2 },
    { y: 154, from: 1, to: 2, label: "wait_for_drain(snapshot)", order: 3 },
    { y: 192, from: 3, to: 2, label: "BotStoppedSpeaking", order: 4 },
    { y: 230, from: 2, to: 1, label: "drained", order: 5 },
    { y: 268, from: 1, to: 4, label: "POST /call/options", tone: "live", order: 6 },
  ];
  return (
    <Frame
      id="act"
      width={880}
      height={330}
      label="How a voice_action reaches the telephony provider"
      caption="The chatbot cannot dial, hang up or transfer. It returns an instruction, and the pipeline performs it once the audio it belongs to has actually played out."
    >
      {lanes.map((lane) => (
        <g key={lane.label}>
          <rect x={lane.x - 62} y="16" width="124" height="30" rx="6" fill={T.sunk} stroke={T.line} />
          <text
            x={lane.x}
            y="36"
            textAnchor="middle"
            fill={T.ink}
            fontSize="11.5"
            fontWeight="600"
            fontFamily="var(--body)"
          >
            {lane.label}
          </text>
          <line x1={lane.x} y1="50" x2={lane.x} y2="296" stroke={T.line} strokeDasharray="3 4" />
        </g>
      ))}
      {steps.map((s) => (
        <Arrow
          key={s.label}
          from={[lanes[s.from].x, s.y]}
          to={[lanes[s.to].x, s.y]}
          label={s.label}
          tone={s.tone || "line"}
          flow={s.order}
        />
      ))}
      <Caption x={430} y={314} anchor="middle">
        transfer leaves the customer on the line; only the bot leg stops
      </Caption>
    </Frame>
  );
}


export function SttDiagram() {
  const col = (x, w, tone, title, rows) => ({ x, w, tone, title, rows });
  const columns = [
    col(20, 400, "brand", "STT_PROVIDER=deepgram", [
      { t: "Deepgram v1 /listen", s: "interim + final transcripts" },
      { t: "SileroVADAnalyzer", s: "confidence 0.7, stop 0.2s" },
      { t: "MinWordsUserTurnStartStrategy", s: "MIN_WORDS_TO_INTERRUPT=3" },
      { t: "LocalSmartTurnAnalyzerV3", s: "SMART_TURN_STOP_SECS=2.5" },
      { t: "turn closed locally", s: "ONNX model in this process", tone: "brand" },
    ]),
    col(460, 400, "live", "STT_PROVIDER=deepgram_flux", [
      { t: "Deepgram v2 /listen", s: "flux-general-multi" },
      { t: "end of turn inside the model", s: "FLUX_EOT_THRESHOLD=0.7" },
      { t: "ExternalUserTurnStartStrategy", s: "interrupts from word one" },
      { t: "ExternalUserTurnStopStrategy", s: "50ms queue hop only" },
      { t: "turn closed by the vendor", s: "no local VAD is built", tone: "live" },
    ]),
  ];
  const top = 70;
  const rowH = 52;
  return (
    <Frame
      id="stt"
      width={880}
      height={top + 5 * rowH + 56}
      label="Two transcription paths and who decides the turn is over"
      caption="Turn-taking moves with the provider. On v1 this process decides; on Flux the model decides and the local analyzers are never constructed."
    >
      {columns.map((c) => (
        <g key={c.title}>
          <Box x={c.x} y={20} w={c.w} h={34} tone={c.tone} title={c.title} titleSize={12} mono />
          {c.rows.map((row, i) => {
            const y = top + i * rowH;
            return (
              <g key={row.t}>
                <Box
                  x={c.x + 20}
                  y={y}
                  w={c.w - 40}
                  h={40}
                  tone={row.tone || "plain"}
                  title={row.t}
                  sub={row.s}
                  titleSize={11.5}
                />
                {i < c.rows.length - 1 && (
                  <Arrow
                    from={[c.x + c.w / 2, y + 40]}
                    to={[c.x + c.w / 2, y + rowH]}
                    tone={c.tone === "live" ? "live" : "brand"}
                    flow={i + 1}
                  />
                )}
              </g>
            );
          })}
        </g>
      ))}
      <line x1={440} y1={20} x2={440} y2={top + 5 * rowH - 6} stroke={T.line} strokeDasharray="3 4" />
      <Caption x={440} y={top + 5 * rowH + 36} anchor="middle">
        set per channel: STT_PROVIDER_ACEFONE, STT_PROVIDER_WEBSITE, and so on
      </Caption>
    </Frame>
  );
}


export function LlmDiagram() {
  return (
    <Frame
      id="llm"
      width={880}
      height={400}
      label="How one turn is assembled and answered"
      caption="The large prefix is byte identical on every turn. Everything that moves per call sits after the history, which is what keeps the prompt cacheable."
    >
      <Caption x={20} y={28}>MESSAGE STACK, IN ORDER</Caption>
      <Box x={20} y={40} w={300} h={44} tone="brand" title="system: base + channel prompt" sub="identical every turn" titleSize={11.5} />
      <Box x={20} y={94} w={300} h={44} tone="plain" title="history: 10 or 12 turns" sub="voice_history table" titleSize={11.5} />
      <Box x={20} y={148} w={300} h={44} tone="warn" title="system: context block" sub="cart, seconds left, capabilities" titleSize={11.5} />
      <Box x={20} y={202} w={300} h={44} tone="plain" title="human: this turn" sub="the joined transcript" titleSize={11.5} />

      <Arrow from={[340, 145]} to={[406, 145]} tone="brand" flow={1} />

      <Box x={410} y={110} w={200} h={70} tone="live" title="model, tools bound" sub="temp 0.4, max 300" />
      <Arrow from={[510, 184]} to={[510, 228]} tone="live" flow={2} />
      <Box x={410} y={232} w={200} h={56} tone="plain" title="tool call" sub="voice_* or inventory" titleSize={11.5} />
      <Arrow from={[510, 292]} to={[510, 330]} flow={3} />
      <Box x={410} y={334} w={200} h={46} tone="plain" title="summary chain" sub="webvoice only" titleSize={11.5} dashed />

      <Arrow from={[614, 145]} to={[690, 145]} tone="ok" flow={4} />
      <Box x={694} y={100} w={170} h={90} tone="ok" title="reply JSON" sub="text + html + action" />

      <Caption x={694} y={214}>response_text, spoken</Caption>
      <Caption x={694} y={230}>response_html, screen</Caption>
      <Caption x={694} y={246}>voice_action, performed</Caption>
      <Caption x={694} y={262}>diagnostics, tokens</Caption>

      <line x1="20" y1="300" x2="380" y2="300" stroke={T.line} strokeDasharray="3 4" />
      <Caption x={20} y={322}>callvoice skips the summary chain:</Caption>
      <Caption x={20} y={338}>the tool already wrote its spoken line,</Caption>
      <Caption x={20} y={354}>so a tool turn costs one model call</Caption>
      <Caption x={20} y={370}>rather than three.</Caption>
    </Frame>
  );
}


export function TtsDiagram() {
  const stages = [
    { t: "Aggregate", s: "LLMTextProcessor", tone: "plain" },
    { t: "Sanitise", s: "strays, digits", tone: "plain" },
    { t: "Guardrail", s: "mute leaks", tone: "warn" },
    { t: "Duplicates", s: "window of six", tone: "warn" },
    { t: "Speak", s: "Murf falcon-2", tone: "brand" },
    { t: "Gain", s: "+5 dB", tone: "plain" },
    { t: "To the wire", s: "serializer", tone: "ok" },
  ];
  const w = 114;
  const gap = 10;
  return (
    <Frame
      id="tts"
      width={880}
      height={250}
      label="What happens to a sentence between the model and the speaker"
      caption="Three of these seven stages exist to stop something being spoken. A muted frame still flows downstream, so the transcript and the history stay accurate."
    >
      <Caption x={20} y={30}>ONE SENTENCE, LEFT TO RIGHT</Caption>
      {stages.map((stage, i) => {
        const x = 20 + i * (w + gap);
        return (
          <g key={stage.t}>
            <Box x={x} y={54} w={w} h={64} tone={stage.tone} title={stage.t} sub={stage.s} titleSize={12} />
            {i < stages.length - 1 && (
              <Arrow
                from={[x + w, 86]}
                to={[x + w + gap, 86]}
                tone={stage.tone === "brand" ? "brand" : "line"}
                flow={i + 1}
              />
            )}
          </g>
        );
      })}
      <line x1="20" y1="152" x2="860" y2="152" stroke={T.line} strokeDasharray="3 4" />
      <Caption x={20} y={174}>skip_tts is set, never dropped</Caption>
      <Caption x={20} y={190} tone={T.muted}>
        a muted frame reaches the aggregator, so the chatbot still learns what the turn contained
      </Caption>
      <Caption x={20} y={216}>rates</Caption>
      <Caption x={20} y={232} tone={T.muted}>
        Murf synthesises at 24k; the serializer resamples to 8k for a phone leg and passes 24k straight
        through to the browser
      </Caption>
    </Frame>
  );
}


export function LatencyDiagram() {
  const total = 560;
  const segs = [
    { w: 90, label: "STT", color: T.brand },
    { w: 300, label: "LLM", color: T.live },
    { w: 110, label: "TTS", color: T.ok },
  ];
  let x = 120;
  return (
    <Frame
      id="lat"
      width={760}
      height={178}
      label="What makes up a turn's latency"
      caption="LatencyObserver measures the server legs. The browser measures what the person actually waits for, which is always the larger number."
    >
      <text x="16" y="38" fill={T.muted} fontSize="11.5" fontFamily="var(--body)">
        customer stops speaking
      </text>
      <line x1="120" y1="46" x2="120" y2="132" stroke={T.ink} strokeWidth="1.5" />

      {segs.map((seg) => {
        const rect = (
          <g key={seg.label}>
            <rect x={x} y="56" width={seg.w} height="26" rx="4" fill={seg.color} opacity="0.85" />
            <text
              x={x + seg.w / 2}
              y="74"
              textAnchor="middle"
              fill="#fff"
              fontSize="11.5"
              fontWeight="600"
              fontFamily="var(--body)"
            >
              {seg.label}
            </text>
          </g>
        );
        x += seg.w;
        return rect;
      })}

      <rect x="120" y="94" width={total} height="18" rx="4" fill={T.sunk} stroke={T.line} />
      <rect x={120 + total - 60} y="94" width="60" height="18" rx="4" fill={T.line} opacity="0.6" />
      <text x={126} y="107" fill={T.muted} fontSize="10.5" fontFamily="var(--mono)">
        server total, what LatencyObserver measures
      </text>

      <line
        x1="120"
        y1="124"
        x2={120 + total + 60}
        y2="124"
        stroke={T.ink}
        strokeWidth="1.5"
        markerEnd="url(#lat-line)"
      />
      <text x={126} y="144" fill={T.ink} fontSize="11.5" fontWeight="600" fontFamily="var(--body)">
        end to end, plus network both ways and playback lead
      </text>
      <Caption x={126} y={160}>the browser measures this one; a phone caller feels it with nothing on screen</Caption>
    </Frame>
  );
}

export function ConfigDiagram() {
  return (
    <Frame
      id="cfg"
      width={880}
      height={260}
      label="Where a setting's value comes from"
      caption="The store wins over the file, which is what makes runtime edits possible and also how an edited .env appears to do nothing."
    >
      <Caption x={20} y={28}>RESOLUTION ORDER, FIRST MATCH WINS</Caption>
      <Box x={20} y={44} w={230} h={54} tone="brand" title="settings store" sub="Postgres, USE_DB=true" />
      <Arrow from={[254, 71]} to={[300, 71]} flow={1} />
      <Box x={304} y={44} w={230} h={54} tone="plain" title=".env / environment" sub="the file on disk" />
      <Arrow from={[538, 71]} to={[584, 71]} flow={2} />
      <Box x={588} y={44} w={230} h={54} tone="sunk" title="registry default" sub="src/settings/registry.py" />

      <line x1="20" y1="126" x2="860" y2="126" stroke={T.line} strokeDasharray="3 4" />

      <Caption x={20} y={150}>TWO STORES, EDITED FROM ONE SCREEN</Caption>
      <Box x={20} y={166} w={390} h={64} tone="plain" title="app_settings in pw_voicebot" sub="186 settings, written directly" />
      <Box x={430} y={166} w={390} h={64} tone="ok" title="voice_settings in pw-llm-layer" sub="24 settings, proxied over HTTP" />
      <Caption x={440} y={250} anchor="middle" tone={T.muted}>
        a draft touching both stores is still one Apply
      </Caption>
    </Frame>
  );
}
