import { Mic, PhoneOut } from "./Icons";

export default function SignalChain({ status }) {
  const stack = status?.stack || {};
  const channels = status?.channels || [];

  const stages = [
    {
      role: "Speech to text",
      name: (stack.stt?.provider || "-").toUpperCase(),
      detail: `${stack.stt?.model || ""}${
        stack.stt?.language ? ` · ${stack.stt.language}` : ""
      }`,
      ready: stack.stt?.ready,
      missing: "No Deepgram key",
    },
    {
      role: "Brain",
      name: (stack.llm?.provider || "-").toUpperCase(),
      detail: stack.llm?.model || "",
      ready: stack.llm?.ready,
      missing: "Chatbot not configured",
    },
    {
      role: "Voice",
      name: (stack.tts?.provider || "-").toUpperCase(),
      detail: [stack.tts?.voice, stack.tts?.model].filter(Boolean).join(" · "),
      ready: stack.tts?.ready,
      missing: `No ${stack.tts?.provider || "voice"} key`,
    },
  ];

  const allReady = stages.every((s) => s.ready);

  return (
    <section className="chain">
      <div className="chain-head">
        <span className="eyebrow">Signal path</span>
        <span className={`pill ${allReady ? "ok" : "halt"}`}>
          <span className={`lamp ${allReady ? "on" : "halt"}`} />
          {allReady ? "Ready to take a call" : "Not ready"}
        </span>
        <div className="grow" />
        <span className="small dim">
          {status?.app?.language} · {status?.app?.phoneBrain} / {status?.app?.websiteBrain}
        </span>
      </div>

      <div className="chain-body">
        <div className="chain-track">
          <div className="chain-end">
            <div className="chain-end-glyph">
              <Mic size={16} />
            </div>
            <div className="chain-end-label">Caller</div>
          </div>

          {stages.map((stage) => (
            <Stage key={stage.role} stage={stage} />
          ))}

          <div className={`chain-link ${allReady ? "hot" : ""}`} />

          <div className="chain-end">
            <div className="chain-end-glyph">
              <PhoneOut size={15} />
            </div>
            <div className="chain-end-label">Caller</div>
          </div>
        </div>
      </div>

      <div className="patchbay">
        {channels.map((channel) => {
          const blocked = channel.enabled && channel.missing.length > 0;
          return (
            <span
              key={channel.id}
              className={`patch ${channel.enabled ? "on" : ""} ${blocked ? "blocked" : ""}`}
              title={
                !channel.enabled
                  ? `${channel.name} is off`
                  : blocked
                  ? `${channel.name} is armed but missing: ${channel.missing.join(", ")}`
                  : `${channel.name} is armed at ${channel.path}`
              }
            >
              <span
                className={`lamp ${blocked ? "halt" : channel.enabled ? "live" : ""}`}
              />
              {channel.id}
              {channel.enabled && <span className="patch-path">{channel.path}</span>}
            </span>
          );
        })}
      </div>
    </section>
  );
}

function Stage({ stage }) {
  return (
    <>
      <div className={`chain-link ${stage.ready ? "hot" : ""}`} />
      <div className={`stage ${stage.ready ? "" : "blocked"}`}>
        <div className="stage-top">
          <span className={`lamp ${stage.ready ? "on" : "halt"}`} />
          <span className="stage-role">{stage.role}</span>
        </div>
        <div className="stage-name">{stage.name}</div>
        {stage.ready ? (
          <div className="stage-detail" title={stage.detail}>
            {stage.detail || "-"}
          </div>
        ) : (
          <div className="stage-miss">{stage.missing}</div>
        )}
      </div>
    </>
  );
}
