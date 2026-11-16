import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Alert, Bot, Pencil } from "./Icons";
import { Badge, Skeleton } from "./ui";
import { api } from "../lib/api";
import { fillPersona, SAMPLE_CUSTOMER } from "../lib/persona";

export default function AgentPicker({ channel, value, onChange, preferred = "", defaultTts = {}, customer = "", disabled = false }) {
  const [agents, setAgents] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.usecases()
      .then((r) => {
        const usable = (r.usecases || []).filter((u) => u.status !== "archived" && (u.channels || []).includes(channel));
        setAgents(usable);
        const keep = usable.find((u) => u.slug === value);
        const first = keep || usable.find((u) => u.slug === preferred) || usable.find((u) => u.status === "active") || usable[0];
        if (first) onChange(first);
      })
      .catch((e) => { setAgents([]); setError(e.message); });
  }, [channel]);

  if (!agents) return <Skeleton h={170} r={12} />;
  if (error) return <div className="notice halt"><Alert size={15} /><span>{error}</span></div>;
  if (!agents.length) {
    return (
      <div className="notice warn">
        <Alert size={15} />
        <span>No agent is switched on for this channel. Turn one on under <Link to="/agents">Agents</Link> → Channels & calls.</span>
      </div>
    );
  }

  const agent = agents.find((u) => u.slug === value);
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="field" style={{ margin: 0 }}>
        <label className="label" htmlFor={`agent-${channel}`}>Agent</label>
        <select id={`agent-${channel}`} className="input select" value={value} disabled={disabled}
          onChange={(e) => onChange(agents.find((u) => u.slug === e.target.value))}>
          {agents.map((u) => (
            <option key={u.slug} value={u.slug}>{u.name}{u.status === "draft" ? " (draft)" : ""}</option>
          ))}
        </select>
      </div>
      {agent && <AgentCard agent={agent} defaultTts={defaultTts} customer={customer} />}
    </div>
  );
}

function AgentCard({ agent, defaultTts, customer }) {
  const persona = agent.persona || {};
  const lang = agent.language?.default === "english" ? "english" : "hindi";
  const greeting = fillPersona(agent.greeting?.[lang] || "", persona, customer.trim() || SAMPLE_CUSTOMER, [...(agent.variables || []), ...(agent.global_variables || [])], { greeting: true });
  const engine = agent.voice?.tts_provider || defaultTts.provider || "";
  const voice = agent.voice?.voice_id || (agent.voice?.tts_provider ? "" : defaultTts.voice) || "";

  return (
    <div className="agentpick">
      <div className="agentpick-head">
        <span className="agentpick-icon"><Bot size={16} /></span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="agentpick-name">
            {agent.name}
            <Badge tone={agent.status === "active" ? "ok" : "warn"}>{agent.status}</Badge>
          </div>
          {agent.description && <div className="agentpick-desc">{agent.description}</div>}
        </div>
        <Link className="btn btn-ghost btn-sm" to={`/agents/${agent.slug}`}><Pencil size={13} /> Edit</Link>
      </div>
      <div className="agentpick-facts">
        <Fact label="Speaks as" value={[persona.agent_name, persona.agent_name_hindi].filter(Boolean).join(" · ") || "-"} />
        <Fact label="Language" value={`${lang}${agent.language?.allow_switch ? " · can switch" : ""}`} />
        <Fact label="Voice" value={[engine, voice].filter(Boolean).join(" · ") || "-"} />
        <Fact label="Model" value={agent.llm?.model || "-"} />
        <Fact label="Tools" value={String((agent.tools || []).length)} />
      </div>
      {greeting && (
        <div className="agentpick-greet">
          <span className="tiny faint">Opens with</span>
          <span>{greeting}</span>
        </div>
      )}
    </div>
  );
}

function Fact({ label, value }) {
  return (
    <div className="agentpick-fact">
      <span className="tiny faint">{label}</span>
      <span className="ellipsis" title={value}>{value}</span>
    </div>
  );
}
