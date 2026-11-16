import {
  Bot, Database, Headset, History, Inbox, Lock, Mic2, PhoneCall, Server, Shield, Users, Waves, Wrench, Zap,
} from "../components/Icons";

const LAYERS = [
  {
    id: "people",
    title: "Who starts it",
    nodes: [
      { icon: Inbox, name: "Upstream systems", text: "Post customer records to a QMS intake, e.g. the Abandoned cart API" },
      { icon: PhoneCall, name: "Customers", text: "Pick up a call, or talk to the voice widget on the website" },
      { icon: Users, name: "Your team", text: "Build, test and watch everything in Voice Studio" },
    ],
  },
  {
    id: "voice",
    title: "pipecat-v2v · the voice service",
    sub: "Everything you can hear",
    nodes: [
      { icon: Inbox, name: "QMS", text: "Checks each record and queues the call" },
      { icon: Mic2, name: "Voice pipeline", text: "Listens, knows when you finished, speaks, handles interruptions" },
      { icon: Headset, name: "Phone and web lines", text: "Acefone calls and the website widget" },
      { icon: History, name: "History", text: "Every call: conversation, latency, summary" },
      { icon: Lock, name: "Console API", text: "Sign-in with email code, encrypted traffic, roles" },
    ],
  },
  {
    id: "brain",
    title: "pw-llm-layer · the brain",
    sub: "Everything the agent says and does",
    nodes: [
      { icon: Bot, name: "Agents", text: "Prompt, persona, greeting, variables, language" },
      { icon: Shield, name: "Guardrails", text: "What it must not discuss, and when to hand over" },
      { icon: Wrench, name: "Tools", text: "Factory tools, your HTTP APIs and MCP servers" },
      { icon: Zap, name: "Language model", text: "Writes each reply and decides which tool to use" },
    ],
  },
  {
    id: "outside",
    title: "What they rely on",
    nodes: [
      { icon: Waves, name: "Deepgram", text: "Speech to text" },
      { icon: Zap, name: "Groq", text: "The language model" },
      { icon: Mic2, name: "Murf", text: "Text to speech" },
      { icon: PhoneCall, name: "Acefone", text: "Phone lines and transfers" },
      { icon: Server, name: "MCP and APIs", text: "Outside systems the tools call" },
      { icon: Database, name: "Two Postgres databases", text: "Calls and settings · agents and memory" },
    ],
  },
];

const LINKS = [
  "a record, a call or a click",
  "each turn: what the customer said, and what this call can do",
  "speech, model, voice, phone and data",
];

export default function ArchitectureMap() {
  return (
    <figure className="archmap">
      {LAYERS.map((layer, i) => (
        <div key={layer.id}>
          <section className={`archmap-layer l-${layer.id}`} style={{ "--i": i }}>
            <header>
              <strong>{layer.title}</strong>
              {layer.sub && <span>{layer.sub}</span>}
            </header>
            <div className="archmap-nodes">
              {layer.nodes.map((n) => (
                <div key={n.name} className="archmap-node">
                  <span className="archmap-icon"><n.icon size={16} /></span>
                  <div>
                    <div className="archmap-name">{n.name}</div>
                    <div className="archmap-text">{n.text}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>
          {i < LINKS.length && (
            <div className="archmap-link" aria-hidden="true">
              <span className="archmap-arrow" style={{ "--i": i }} />
              <span className="archmap-label">{LINKS[i]}</span>
            </div>
          )}
        </div>
      ))}
      <figcaption className="tiny faint">
        Read top to bottom. The voice service never decides what to say, and the brain never touches the phone line.
      </figcaption>
    </figure>
  );
}

