import { useEffect, useRef, useState } from "react";
import {
  ActionDiagram,
  ChannelDiagram,
  ConfigDiagram,
  DeploymentDiagram,
  LatencyDiagram,
  LlmDiagram,
  PipelineDiagram,
  SttDiagram,
  SystemDiagram,
  TtsDiagram,
  TurnDiagram,
} from "../docs/diagrams";
import ArchitectureMap from "../docs/ArchitectureMap";
import FlowStrip from "../docs/FlowStrip";
import Timeline from "../docs/Timeline";
import {
  Activity,
  Alert,
  Bot,
  Check,
  Database,
  Gauge,
  Globe,
  Inbox,
  Key,
  Server,
  Mic,
  PhoneOut,
  Plug,
  Sliders,
  Transfer,
  Waves,
} from "../components/Icons";

const PARTS = [
  {
    part: "Overview",
    sections: [
      {
        id: "what",
        label: "What this system is",
        icon: Gauge,
        summary: "One pipeline, one brain, two surfaces, and a strict line between them.",
        subs: [
          { id: "what-map", label: "The system at a glance" },
          { id: "what-call", label: "A call, end to end" },
          { id: "what-split", label: "Division of responsibility" },
          { id: "what-surfaces", label: "The two surfaces" },
          { id: "what-words", label: "Vocabulary" },
        ],
      },
    ],
  },
  {
    part: "Voice AI Studio",
    sections: [
      {
        id: "studio-agents",
        label: "Agents",
        icon: Bot,
        summary: "One agent is one complete voice persona, configured end to end from the console.",
        subs: [
          { id: "studio-agent-parts", label: "What an agent holds" },
          { id: "studio-placeholders", label: "Placeholders and variables" },
          { id: "studio-guardrails", label: "The guardrail library" },
          { id: "studio-save", label: "Saving and propagation" },
        ],
      },
      {
        id: "studio-tools",
        label: "Tools and MCP servers",
        icon: Server,
        summary: "Factory tools, your own HTTP APIs, and MCP servers, and how an agent gets them.",
        subs: [
          { id: "studio-tool-kinds", label: "Three kinds of tool" },
          { id: "studio-mcp", label: "Connecting an MCP server" },
          { id: "studio-language-tool", label: "Language switching is a tool" },
        ],
      },
      {
        id: "studio-qms",
        label: "QMS and History",
        icon: Inbox,
        summary: "Where customer calls enter the system, and the record of what became of each one.",
        subs: [
          { id: "studio-intakes", label: "QMS APIs" },
          { id: "studio-contract", label: "The record contract" },
          { id: "studio-lifecycle", label: "Record lifecycle" },
          { id: "studio-history", label: "History, retry and cancel" },
          { id: "studio-call-detail", label: "Inside a call" },
        ],
      },
      {
        id: "studio-access",
        label: "Access and team",
        icon: Key,
        summary: "Roles, permissions, invitations, the sign-in code, payload encryption and secrets.",
        subs: [
          { id: "studio-roles", label: "Roles and permissions" },
          { id: "studio-invites", label: "Invitations and passwords" },
          { id: "studio-otp", label: "Two-step sign-in" },
          { id: "studio-encryption", label: "Encrypted console traffic" },
          { id: "studio-secrets", label: "Secrets on screen" },
        ],
      },
    ],
  },
  {
    part: "High level design",
    sections: [
      {
        id: "hld-context",
        label: "System context",
        icon: Globe,
        summary: "Three services, four vendors, and the only paths between them.",
        subs: [
          { id: "hld-services", label: "The three services" },
          { id: "hld-vendors", label: "External dependencies" },
          { id: "hld-boundaries", label: "Boundaries that matter" },
        ],
      },
      {
        id: "hld-runtime",
        label: "Runtime topology",
        icon: Plug,
        summary: "What listens on which path, and what survives a config change.",
        subs: [
          { id: "hld-routes", label: "One process, many routes" },
          { id: "hld-stores", label: "Two databases" },
          { id: "hld-restart", label: "What needs a restart" },
        ],
      },
    ],
  },
  {
    part: "Low level design",
    sections: [
      {
        id: "lld-pipeline",
        label: "The processor chain",
        icon: Plug,
        summary: "Nineteen positions in one list, identical on every channel.",
        subs: [
          { id: "lld-order", label: "Order, and why it is that order" },
          { id: "lld-conditional", label: "Conditional processors" },
          { id: "lld-frames", label: "The frame contract" },
        ],
      },
      {
        id: "lld-turn",
        label: "One turn, in detail",
        icon: Activity,
        summary: "From the last syllable to the first sample of the reply.",
        subs: [
          { id: "lld-close", label: "Closing the turn" },
          { id: "lld-race", label: "The parallel race" },
          { id: "lld-stale", label: "Barge in and stale replies" },
        ],
      },
      {
        id: "lld-actions",
        label: "The reverse path",
        icon: Alert,
        summary: "How a chatbot with no telephony access transfers a live call.",
        subs: [
          { id: "lld-action-shape", label: "What an action is" },
          { id: "lld-gate", label: "The drain gate" },
          { id: "lld-checks", label: "Seven checks, in order" },
        ],
      },
    ],
  },
  {
    part: "Speech to text",
    sections: [
      {
        id: "stt",
        label: "Speech to text",
        icon: Mic,
        summary: "Two Deepgram APIs, two turn-taking models, tuned per channel.",
        subs: [
          { id: "stt-engines", label: "Engines and models" },
          { id: "stt-turns", label: "Who decides the turn is over" },
          { id: "stt-tuning", label: "Per channel tuning" },
          { id: "stt-connect", label: "Connection and framing" },
          { id: "stt-script", label: "Script normalisation" },
        ],
      },
    ],
  },
  {
    part: "The language model",
    sections: [
      {
        id: "llm",
        label: "The language model",
        icon: Globe,
        summary: "Every word spoken is decided in another process, over HTTP.",
        subs: [
          { id: "llm-contract", label: "The turn contract" },
          { id: "llm-prompt", label: "Prompt layering and caching" },
          { id: "llm-tools", label: "Tools and voice actions" },
          { id: "llm-kinds", label: "Turn kinds and hold lines" },
          { id: "llm-channels", label: "callvoice against webvoice" },
        ],
      },
    ],
  },
  {
    part: "Text to speech",
    sections: [
      {
        id: "tts",
        label: "Text to speech",
        icon: Waves,
        summary: "Four providers behind one factory, and four filters in front of them.",
        subs: [
          { id: "tts-providers", label: "Providers and voices" },
          { id: "tts-hygiene", label: "What never reaches the speaker" },
          { id: "tts-audio", label: "Rates, gain and ambience" },
          { id: "tts-language", label: "Switching language mid call" },
        ],
      },
    ],
  },
  {
    part: "Telephony",
    sections: [
      {
        id: "tel",
        label: "Telephony",
        icon: PhoneOut,
        summary: "One carrier, one dial path, one transfer that works.",
        subs: [
          { id: "tel-wire", label: "Wire formats and serializers" },
          { id: "tel-dial", label: "Placing a call" },
          { id: "tel-lifecycle", label: "Lifecycle and webhooks" },
          { id: "tel-transfer", label: "Transfer to a human" },
          { id: "tel-limits", label: "Ending a call" },
        ],
      },
    ],
  },
  {
    part: "Walkthroughs",
    sections: [
      {
        id: "walk-call",
        label: "A call, end to end",
        icon: Transfer,
        summary: "The production abandoned cart flow, from trigger to transfer.",
        subs: [
          { id: "walk-call-strip", label: "The seven stages" },
          { id: "walk-call-timeline", label: "A worked call" },
        ],
      },
      {
        id: "walk-web",
        label: "A browser session",
        icon: Mic,
        summary: "The same pipeline, with a screen to render onto.",
        subs: [
          { id: "walk-web-strip", label: "The six stages" },
          { id: "walk-web-timeline", label: "A worked session" },
        ],
      },
    ],
  },
  {
    part: "Operations",
    sections: [
      {
        id: "ops-latency",
        label: "Latency and cost",
        icon: Activity,
        summary: "What is measured per turn, and what each turn is worth in rupees.",
        subs: [
          { id: "ops-budget", label: "The three legs" },
          { id: "ops-cost", label: "What a call costs" },
        ],
      },
      {
        id: "ops-config",
        label: "Configuration",
        icon: Database,
        summary: "Every voice setting lives in the database. .env only bootstraps it.",
        subs: [
          { id: "ops-resolution", label: "Where a value comes from" },
          { id: "ops-envonly", label: "Env only by design" },
          { id: "ops-bootstrap", label: "First boot and recovery" },
        ],
      },
      {
        id: "ops-settings",
        label: "The Settings screen",
        icon: Sliders,
        summary: "How an edit reaches a call that is already in progress.",
        subs: [
          { id: "ops-layout", label: "How it is organised" },
          { id: "ops-save", label: "Where a save goes" },
          { id: "ops-inherit", label: "Empty is a value" },
          { id: "ops-validate", label: "Validation and secrets" },
        ],
      },
    ],
  },
];

const SECTIONS = PARTS.flatMap((p) => p.sections);

const META = Object.fromEntries(
  PARTS.flatMap((group, index) =>
    group.sections.map((section) => [
      section.id,
      { part: group.part, index: index + 1, icon: section.icon, summary: section.summary },
    ])
  )
);

const SECTION_OF = Object.fromEntries(
  SECTIONS.flatMap((section) => [
    [section.id, section.id],
    ...(section.subs || []).map((sub) => [sub.id, section.id]),
  ])
);

const TRACKED = Object.keys(SECTION_OF);

export default function Docs() {
  const [active, setActive] = useState(SECTIONS[0].id);
  const bodyRef = useRef(null);

  useEffect(() => {
    const root = bodyRef.current;
    if (!root) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (visible) setActive(visible.target.id);
      },
      { root, rootMargin: "-10% 0px -72% 0px", threshold: 0 }
    );
    TRACKED.forEach((id) => {
      const el = root.querySelector(`#${id}`);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, []);

  const jump = (id) => {
    const el = bodyRef.current?.querySelector(`#${id}`);
    el?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const activeSection = SECTION_OF[active] || SECTIONS[0].id;

  return (
    <div className="docs-page">
      <div className="docs-bar">
        <div className="settings-title">
          <h1>Docs</h1>
          <span className="tiny faint">
            How the voicebot is built, from a customer speaking to a call being handed to a person
          </span>
        </div>
      </div>

      <div className="docs-body">
        <nav className="docs-nav">
          {PARTS.map((group, index) => (
            <div key={group.part} className="docs-nav-topic">
              <div className="settings-nav-label">
                <span className="docs-nav-n mono">{String(index + 1).padStart(2, "0")}</span>
                {group.part}
              </div>
              {group.sections.map((section) => (
                <div key={section.id}>
                  <button
                    className={`settings-nav-item docs-nav-item ${
                      activeSection === section.id ? "on" : ""
                    }`}
                    onClick={() => jump(section.id)}
                  >
                    <section.icon size={14} />
                    <span className="ellipsis">{section.label}</span>
                  </button>
                  {activeSection === section.id && section.subs && (
                    <div className="docs-nav-subs">
                      {section.subs.map((sub) => (
                        <button
                          key={sub.id}
                          className={`docs-nav-sub ${active === sub.id ? "on" : ""}`}
                          onClick={() => jump(sub.id)}
                        >
                          <span className="ellipsis">{sub.label}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ))}
        </nav>

        <article className="docs-content" ref={bodyRef}>

          <Section id="what" title="What this system is">
            <p className="lede">
              One pipeline, one brain, two surfaces. This service owns everything you can
              hear: transcription, turn taking, interruptions, speech, and the telephony wire
              formats. It owns no conversation logic at all.
            </p>

            <Sub id="what-map">The system at a glance</Sub>
            <p>
              Two services do all the work. <strong>pipecat-v2v</strong> handles everything you
              can hear and everything the team sees in Voice AI Studio.{" "}
              <strong>pw-llm-layer</strong> is the brain: it decides what the agent says and
              which tools it uses.
            </p>
            <ArchitectureMap />

            <Sub id="what-call">A call, end to end</Sub>
            <FlowStrip
              note="Every turn of the conversation repeats steps 4 to 6 until the call ends."
              stages={[
                { icon: Inbox, title: "1 · Request", who: "QMS", tone: "brand", detail: "a record arrives and is checked" },
                { icon: PhoneOut, title: "2 · Dial", who: "Acefone", detail: "the customer's phone rings" },
                { icon: Mic, title: "3 · Greet", who: "agent", detail: "opens with the agent's greeting" },
                { icon: Waves, title: "4 · Listen", who: "Deepgram", detail: "speech becomes text" },
                { icon: Bot, title: "5 · Think", who: "brain", tone: "act", detail: "reply, and a tool if needed" },
                { icon: Mic, title: "6 · Speak", who: "Murf", detail: "the reply becomes voice" },
                { icon: Check, title: "7 · Record", who: "History", tone: "done", detail: "conversation, latency, summary" },
              ]}
            />
            <Steps
              ordered
              items={[
                { t: "A request comes in", d: "An upstream system posts a customer record to a QMS intake, or someone uses the Phone test. Anything missing or invalid is rejected and never called." },
                { t: "The call is placed", d: "After a short delay the record is dialled through Acefone with the agent that intake is set up for." },
                { t: "The conversation runs", d: "Deepgram turns the customer's speech into text, the brain writes the reply (calling a tool when it needs facts or must act), and Murf speaks it. The customer can interrupt at any time." },
                { t: "Actions happen on the line", d: "Transfer to a person, sending the booking link or ending the call are carried out by the voice service once the agent finishes speaking." },
                { t: "Everything is recorded", d: "When the call ends, History keeps the conversation, the latency of every turn, the providers used and a written summary." },
              ]}
            />

            <Sub id="what-split">Division of responsibility</Sub>
            <p>
              Every word the bot says comes from <strong>pw-llm-layer</strong> over HTTP, and
              every capability it offers comes from tools registered in{" "}
              <strong>tool-ecosystem</strong>. This process runs no model of its own. The
              split is not stylistic: a change to the website or WhatsApp flow cannot reach a
              live phone call, and an audio bug cannot be caused by a prompt edit.
            </p>
            <Table
              head={["Concern", "Owned by", "Not owned by"]}
              proseKey
              rows={[
                ["Audio in and out, codecs, sample rates", "pipecat-v2v", "pw-llm-layer"],
                ["Turn taking, barge in, interruptions", "pipecat-v2v", "pw-llm-layer"],
                ["What to say, in which language", "pw-llm-layer", "pipecat-v2v"],
                ["Which tools exist and what they do", "tool-ecosystem", "pipecat-v2v"],
                ["Dialling, transferring, hanging up", "pipecat-v2v", "pw-llm-layer"],
                ["Conversation memory", "pw-llm-layer", "pipecat-v2v"],
              ]}
            />
            <Callout tone="brand" title="The idea worth internalising">
              The reply carries a <Code>voice_action</Code>, a structured instruction the
              pipeline performs <em>after</em> it finishes speaking. That is how a chatbot
              with no access to telephony transfers a live call.
            </Callout>

            <Sub id="what-surfaces">The two surfaces</Sub>
            <p>
              A phone call asks the brain as <Code>callvoice</Code>. The browser widget asks
              as <Code>webvoice</Code>. That one value selects the prompt, the tool set, the
              history table and the history depth.
            </p>
            <Table
              head={["", "Phone", "Browser"]}
              proseKey
              rows={[
                ["Brain", "callvoice", "webvoice"],
                ["Session id", "voice-<digits>, carries across calls", "fresh per socket"],
                ["Screen", "none, result HTML is discarded", "streamed to the tab"],
                ["Time limit", "MAX_CALL_DURATION_SECS", "none"],
                ["Idle nudges and watchdog", "on", "off"],
                ["Audio out", "8k on the wire", "24k to the browser"],
                ["Can be transferred", "yes, Acefone", "no"],
              ]}
            />
            <p>
              The browser has neither a per minute cost nor a line that can drop, and a
              visitor reading fifteen hotel cards is legitimately silent for minutes. Cutting
              them off on a timer would be worse with nothing to justify it.
            </p>

            <Sub id="what-words">Vocabulary</Sub>
            <Table
              head={["Term", "Means"]}
              rows={[
                ["channel", "One telephony provider or the website: acefone, website"],
                ["brain / user_type", "Which prompt and tool set the chatbot runs: callvoice or webvoice"],
                ["turn", "One customer utterance and the reply to it"],
                ["turn_kind", "Why this request was made: user, hold, greeting, recovery, closing"],
                ["voice_action", "A structured instruction returned with a reply, performed by the pipeline"],
                ["capabilities", "What this specific call can actually do, sent on every turn"],
                ["hold line", "A short filler spoken while the real answer is still being composed"],
                ["surface", "Where non spoken results go: the browser socket, or nowhere"],
              ]}
            />
          </Section>


          <Section id="studio-agents" title="Agents">
            <p className="lede">
              An agent is one complete voice persona: who speaks, what it may discuss, which
              tools it can call, how it sounds and where it runs. Agents are stored in the
              brain's database, and an agent's identifier is the <Code>user_type</Code> the
              brain runs it as.
            </p>

            <Sub id="studio-agent-parts">What an agent holds</Sub>
            <Table
              head={["Tab", "Holds"]}
              proseKey
              rows={[
                ["Agent", "Name, description, system prompt and the opening greeting in English and Hindi. Two greetings per language can be suggested by the model from the prompt and variables."],
                ["Variables", "The persona (agent name, its Hindi spelling, company), the global variables every agent shares, and this agent's own. The Hindi name is transliterated automatically."],
                ["Tools", "Factory tools from tool-ecosystem, your HTTP API tools and MCP servers, each switched on per agent."],
                ["Guardrails", "Entries attached from the guardrail library, the refusal line in both languages (suggestions available), personal data masking and reply length."],
                ["Voice and model", "Speech engine and voice, prefilled from Settings, and the language model with its temperature and token limit."],
                ["Channels and calls", "Where the agent may run, whether it is a phone agent, its maximum call length, and this agent's own settings: retention discount, WhatsApp message and transfer number. Each one left empty uses the value from Settings."],
                ["QMS", "The QMS API that sends this agent its customers, the payload the agent receives, and when it calls: delay, calling hours, duplicate window."],
                ["Preview", "The system prompt exactly as the model receives it, with every placeholder filled."],
              ]}
            />
            <p>
              The Phone test and Browser test pages pick an agent from those switched on for
              their channel and show what it will do before anything connects: the voice, the
              model, the tools and the opening line, filled with the customer's name.
            </p>

            <Sub id="studio-placeholders">Placeholders and variables</Sub>
            <p>
              Any text an agent speaks or reads can use placeholders in braces. Typing{" "}
              <Code>{"{"}</Code> in a field opens a list of the variables that agent can use;
              known placeholders are highlighted, and an unknown one is marked so it is fixed
              before it reaches a call.
            </p>
            <Table
              head={["Placeholder", "Filled with"]}
              rows={[
                ["{agent_name}, {agent_name_hindi}, {company}", "The agent's persona, set on its Variables tab"],
                ["{customer_name}", "The customer on this call, from the record that requested it"],
                ["{helpline}, {website}, any custom key", "The agent's own value, else the global variable of that name"],
                ["{call_details}", "Every field the QMS intake sent for this call, as a list"],
                ["Any payload field, e.g. {hotel_name}", "That field's value, for agents fed by an API that sends it"],
                ["{cart_summary}", "One line describing the cart, for agents fed by the Abandoned cart API"],
              ]}
            />
            <p>
              Global variables are written once (Variables tab → Edit globals) and every agent can
              use them; a new agent starts with them and none of its own. An agent's own variable
              of the same name overrides the global one for that agent only.
            </p>
            <p>
              The agent always hears its call data. When the context template does not use{" "}
              <Code>{"{call_details}"}</Code>, the fields are appended to it as a{" "}
              <Code>{"<call_details>"}</Code> block, so a new intake works without editing the
              prompt.
            </p>

            <Sub id="studio-guardrails">The guardrail library</Sub>
            <p>
              Blocked topics, banned phrases and escalation rules are written once on the
              Guardrails page, each with a name and a description, and attached to any number
              of agents. The brain renders each attached entry into the prompt as its name and
              description; banned phrases are also enforced by the pipeline on the way to the
              speaker, so a phrase the model produces anyway is never heard.
            </p>

            <Sub id="studio-save">Saving and propagation</Sub>
            <Steps
              ordered
              items={[
                { t: "Each field saves on its own", d: "A changed field shows ✓ and ✕ beside it. ✓ sends only that field; ✕ puts it back." },
                { t: "The brain merges the change", d: "Objects are merged and lists replaced, so saving one greeting never touches the other." },
                { t: "The pipeline picks it up within ten seconds", d: "Agents are cached for ten seconds, so the next call after that runs the new version. No restart is needed." },
              ]}
            />
          </Section>

          <Section id="studio-tools" title="Tools and MCP servers">
            <p className="lede">
              A tool is something an agent can do mid-call. The Tools page lists every tool by
              name and purpose; opening one shows everything about it, and each agent switches
              on exactly the tools it needs on its own Tools tab.
            </p>

            <Sub id="studio-tool-kinds">Three kinds of tool</Sub>
            <Table
              head={["Kind", "Where it comes from", "Switch on the Tools page"]}
              proseKey
              rows={[
                ["Factory", "tool-ecosystem: transfer, end call, cart, booking link, searches and status lookups", "Turns the tool off for every agent at once, without editing each agent"],
                ["HTTP API", "A request you define: method, URL, headers, parameters the model fills, what it reads back", "Disables the tool everywhere it is attached"],
                ["MCP server", "Any Model Context Protocol server, reached by its URL; its tools are discovered automatically", "Disables every tool from that server"],
              ]}
            />
            <p>
              Add tool on the Tools page is the only place to create one, and it asks which
              kind first. HTTP API and MCP tools can be tested from their detail view exactly as
              an agent would call them mid-call.
            </p>

            <Sub id="studio-mcp">Connecting an MCP server</Sub>
            <Steps
              ordered
              items={[
                { t: "Point at the URL", d: "Give the server a name, a one-line purpose and its endpoint. Headers carry an API key or bearer token; reference a secret as {{secret:NAME}} and it is resolved on the server, never shown in the console." },
                { t: "Connect", d: "The brain speaks Streamable HTTP, the current MCP transport, and falls back to the older HTTP + SSE transport on Auto. It initialises a session and lists the server's tools." },
                { t: "Choose what agents may use", d: "Every discovered tool is listed with its description and parameters. Switch off any an agent should never call. Sync later picks up tools the server added or removed." },
                { t: "Give it to an agent", d: "On the agent's Tools tab the server is one switch. The model sees each exposed tool as <server>__<tool> with the server's own input schema, so two servers can both offer a search." },
              ]}
            />
            <Callout tone="brand" title="How a call reaches the server">
              Sessions are kept open for five minutes and reused, so a tool call mid-conversation
              costs one round trip. A server that is down, slow or returns an error never breaks
              the call: the agent is told the lookup did not work and carries on.
            </Callout>

            <Sub id="studio-language-tool">Language switching is a tool</Sub>
            <p>
              Allowing an agent to switch language mid-call and giving it the{" "}
              <Code>voice_switch_language</Code> tool are the same setting. Turning the switch on
              gives the agent the tool; switching the tool off turns the switch off. The brain
              enforces this on every save, so the two can never disagree.
            </p>
          </Section>

          <Section id="studio-qms" title="QMS and History">
            <p className="lede">
              QMS is where customer calls enter the system. Each intake API queues calls for
              one agent, and History records every request and what became of it.
            </p>

            <Sub id="studio-intakes">QMS APIs</Sub>
            <p>
              A QMS API is one upstream system that sends customers to call. The work is split
              in two, so the team that owns the data and the team that owns the agent each set
              their own half.
            </p>
            <Table
              head={["Set on", "What", "Holds"]}
              proseKey
              rows={[
                ["QMS page", "The contract", "Name, endpoint, token and the payload fields. This is what you hand to the sending team."],
                ["Agent → QMS tab", "Who calls and when", "Which API feeds the agent, the delay after a record arrives, calling hours (IST) and the duplicate window."],
                ["Agent → Variables", "What else the agent knows", "Global variables shared by every agent (company, helpline, website) and the agent's own."],
              ]}
            />
            <p>
              The order for a new use case, for example hotel recovery: create the API on QMS,
              share its endpoint, token and curl with the sending team, create the agent, then
              connect the API on the agent's QMS tab and set when it calls. No code change and no
              restart.
            </p>
            <Table
              head={["API", "Endpoint", "Payload"]}
              proseKey
              rows={[
                ["Abandoned cart (built in)", "POST {base}/api/ingestion/calls", "The cart: trip, dates, passengers, amount, status. Fixed, because the cart tools read them. Connected to callvoice, 120 s delay, 1 h duplicate window."],
                ["Any API you add", "POST {base}/api/qms/{id}/calls", "Whatever you define: text, number, integer, date, date and time, choice, phone, email, link or yes/no."],
              ]}
            />
            <p>
              <Code>{"{base}"}</Code> is the public API base URL from Settings → QMS
              (<Code>QMS_PUBLIC_BASE_URL</Code>); when it is empty it is derived from the public
              WebSocket address. Every endpoint, curl and token dialog uses it, so what you copy is
              what the sending team calls.
            </p>
            <p>
              The QMS page lists every API with its state (Active, Needs setup, Off). The selected
              API shows its endpoint, token, connected agent and timing, then four tabs: Received
              data (every request, valid or not, with each field it carried and why it was
              rejected), Payload, Endpoint and curl, and Response. The token is shown once when it
              is created or replaced; only its last four characters are kept.
            </p>
            <p>
              An endpoint takes one record as a JSON object, or up to{" "}
              <Code>INGESTION_MAX_BATCH</Code> as an array, with the API's token in{" "}
              <Code>Authorization: Bearer</Code> or <Code>X-API-Key</Code>. It answers 202 when at
              least one record was queued, 422 when none was, 401 for a bad token, 404 for an
              unknown API, and 503 when the API, QMS or the dialer is off.
            </p>
            <p>
              An API can be created and handed out before its agent exists. A valid record that
              arrives while no live agent is connected (none connected, or the agent is not Active
              on its channel yet) is accepted with 202 and held as <strong>trigger pending</strong>;
              invalid ones are still rejected. When the API is connected on an agent's QMS tab and
              records are held, the dashboard asks what to do with them: call them, now if the
              agent is live or the moment it is made live, or keep them held. Records that arrive
              after connecting, while the agent is not live yet, are called once it is. Held
              records can also be called from the QMS page.
            </p>
            <p>
              Releasing re-checks every held record (a travel date may have passed), skips
              duplicates, and hands the rest to the scheduler with the API's delay and calling
              hours, 20 seconds apart, so a backlog rings one call at a time.
            </p>
            <Table
              head={["Timing", "Behaviour"]}
              proseKey
              rows={[
                ["Delay", "The call rings this long after the record arrives. A record's scheduled_at always wins."],
                ["Calling hours", "Optional IST window, e.g. 09:00 to 21:00. A record outside it waits for the window to open; a window may cross midnight."],
                ["Duplicate window", "A record for a number or reference already queued or called inside it is logged as a duplicate and not called."],
              ]}
            />

            <Sub id="studio-contract">The record contract</Sub>
            <p>
              A record is called only when every required field is present and makes sense.
              A record with anything missing or invalid is rejected as a whole and never
              dialled.
            </p>
            <Table
              head={["Fields", "Required"]}
              proseKey
              rows={[
                ["Every API", "customer_name, phone_number. Optional: reference_id (generated as e.g. HR-261013-7F3A2C when left out, and returned in the response), scheduled_at, language."],
                ["Abandoned cart", "booking_type, origin, destination, travel_date, trip_type, status, passengers, total_amount_inr, and return_date for a round trip"],
                ["Your API", "The fields marked required, plus any field whose condition (required when another field equals a value) is met"],
              ]}
            />
            <p>
              The Phone test and Browser test ask for exactly the fields of the API connected to
              the chosen agent, checked by the same rules as the live endpoint. The reference id is
              generated for tests too. The Browser test
              holds its record under a <Code>TEST-</Code> reference so the agent hears the same
              call details. Tests run the payment pending flow, so the cart status is fixed to{" "}
              <Code>payment_pending</Code>; other statuses arrive through the live API.
            </p>
            <p>
              Cart tools such as <Code>voice_cart_details</Code> read the cart, so give them only
              to agents fed by the Abandoned cart API. Agents fed by another API already
              hear their data in <Code>{"<call_details>"}</Code>.
            </p>

            <Sub id="studio-lifecycle">Record lifecycle</Sub>
            <Table
              head={["Status", "Means"]}
              rows={[
                ["rejected", "Missing or invalid data. Never dialled."],
                ["trigger pending", "Valid, held until a live agent is connected to its API and the records are released."],
                ["duplicate", "The same reference or number is already queued or was called inside INGESTION_DEDUPE_WINDOW_SECS."],
                ["scheduled", "Valid and queued. Dials after INGESTION_CALL_DELAY_SECS, or at the record's scheduled_at."],
                ["dialing", "The dial request is with the provider."],
                ["triggered", "The provider accepted the call."],
                ["failed", "The provider refused the call, or the agent is not usable on the channel."],
                ["cancelled", "Stopped from History before it rang."],
              ]}
            />
            <Callout tone="warn" title="What a restart does to the queue">
              Scheduled records are picked back up when the service starts. A record left in{" "}
              <Code>dialing</Code> may or may not have rung, so it is closed as failed rather
              than dialled a second time.
            </Callout>

            <Sub id="studio-history">History, retry and cancel</Sub>
            <Steps
              ordered={false}
              items={[
                { t: "Filters", d: "Status, agent, source and a search over reference, number, name and reason. Filters are kept in the address, so a filtered view can be shared as a link." },
                { t: "Detail", d: "Each record opens to show its source, agent, timings, the dial attempt and the payload exactly as received." },
                { t: "Retry", d: "A failed call can be retried with the Place calls permission. The payload is validated again and queued as a new record; the failed record stays as it was and names the retry." },
                { t: "Cancel", d: "A scheduled call can be stopped before it rings with the Cancel scheduled calls permission." },
              ]}
            />

            <Sub id="studio-call-detail">Inside a call</Sub>
            <p>
              Opening a call in History shows everything about it in one place.
            </p>
            <Table
              head={["Part", "Shows"]}
              proseKey
              rows={[
                ["At a glance", "Duration, turns, average response time and the outcome"],
                ["Summary", "Written by the model the first time the call is opened, in English, with the outcome, the next step and the customer's sentiment. Rewrite asks for a fresh one."],
                ["Conversation", "Every line, customer and agent, end to end, with the time it was said"],
                ["Latency and providers", "The speech, model and voice providers the call ran on, their average time, each turn's split into STT, LLM, TTS and lead silence, tokens and the estimated cost"],
                ["Timeline", "Received, dialled, answered, transferred and ended, why it ended, and the recording when the provider supplies one"],
                ["Request", "The record exactly as it arrived, and what was wrong with it if it was rejected"],
              ]}
            />
            <p>
              Latency and providers are filed against the call when it ends, so calls placed
              before this was added have a conversation but no latency.
            </p>
          </Section>

          <Section id="studio-access" title="Access and team">
            <p className="lede">
              Every screen and every action is behind a permission. A role is a named set of
              permissions, and each team member holds exactly one role.
            </p>

            <Sub id="studio-roles">Roles and permissions</Sub>
            <Table
              head={["Role", "Can"]}
              proseKey
              rows={[
                ["Super admin", "Everything, including managing other admins and roles"],
                ["Admin", "Everything except changing a super admin"],
                ["Custom roles", "Exactly the permissions chosen on Roles and access"],
              ]}
            />
            <Table
              head={["Area", "Permissions"]}
              rows={[
                ["Calls", "View live calls, Place calls, View QMS and history, Cancel scheduled calls"],
                ["Agents and tools", "View, edit and delete agents; view and edit tools"],
                ["Settings", "View settings, Edit settings, Reveal secrets"],
                ["Data", "View database, Delete database rows, View logs"],
                ["Team", "View team, Manage team, Manage roles"],
              ]}
            />
            <p>
              A role cannot grant a permission its creator does not hold, so access can only be
              handed down, never escalated.
            </p>

                        <p>
              Everything stays in the sidebar for everyone. A page the role cannot open is marked
              with a lock and, when opened, says which permission it needs and offers{" "}
              <strong>Request access</strong> with an optional note. Admins who can manage the
              team are emailed and see the request on the Team page; they grant it by adding the
              permission to the role or moving the person to a role that has it, then mark it
              granted or dismissed, which emails the person who asked. Locked cards on the
              Overview offer the same request.
            </p>

            <Sub id="studio-invites">Invitations and passwords</Sub>
            <p>
              Inviting a member emails a temporary password and the console link. The member
              must set their own password at first sign in. A reset from Team works the same
              way. When email cannot be sent, the temporary password is shown once to the
              person who issued it.
            </p>
            <p>
              Forgot password on the sign-in screen emails a one-time link instead, valid for
              15 minutes and stored only as a keyed hash. The current password keeps working
              until the link is used, so nobody can lock a colleague out by asking for a reset
              in their name. Asking again replaces the older link, and the same address can ask
              at most once a minute.
            </p>

            <Sub id="studio-otp">Two-step sign-in</Sub>
            <Steps
              ordered
              items={[
                { t: "Password", d: "Checked first. A wrong one gets no hint about which part was wrong." },
                { t: "Emailed code", d: "A six-digit code goes to the account's email. It expires in five minutes, works once, and is stored only as a keyed hash." },
                { t: "Limits", d: "Five wrong codes end the attempt. A new code can be requested after 30 seconds, up to three times." },
                { t: "Session", d: "Only a correct code issues a session, and it lasts 7 days (DASHBOARD_SESSION_HOURS, 168), so the code is asked once a week per browser. If the email cannot be sent, no session is issued and the screen says why." },
              ]}
            />

            <Sub id="studio-encryption">Encrypted console traffic</Sub>
            <p>
              Every request and response body between the console and{" "}
              <Code>/api/admin</Code> is encrypted in the browser, on top of TLS. When the page
              opens it agrees a key with the server (ECDH P-256, then HKDF-SHA256) that never
              leaves memory, and seals each body with AES-256-GCM. A body is bound to its method
              and path and carries a timestamp, so a captured request cannot be replayed or
              redirected to another endpoint. The browser's network panel shows only ciphertext,
              and the API refuses plain requests.
            </p>
            <Callout tone="warn" title="What this does not cover">
              The browser needs a secure context for this, so open the console over HTTPS or on
              localhost. External integrations such as the QMS intake API keep their token
              authentication over TLS, since upstream systems post to them directly.
            </Callout>

            <Sub id="studio-secrets">Secrets on screen</Sub>
            <p>
              API keys and tokens are never sent to the browser with the other settings. A
              stored secret shows as a filled, masked field. Clicking into it, or pressing the
              eye, loads the real value for editing; that needs the Reveal secrets permission
              and is logged. Emptying the field and saving clears the secret.
            </p>
          </Section>


          <Section id="hld-context" title="System context">
            <p className="lede">
              Three services and four vendors. The arrows below are the only ways any of them
              talk to each other.
            </p>
            <SystemDiagram />

            <Sub id="hld-services">The three services</Sub>
            <Table
              head={["Service", "Job", "Runs"]}
              rows={[
                [
                  "pipecat-v2v",
                  "Media, turn taking, telephony, actions, the console",
                  "FastAPI on :8410, one pipeline task per live call",
                ],
                [
                  "pw-llm-layer",
                  "Prompts, model calls, tool selection, conversation memory",
                  "FastAPI on :8000, stateless per request",
                ],
                [
                  "tool-ecosystem",
                  "The tools themselves: cart, discount, booking link, transfer, inventory",
                  "Imported by pw-llm-layer as a library",
                ],
              ]}
            />

            <Sub id="hld-vendors">External dependencies</Sub>
            <Table
              head={["Vendor", "Used for", "Reached by"]}
              proseKey
              rows={[
                ["Deepgram", "Speech to text, v1 /listen or v2 /listen (Flux)", "pipecat-v2v"],
                ["Murf", "Speech synthesis, streaming websocket", "pipecat-v2v"],
                ["Acefone (Smartflo)", "PSTN media stream, dialling, live call transfer", "pipecat-v2v"],
                ["Groq", "The language model behind both voice brains", "pw-llm-layer"],
                ["QMS intake APIs", "Customer records that request a call", "upstream posts into pipecat-v2v"],
              ]}
            />
            <p>
              Gemini, Sarvam and OpenAI are wired as alternative speech engines behind the
              same factory. Swapping one for another is a configuration change, not a code
              change. Acefone is the only carrier wired up; a second one would be a new
              channel module and serializer behind the same transport.
            </p>

            <Sub id="hld-boundaries">Boundaries that matter</Sub>
            <Steps
              ordered={false}
              items={[
                {
                  t: "The brain never touches the line",
                  d: "It cannot dial, hang up, transfer or change the audio. It returns an instruction and the pipeline decides whether that instruction is currently possible.",
                },
                {
                  t: "The pipeline never composes a sentence",
                  d: "The only text it produces on its own is the greeting template and the canned fallback lines, and both exist purely to cover latency.",
                },
                {
                  t: "Neither service can read the other's database",
                  d: "That is why the console proxies the Brain settings over HTTP rather than running a second query.",
                },
              ]}
            />
          </Section>

          <Section id="hld-runtime" title="Runtime topology">
            <p className="lede">
              One FastAPI process serves the media sockets, the provider webhooks, the console
              API and the console itself.
            </p>
            <DeploymentDiagram />

            <Sub id="hld-routes">One process, many routes</Sub>
            <p>
              Every channel path is registered whether or not the channel is enabled, and the{" "}
              <Code>ENABLE_*</Code> flag is read when a socket connects rather than when the
              module is imported. Turning a channel on, pointing a new provider at it, or
              moving it to a different path takes effect on the next call instead of the next
              restart.
            </p>
            <Table
              head={["Path", "Serves"]}
              rows={[
                ["/ws/acefone", "The telephony media socket"],
                ["/ws/website", "The browser voice widget"],
                ["/api/ingestion/calls", "QMS: the Abandoned cart API, token authenticated"],
                ["/webhooks/acefone", "Call lifecycle events"],
                ["/api/admin/session-key", "Agrees the console's payload encryption key"],
                ["/api/admin/*", "The console API: session token, encrypted bodies"],
                ["/dashboard/", "The built console, served as static files"],
              ]}
            />
            <Callout tone="warn" title="A disabled channel does not 404">
              It closes the socket with code <Code>1013</Code> and a reason. From the outside,
              a provider pointed at a path that does not exist and a channel that is simply
              switched off would otherwise look identical, and they need different fixes.
            </Callout>

            <Sub id="hld-stores">Two databases</Sub>
            <Table
              head={["Database", "Tables", "Owned by"]}
              rows={[
                [
                  "pw_voicebot (underscore)",
                  "app_settings, setting_changes, dashboard_users, call_records, call_sessions, call_events, call_transcripts",
                  "this service",
                ],
                ["pw-llm-layer (hyphen)", "voice_settings, voice_history, chat_history", "the brain"],
              ]}
            />
            <Callout tone="halt" title="One character apart">
              Reading the two <Code>.env</Code> files side by side, the difference between{" "}
              <Code>pw_voicebot</Code> and <Code>pw-llm-layer</Code> is invisible. Pointing one
              service at the other's database is the most expensive typo available here.
            </Callout>

            <Sub id="hld-restart">What needs a restart</Sub>
            <p>
              Almost nothing. <Code>HOST</Code>, <Code>PORT</Code> and <Code>LOG_LEVEL</Code>{" "}
              are consumed once as the process starts. Everything else applies to the next
              connection, because the routing table is rebuilt from config rather than
              registered at import, and every provider client is constructed during call
              setup.
            </p>
            <p>
              With <Code>SETTINGS_REFRESH_SECS</Code> above zero, every worker re-reads{" "}
              <Code>app_settings</Code> on that interval and the chatbot re-reads{" "}
              <Code>voice_settings</Code> every <Code>VOICE_SETTINGS_TTL_SECS</Code>. A change
              made on one worker, or written straight into Postgres by an ops script, reaches
              all of them without a restart, and a call already in progress picks it up on its
              next turn.
            </p>
          </Section>


          <Section id="lld-pipeline" title="The processor chain">
            <p className="lede">
              Every channel builds this identical shape. Only the transport, the serializer and
              the sample rates differ.
            </p>
            <PipelineDiagram />

            <Sub id="lld-order">Order, and why it is that order</Sub>
            <Steps
              ordered={false}
              items={[
                {
                  t: "The gate sits ahead of the transcriber, not behind it",
                  d: "Audio that arrives before Deepgram's socket is confirmed is dropped by the service itself, so it has to be held before it gets there.",
                },
                {
                  t: "The engine sits where a local model used to sit",
                  d: "VoiceEngineProcessor speaks the same frame contract an LLM service would, which is what let the brain move into another process without touching anything downstream of it.",
                },
                {
                  t: "Every filter sits after sentence aggregation",
                  d: "LLMTextProcessor turns a stream of token frames into whole sentences. A guardrail cannot match a rule against half a word.",
                },
                {
                  t: "Gain and ambience sit after TTS and before the transport",
                  d: "They operate on synthesised audio, and the transport is where the serializer converts it to the wire format.",
                },
              ]}
            />

            <Sub id="lld-conditional">Conditional processors</Sub>
            <Table
              head={["Processor", "Present when"]}
              rows={[
                ["AudioRechunkerProcessor", "The channel runs Flux and FLUX_INPUT_CHUNK_MS is set"],
                ["STTConnectGateProcessor", "The STT service exposes a readiness event (Deepgram v1 does, Flux does not)"],
                ["TranscriptRelayProcessor", "Website only, one instance on each side of the engine"],
                ["OutputGainProcessor", "BOT_OUTPUT_GAIN_DB is non zero"],
                ["AmbienceMixerProcessor", "ENABLE_BACKGROUND_AMBIENCE is on"],
              ]}
            />
            <p>
              A phone call ends when the model decides it should. Every phone agent is given{" "}
              <Code>voice_end_call</Code> whether or not it was ticked on the Tools tab; the
              model calls it once the conversation is over, speaks the closing it is handed,
              and the line drops after that audio finishes. Nothing guesses from the words of
              a reply. The only other endings are the call-length limit and a customer who
              stays silent through the re-prompts. After a closing, the end-of-call watchdog
              waits <Code>CALL_END_WATCHDOG_SECS</Code> of customer silence, restarting the
              moment the customer starts speaking again.
            </p>

            <Sub id="lld-frames">The frame contract</Sub>
            <p>
              Suppression in this pipeline is expressed as <Code>skip_tts</Code> on a frame,
              never as dropping the frame. A muted sentence still reaches the assistant
              aggregator and the transcript recorder, so the conversation the brain remembers
              stays accurate even when the customer heard nothing. Dropping it instead would
              leave the brain believing it said something it did not, and the next turn would
              be built on that belief.
            </p>
          </Section>

          <Section id="lld-turn" title="One turn, in detail">
            <p className="lede">
              One customer sentence, from air to air. The two branches run at the same time,
              which is the whole trick to not sounding slow.
            </p>
            <TurnDiagram />

            <Sub id="lld-close">Closing the turn</Sub>
            <p>
              A turn closes when the configured turn strategies agree the customer has
              finished. On Deepgram v1 that decision is made in this process by Silero VAD and
              a smart turn model. On Flux it is made inside the transcription model and
              arrives as an event. Either way the same thing happens next: the user aggregator
              emits the joined transcript and the engine starts a turn.
            </p>
            <p>
              The engine joins fragments back to the last thing the bot said. One spoken
              request routinely splits across several transcripts, and sending only the newest
              fragment made the brain re-ask for a city it had already been told.
            </p>

            <Sub id="lld-race">The parallel race</Sub>
            <FlowStrip
              note="If the answer wins the race, the hold line is dropped unheard and costs only its own tokens."
              stages={[
                { icon: Mic, title: "Speech ends", who: "turn strategies", detail: "the turn closes" },
                { icon: Plug, title: "Fragments joined", who: "engine", detail: "back to the last bot line" },
                { icon: Globe, title: "Ask the brain", who: "HTTP", tone: "bot", detail: "and compose a hold line, in parallel" },
                { icon: Activity, title: "Race", who: "engine", tone: "act", detail: "answer inside 1.4s means no filler" },
                { icon: Waves, title: "Speak", who: "TTS", tone: "bot", detail: "filters run before a word is heard" },
                { icon: Check, title: "Render", who: "page", tone: "done", detail: "only if there is markup to show" },
              ]}
            />
            <Table
              head={["Timer", "Phone", "Browser"]}
              proseKey
              rows={[
                ["First hold line", "PW_CHAT_PHONE_HOLD_DELAY_SECS, 1.4s", "PW_CHAT_HOLD_DELAY_SECS, 1.8s"],
                ["Second hold line", "PW_CHAT_PHONE_SECOND_HOLD_SECS, 4.5s", "PW_CHAT_SECOND_HOLD_SECS, 8.0s"],
                ["Read timeout", "PW_CHAT_PHONE_READ_TIMEOUT_SECS, 8.0s", "PW_CHAT_READ_TIMEOUT_SECS, 30.0s"],
                ["Connect timeout", "PW_CHAT_CONNECT_TIMEOUT_SECS, 5.0s", "same"],
                ["Attempts", "PW_CHAT_MAX_ATTEMPTS, 2", "same"],
              ]}
            />
            <p>
              The phone budgets are tighter for a reason that is not arbitrary. A visitor
              watches a pending state and a results area. A caller hears nothing at all and
              starts saying "hello?" at about 1.2 seconds. Hold lines are load bearing on a
              phone and cosmetic in a browser.
            </p>

            <Sub id="lld-stale">Barge in and stale replies</Sub>
            <Steps
              ordered={false}
              items={[
                {
                  t: "The HTTP call survives barge in",
                  d: "Child tasks are cancelled when the customer interrupts; the chat request is not. A reply that arrives late is still recorded with the brain, it is simply never spoken.",
                },
                {
                  t: "A stale answer is never spoken",
                  d: "A watermark drops any reply older than one already delivered, even when it arrives afterwards. Without it, a slow retry lands behind the real answer and the customer hears the same thing twice.",
                },
                {
                  t: "Repeats are caught even across several lines",
                  d: "The duplicate filter keeps a window of six recent lines, because a closing sequence is three or four sentences long and single line memory cannot see a re-spoken closing at all.",
                },
                {
                  t: "A sign off is capped at one per call",
                  d: 'Two sign off variants can share almost no vocabulary ("आपकी यात्रा शुभ हो" against "आपका दिन शुभ हो"), so no similarity rule was ever going to catch them. What makes them duplicates is their role in the call, not their wording.',
                },
              ]}
            />
          </Section>

          <Section id="lld-actions" title="The reverse path">
            <p className="lede">
              This is the mechanism the whole architecture is built around, and the only way
              the brain can affect the line.
            </p>
            <ActionDiagram />

            <Sub id="lld-action-shape">What an action is</Sub>
            <p>
              A reply may carry one <Code>voice_action</Code>: an id, a type, a parameter
              object, a turn id, and <Code>execute_after_speech</Code>. Five types are known.
              Anything else is logged and ignored rather than guessed at.
            </p>
            <Table
              head={["type", "What the pipeline does", "Terminal"]}
              rows={[
                [
                  "transfer_to_agent",
                  "Drain the audio, call Acefone, disable auto hang up, stop the bot leg. Deliberately no EndTaskFrame, because the customer is now with a person",
                  "yes",
                ],
                ["end_call", "Record the disposition, drain, then EndTaskFrame upstream", "yes"],
                [
                  "switch_language",
                  "Flip LanguageState and the TTS locale, before the reply is spoken",
                  "no",
                ],
                ["log_disposition", "Write to call_records and arm the wrap up", "no"],
                ["send_booking_link", "Acknowledge, the tool has already sent it", "no"],
              ]}
            />

            <Sub id="lld-gate">The drain gate</Sub>
            <p>
              <Code>ActionGateProcessor</Code> watches the audio actually play out.
              A transfer fired the moment the reply text arrived would cut the customer off
              mid sentence, so the executor takes a snapshot, waits for{" "}
              <Code>BotStoppedSpeaking</Code>, and only then calls the provider. On telephony
              the drain is real time: the audio has to travel the wire and be played.
            </p>

            <Sub id="lld-checks">Seven checks, in order</Sub>
            <p className="docs-chain mono">
              actions disabled &rarr; already executed &rarr; terminal latched &rarr; call
              ended &rarr; stale turn &rarr; not in capabilities &rarr; unknown type
            </p>
            <p>
              Every failure is acknowledged back to the brain on the next turn as{" "}
              <Code>last_action_ack</Code>, so it never waits forever on something that was
              dropped, and a once per call latch inside the tool is released so the customer
              can ask again.
            </p>
            <Callout tone="brand" title="capabilities is the gate">
              The session advertises only what this specific call can actually do. No
              TransferHandle means <Code>transfer_to_agent</Code> is never offered, so the
              brain cannot promise something that would fail. A transfer handle is built only
              when the channel is Acefone, <Code>ENABLE_CALL_TRANSFER</Code> is on, and both{" "}
              <Code>CALL_TRANSFER_NUMBER</Code> and <Code>ACEFONE_AUTH_TOKEN</Code> are set.
            </Callout>
          </Section>


          <Section id="stt" title="Speech to text">
            <p className="lede">
              Selecting a transcription engine is a configuration change: set{" "}
              <Code>STT_PROVIDER</Code> and the matching key, and nothing else moves. What
              does move with it is who decides a turn is over.
            </p>
            <SttDiagram />

            <Sub id="stt-engines">Engines and models</Sub>
            <Table
              head={["STT_PROVIDER", "API", "Models", "Turn taking"]}
              rows={[
                ["deepgram", "v1 /listen", "nova-3 (multi, en), nova-2 (single language)", "local, VAD plus smart turn"],
                ["deepgram_flux", "v2 /listen", "flux-general-multi, flux-general-en", "inside the model"],
              ]}
            />
            <p>
              The v1 service runs with <Code>smart_format</Code>, <Code>punctuate</Code> and{" "}
              <Code>interim_results</Code> on, so partial transcripts are available while the
              customer is still speaking. Flux takes language hints rather than a language:
              Hindi implies Hinglish here, because callers say "booking", "flight" and
              "payment" mid sentence whichever way the channel is configured.
            </p>
            <Callout tone="warn" title="The two APIs do not share parameters">
              <Code>/v2/listen</Code> rejects v1 parameters outright. That is why{" "}
              <Code>resolve_stt_params</Code> coerces a channel to{" "}
              <Code>STT_FLUX_MODEL</Code> unless its own override is already a{" "}
              <Code>flux-*</Code> name. Without it, the website's standing{" "}
              <Code>STT_MODEL_WEBSITE</Code> would be sent to the v2 endpoint the moment the
              channel was flipped, and flipping it back would need two edits instead of one.
            </Callout>

            <Sub id="stt-turns">Who decides the turn is over</Sub>
            <Table
              head={["", "Deepgram v1", "Deepgram Flux"]}
              proseKey
              rows={[
                ["Start of turn", "MinWordsUserTurnStartStrategy, MIN_WORDS_TO_INTERRUPT", "ExternalUserTurnStartStrategy, from the first word"],
                ["End of turn", "LocalSmartTurnAnalyzerV3, an ONNX model in this process", "eot_threshold inside the ASR model"],
                ["Voice activity", "SileroVADAnalyzer, built per call", "none is built at all"],
                ["Aggregation window", "n/a", "FLUX_TURN_AGGREGATION_MS, 50ms"],
                ["Interruption", "after MIN_WORDS_TO_INTERRUPT words", "FLUX_SHOULD_INTERRUPT, immediate"],
              ]}
            />
            <p>
              A channel on Flux builds no local VAD, and the external strategies are passed in
              by hand rather than left to the default. Two reasons, both measured. Leaving
              them unset makes pipecat construct a smart turn analyzer that loads an ONNX
              session in its constructor and is then immediately discarded on every call. And{" "}
              <Code>ExternalUserTurnStrategies()</Code> hardcodes a half second aggregation
              window, which showed up as 504ms of dead latency ahead of every brain request,
              because the stop frame overtakes the queued transcript and the strategy declines
              to close the turn until the window expires.
            </p>
            <Callout tone="halt" title="Eager end of turn is deliberately off">
              <Code>eager_eot_threshold</Code> is left unset. Speculative replies would raise
              brain calls by roughly 50 to 70 percent for turns that get discarded, and the
              brain is the expensive leg.
            </Callout>

            <Sub id="stt-tuning">Per channel tuning</Sub>
            <p>
              Provider, language and model all resolve in two layers: the global value, then
              the channel's own override. Telephony and the website are genuinely different
              signals, 8kHz band limited line audio against 16kHz browser audio that has
              already been through echo cancellation, noise suppression and automatic gain
              control. A threshold tuned for one is wrong for the other.
            </p>
            <Table
              head={["Setting", "Global default", "Per channel key"]}
              rows={[
                ["STT_PROVIDER", "deepgram", "STT_PROVIDER_ACEFONE, _WEBSITE"],
                ["STT_MODEL", "nova-3", "STT_MODEL_<CHANNEL>"],
                ["STT_LANGUAGE", "multi", "STT_LANGUAGE_<CHANNEL>"],
                ["VAD_CONFIDENCE", "0.7", "VAD_CONFIDENCE_<CHANNEL>"],
                ["VAD_START_SECS", "0.2", "VAD_START_SECS_<CHANNEL>"],
                ["VAD_STOP_SECS", "0.2", "VAD_STOP_SECS_<CHANNEL>"],
                ["VAD_MIN_VOLUME", "0.6", "VAD_MIN_VOLUME_<CHANNEL>"],
              ]}
            />
            <p>
              The website is the only channel that overrides anything today: it pins its own
              language, because nova-3 is built around <Code>en</Code> and <Code>multi</Code>{" "}
              and a channel that should listen in Hindi only needs to say so. Every resolved
              value is logged during call setup, naming which keys were overridden, so a
              surprise on one channel is one grep away.
            </p>

            <Sub id="stt-connect">Connection and framing</Sub>
            <Steps
              ordered={false}
              items={[
                {
                  t: "Warm up at boot, not on the first call",
                  d: "Every provider in use opens and closes a connection at startup. Deepgram is a fresh websocket per call, so this mainly warms DNS and TLS session resumption, and it doubles as a check on the key and the model name: a typo shows up at boot instead of on a live call.",
                },
                {
                  t: "STTConnectGateProcessor holds the gap",
                  d: "pipecat launches Deepgram's handshake in the background and drops any audio that arrives before it finishes. Measured against this deployment's network path, a cold handshake took over two seconds. A customer who speaks right over the greeting would lose their entire first turn, and it looks like a broken microphone.",
                },
                {
                  t: "Flux needs no gate",
                  d: "Its start() blocks the pipeline until the socket is confirmed, so audio queues behind the start frame rather than being dropped.",
                },
                {
                  t: "Input framing is the carrier's, not ours",
                  d: "One websocket message becomes exactly one audio frame, so the framing is whatever the provider happens to send: Acefone 100ms and 120ms, the browser recorder 85ms. AudioRechunkerProcessor can re-frame toward the ~80ms Flux prefers, and is off by default because re-chunking downward always costs a little latency.",
                },
              ]}
            />

            <Sub id="stt-script">Script normalisation</Sub>
            <p>
              nova-3 is the most accurate model available for this audio, but it writes English
              loan words in Latin script even with <Code>language=hi</Code>: "मैं sun रहा हूँ",
              "मेरी booking confirm कर दीजिए". Switching models is not a fix, because nova-2 is
              inconsistent and whisper-large misrecognises the actual words and does not stream.
            </p>
            <Callout tone="brand" title="The transform is display only">
              Devanagari rendering is applied to what the browser shows. The text handed to the
              model stays exactly as the transcriber produced it, because the prompt is tuned
              on that form, and the Hindi prompt deliberately keeps loan words in Latin so Murf
              pronounces them correctly. Rewriting it would change call behaviour to fix a
              cosmetic issue. Coverage is a fixed map of travel vocabulary rather than a general
              transliterator: a wrong guess renders a real Hindi word as gibberish.
            </Callout>
          </Section>


          <Section id="llm" title="The language model">
            <p className="lede">
              The brain is an ordinary chatbot with voice shaped prompts and a voice shaped
              tool set. What makes it a <em>voice</em> brain is the reply it returns.
            </p>
            <LlmDiagram />

            <Sub id="llm-contract">The turn contract</Sub>
            <p>
              Every turn is one authenticated POST to <Code>PW_CHAT_API_URL</Code> carrying an{" "}
              <Code>X-Api-Token</Code> header. Voice is authenticated where the website and
              WhatsApp channels are not, because a callvoice session id is derived from the
              customer's phone number and is therefore guessable.
            </p>
            <Table
              head={["Field", "Carries"]}
              rows={[
                ["session_id", "voice-<digits> for a call, webvoice-<uuid> for a browser session"],
                ["message", "The joined transcript for this turn"],
                ["user_type", "callvoice or webvoice"],
                ["turn.turn_id, turn_kind, turn_reason", "Why this request exists and which turn it belongs to"],
                ["turn.assistant_prefix", "What the bot has already said this turn"],
                ["turn.last_action_ack", "The outcome of the previous voice_action"],
                ["voice_context", "Cart, customer, language, seconds remaining, turn index, capabilities"],
                ["deadline_ms", "How long this side is prepared to wait"],
              ]}
            />
            <p>
              The reply comes back as <Code>response_text</Code> (spoken),{" "}
              <Code>response_html</Code> (rendered, browser only), an optional{" "}
              <Code>voice_action</Code>, and diagnostics including token usage. Only the text
              between <Code>&lt;FRIENDLY_TEXT&gt;</Code> tags is spoken when those tags are
              present.
            </p>
            <Callout tone="ok" title="The context is rebuilt fresh on every turn">
              Cart contents, the language in force, seconds remaining and the current
              capability list are computed at the moment of the request rather than
              remembered. A hallucinated itinerary is the failure this removes: the model is
              told the booking, it does not recall it.
            </Callout>

            <Sub id="llm-prompt">Prompt layering and caching</Sub>
            <p className="docs-chain mono">
              system: base + channel prompt &rarr; history &rarr; system: per turn context
              &rarr; human: this turn
            </p>
            <p>
              The order is the point. The base prompt is byte identical on every turn, and the
              values that move per call live in a separate trailing system message placed{" "}
              <em>after</em> the history. Put that block in front instead and a backend that
              merges adjacent system messages sees a prefix that mutates every turn, so the
              prompt cache misses on all of it.
            </p>
            <Table
              head={["Layer", "callvoice", "webvoice"]}
              proseKey
              rows={[
                ["Base prompt", "voice_base.yml", "voice_base.yml"],
                ["Channel prompt", "callvoice.yml", "webvoice.yml"],
                ["Context block", "callvoice_context_block", "webvoice_context_block"],
                ["History table", "voice_history", "voice_history"],
                ["History depth", "12 turns", "10 turns"],
                ["Temperature / max tokens", "0.4 / 300", "0.4 / 300"],
                ["Reasoning effort", "low", "low"],
              ]}
            />
            <p>
              Both voice channels skip the intent gate and the optional parameter chain that
              the website flow runs. On a live call those passes are latency spent to reduce a
              risk that voice does not carry.
            </p>

            <Sub id="llm-tools">Tools and voice actions</Sub>
            <p>
              Tools are registered once in <Code>tool-ecosystem</Code> and filtered per channel
              by an exclusion list, so a phone call is never offered a tool that only makes
              sense with a screen. A voice tool returns an ordinary tool response plus an
              optional <Code>voice_action</Code>.
            </p>
            <Table
              head={["Tool", "Returns"]}
              rows={[
                ["voice_cart_details", "The parked cart, phrased for speech"],
                ["voice_apply_discount", "min(MAX, max(MIN, total x PCT)), refused outright when there is no real amount"],
                ["voice_offer_booking_link / voice_share_booking_link", "A WhatsApp booking link, plus send_booking_link"],
                ["voice_transfer_to_agent", "Its own spoken handoff line, plus transfer_to_agent"],
                ["voice_end_call", "The disposition, plus end_call"],
                ["voice_switch_language", "switch_language"],
                ["voice_log_disposition", "log_disposition"],
              ]}
            />
            <Callout tone="warn" title="voice_action is stripped from the tool message">
              Left in, the summary chain paraphrases "transfer_to_agent" into a sentence, the
              guardrail mutes that sentence for containing a tool name, and the customer hears
              silence at the exact moment they were promised a person.
            </Callout>

            <Sub id="llm-kinds">Turn kinds and hold lines</Sub>
            <Table
              head={["turn_kind", "What happens", "Model calls"]}
              rows={[
                ["user", "Full turn: history, model with tools bound, maybe a tool, reply", "1 or 2"],
                ["hold", "One tiny prompt for a contextual filler. Nothing written to history", "1"],
                ["greeting, recovery, closing", "Recorded in voice_history so the brain knows it was said", "0"],
              ]}
            />
            <p>
              A hold line names back what the customer asked for, so they know they were heard.
              It is composed in parallel from the moment the turn starts and dropped unheard if
              the real answer wins, and it is never written to history: it is filler covering a
              wait, and recording it would have the model treat it as something it already
              answered.
            </p>
            <p>
              Not every turn earns one. A turn made only of acknowledgements is a backchannel,
              not a lookup, and composing for it left the pending booking as the only concrete
              noun in the prompt, so the model announced a search that nobody had asked for.
              The assistant's own name counts as a backchannel too: a caller saying it is
              addressing her, not naming a subject.
            </p>

            <Sub id="llm-channels">callvoice against webvoice</Sub>
            <Table
              head={["", "callvoice", "webvoice"]}
              proseKey
              rows={[
                ["Summary chain", "off", "on"],
                ["Result HTML", "none, there is no screen", "streamed in 8KB chunks"],
                ["Renders as", "itself", "website, so legacy tools emit HTML"],
                ["Typical tool turn", "1 model call", "3 model calls"],
                ["Session lifetime", "keyed on the phone number, carries across calls", "fresh per socket"],
              ]}
            />
            <p>
              callvoice skips the summary chain because its tools write their own spoken lines
              already. webvoice keeps it, because its search tools return English prose with
              rupee symbols and URLs that have to become one speakable Hinglish sentence.
            </p>
          </Section>


          <Section id="tts" title="Text to speech">
            <p className="lede">
              Four engines sit behind one factory, and four filters sit in front of them. Three
              of those filters exist to stop something being said.
            </p>
            <TtsDiagram />

            <Sub id="tts-providers">Providers and voices</Sub>
            <Table
              head={["TTS_PROVIDER", "Transport", "Notable settings"]}
              rows={[
                ["murf", "Streaming websocket", "MURF_TTS_MODEL falcon-2, voice, style, rate, pitch, variation, buffer size and delay"],
                ["gemini", "Streaming generate_content", "TTS_MODEL, TTS_VOICE, wide emotional range, the largest latency risk here"],
                ["sarvam", "HTTP", "SARVAM_TTS_MODEL bulbul:v3, speaker, pace, language code"],
                ["openai", "Streaming HTTP", "OPENAI_TTS_MODEL, voice, instructions, speed"],
              ]}
            />
            <p>
              Murf is what production speaks with today, on a conversational style at 24kHz
              mono PCM. A voice is chosen from a listed set, <Code>Anisha</Code>,{" "}
              <Code>Ayushi</Code> or <Code>Pooja</Code>, rather than free text, which is why a
              typo cannot reach the provider through the console.
            </p>
            <Callout tone="brand" title="Per session overrides">
              The console's WebRTC panel can audition a provider, a voice or a sample rate
              against a real pipeline without moving the configuration everyone else runs on.
              The override is passed into the factory for that one session and nothing is
              written anywhere.
            </Callout>
            <p>
              Each provider is warmed at boot by talking to its underlying client directly
              rather than through the pipecat service. Those services are frame processors and
              need a task manager wired in by a running pipeline, so calling their own
              synthesis path outside one is not possible. The direct call is the same request
              the service would make internally, and gets the same warm up effect.
            </p>

            <Sub id="tts-hygiene">What never reaches the speaker</Sub>
            <Table
              head={["Filter", "Catches"]}
              rows={[
                ["SpokenTextSanitizer", "Invisible and stray characters, digit groups that should be spelled out"],
                ["GuardrailFilter: leaked tool call", "Bracketed call syntax, tool names, JSON argument objects"],
                ["GuardrailFilter: stage notes", "Bracketed or angled asides the model wrote to itself"],
                ["GuardrailFilter: unfilled placeholder", "A template variable the brain never filled in"],
                ["GuardrailFilter: leaked reasoning", "Phrases about the assistant, the guidelines or the tool call"],
                ["DuplicateSpeechFilter", "Near verbatim repeats within six lines, and a second sign off"],
              ]}
            />
            <Callout tone="halt" title="Why an unfilled placeholder is muted rather than spoken">
              Seen live as "और कुल amount {"{AMOUNT}"} है।", which the voice read aloud as the
              word AMOUNT. The customer is told a price exists and never told what it is.
              Quoting nothing is safer than quoting a placeholder, and the warning in the log
              surfaces the prompt bug behind it.
            </Callout>
            <p>
              The duplicate threshold is deliberately strict at 0.85 overlap. A looser
              threshold starts catching genuinely different lines that share vocabulary, two
              questions about the same booking overlap at roughly 0.75, and silencing a real
              line mid call is worse than letting one duplicate through.
            </p>

            <Sub id="tts-audio">Rates, gain and ambience</Sub>
            <Table
              head={["Leg", "Rate", "Why"]}
              proseKey
              rows={[
                ["Phone in and out", "8000 Hz", "What the carrier gives and takes, mu-law or PCM"],
                ["Website input", "16000 Hz", "Silero VAD accepts 8k or 16k and nothing else"],
                ["Website output", "24000 Hz", "What Murf synthesises and what the browser plays"],
                ["Murf synthesis", "24000 Hz", "Resampled by the serializer only when the wire needs it"],
              ]}
            />
            <p>
              The website's two rates are deliberately different because they apply to
              different legs. Pinning output to the pipeline rate as well used to force speech
              through 24k, then 16k, then 24k again, which permanently band limited the voice
              and made it sound dull for no benefit. At matched rates both resamplers short
              circuit and the audio reaches the browser untouched.
            </p>
            <p>
              <Code>BOT_OUTPUT_GAIN_DB</Code> lifts the synthesised audio before it hits the
              wire, currently by 5 dB. <Code>ENABLE_BACKGROUND_AMBIENCE</Code> mixes a quiet
              call centre bed underneath at <Code>BACKGROUND_AMBIENCE_LEVEL_DB</Code>, and is
              off today.
            </p>

            <Sub id="tts-language">Switching language mid call</Sub>
            <p>
              A <Code>switch_language</Code> action flips two things before the reply is
              spoken: the language state the next context block reports, and the TTS locale.
              The locale flip works by writing the provider's native locale setting in place,
              which only Murf exposes. On any other provider the switch is logged as
              unavailable rather than silently ignored, because a bot answering in Hindi with
              an English voice is a worse failure than not switching at all.
            </p>
          </Section>


          <Section id="tel" title="Telephony">
            <p className="lede">
              Acefone on the phone and the browser widget, each with its own handshake and
              envelope, converging on one pipeline that knows nothing about either.
            </p>
            <ChannelDiagram />

            <Sub id="tel-wire">Wire formats and serializers</Sub>
            <Table
              head={["Channel", "Audio", "Envelope", "Notes"]}
              proseKey
              rows={[
                [
                  "Acefone (Smartflo)",
                  "mu-law 8k",
                  "JSON media events",
                  "Production. Outbound chunks are ACEFONE_OUT_10MS_CHUNKS x 10ms",
                ],
                ["Website", "raw PCM", "JSON control frames", "Also carries state events and result HTML"],
              ]}
            />
            <Steps
              ordered={false}
              items={[
                {
                  t: "The Acefone serializer is subclassed for events the vendor sends but the library does not handle",
                  d: "stop and mark arrive on the same socket, and the docs do not guarantee an event key on every frame. An unhandled key raised inside the transport read loop, which surfaced as a dead call rather than a clean hang up. A caller hangup now ends the pipeline immediately instead of waiting for a socket timeout.",
                },
                {
                  t: "The website serializer speaks plain binary PCM",
                  d: "Binary messages are audio, text messages are control JSON. There is no telephony leg to drop the line, so the browser saying hangup is the only end-of-call signal there is.",
                },
              ]}
            />

            <Sub id="tel-dial">Placing a call</Sub>
            <p>
              Acefone resolves the streaming app from the API key in its own panel, so the
              dial request carries no URL at all and <Code>PUBLIC_WSS_BASE</Code> is not part
              of placing a call. It is still what you hand the provider's panel when pointing
              it at this server.
            </p>
            <p>
              Identifiers that have to survive the round trip are packed into the single
              <Code>custom_identifier</Code> string Acefone carries, and unpacked on the start
              event. A custom field can come back as the <em>key</em> of the parameters object
              with an empty value, so a bare valueless key is treated as the packed identifier
              only when it is genuinely the sole such key, otherwise an ordinary named
              parameter would be mistaken for a cart reference.
            </p>
            <Callout tone="halt" title="Two credentials on every dial">
              Since 30 September 2026 Acefone requires the access token on{" "}
              <Code>click_to_call_support</Code> as well as the API key.{" "}
              <Code>ACEFONE_API_KEY</Code> travels in the body and selects the streaming app;{" "}
              <Code>ACEFONE_AUTH_TOKEN</Code> travels as <Code>Authorization: Bearer</Code>. A
              request missing the token is refused with 401 "Token not provided".
            </Callout>
            <Callout tone="brand" title="Where dials come from">
              Calls are requested through QMS: an upstream system posts customer records to an
              intake API, each record is validated in full, and a valid record is parked in
              the cart store under its reference id and scheduled. The Phone test uses the
              same path. Every request and its outcome is listed in History.
            </Callout>

            <Sub id="tel-lifecycle">Lifecycle and webhooks</Sub>
            <p>
              Acefone posts call lifecycle events to <Code>/webhooks/acefone</Code>. They are
              answered 200 in almost every case, because a provider that retries a delivery it
              could not complete would otherwise replay it against a call that has already
              moved on.
            </p>
            <Steps
              ordered={false}
              items={[
                {
                  t: "Two idempotency layers",
                  d: "The event key is unique, and every status transition is rank guarded, so a replayed event cannot move a call backwards.",
                },
                {
                  t: "call_sessions tracks the legs",
                  d: "Acefone can move a call to a new leg during the call. The original and current call id and uuid are both held, with the leg history beside them.",
                },
                {
                  t: "Live calls are polled as well as pushed",
                  d: "ACEFONE_LIVE_CALLS_POLL_SECS reconciles what the provider thinks is live against what we think is live, which is what keeps the Live calls screen honest when a webhook is lost.",
                },
                {
                  t: "Transcripts are filed against the session",
                  d: "CALL_TRANSCRIPT_ENABLED writes each turn against the call_sessions row, so the agent who takes a transfer can read the conversation so far.",
                },
              ]}
            />

            <Sub id="tel-transfer">Transfer to a human</Sub>
            <p>
              A transfer is Acefone's Call Operations API, operation type 4, against a live
              call. Acefone identifies a live call by one of <Code>ref_id</Code>,{" "}
              <Code>call_id</Code> or <Code>uuid</Code>, and rejects a request carrying more
              than one, so all three are tried in order and whichever the provider recognises
              wins.
            </p>
            <Callout tone="warn" title="ref_id goes first, and the order is not arbitrary">
              <Code>ref_id</Code> is the identifier Acefone issued at origination and the only
              one that identifies the <em>call</em>. <Code>call_id</Code> and{" "}
              <Code>uuid</Code> identify a <em>connection</em>, and the provider may have moved
              the call to a new leg since we last saw them. That is exactly how a stale call id
              earns an "Invalid Call ID" rejection. The live identifiers are read back from{" "}
              <Code>call_sessions</Code> rather than trusted from the socket handshake snapshot.
            </Callout>
            <Steps
              ordered
              items={[
                { t: "The tool speaks its own handoff line", d: "So the customer is told before anything moves, and the brain adds nothing of its own on that turn." },
                { t: "The gate waits for the audio to play out", d: "execute_after_speech is true, so the action is held until BotStoppedSpeaking." },
                { t: "The provider is called", d: "POST /call/options with the destination normalised to Acefone's expected form." },
                { t: "Auto hang up is disabled", d: "The serializer would otherwise send an end event for a call that is no longer ours, and drop a customer who is now talking to a person." },
                { t: "The bot leg stops without ending the call", d: "Deliberately no EndTaskFrame upstream. The customer stays on the line." },
              ]}
            />
            <Callout tone="ok" title="If the transfer fails">
              The executor speaks a fallback line, acknowledges the action as failed on the
              next turn, and the call continues with the bot. The brain finds out it did not
              happen instead of assuming it did.
            </Callout>

            <Sub id="tel-limits">Ending a call</Sub>
            <Table
              head={["Setting", "Value", "Does"]}
              rows={[
                ["MAX_CALL_DURATION_SECS", "300", "Hard cap on a bot leg, telephony only"],
                ["CALL_WRAP_UP_WARNING_SECS", "30", "When the brain is told to start closing"],
                ["CALL_END_WATCHDOG_SECS", "20", "How long a closing may hang before the call is ended anyway"],
                ["MAX_CONSECUTIVE_REPROMPTS", "3", "Silent turns before the call is wrapped up"],
                ["USER_IDLE_TIMEOUT_SECS", "5", "Silence before a check in is offered"],
              ]}
            />
            <p>
              The reprompt counter is per call rather than per turn, and it is handed back when
              a check in is suppressed as a duplicate. Without that, a customer who heard one
              check in would be hung up on as though they had ignored three. A closing line
              spoken with no disposition recorded behind it arms the watchdog, which is the
              only thing standing between a brain that says goodbye and never reports an
              outcome, and a call that sits open until the hard cap.
            </p>
          </Section>


          <Section id="walk-call" title="A call, end to end">
            <p className="lede">
              An abandoned cart becomes a phone call. Follow the strip left to right: that is
              the order, and every step expands one of the boxes above.
            </p>

            <Sub id="walk-call-strip">The seven stages</Sub>
            <FlowStrip
              note="The bot leg ends at the transfer; the customer stays on the line with a person."
              stages={[
                { icon: Database, title: "Cart abandoned", who: "QMS intake", detail: "validated, parked, and scheduled" },
                { icon: PhoneOut, title: "Dial", who: "Acefone", detail: "the API key selects the streaming app" },
                { icon: Plug, title: "Socket opens", who: "pipeline", detail: "call id and number, cart looked back up" },
                { icon: Waves, title: "Greeting", who: "pipeline", tone: "bot", detail: "local template, about 1s saved" },
                { icon: Mic, title: "Each turn", who: "brain", tone: "bot", detail: "STT, then /voice/chat, then speech" },
                { icon: Alert, title: "Action", who: "executor", tone: "act", detail: "transfer, after the line finishes playing" },
                { icon: Check, title: "Disposition", who: "pipeline", tone: "done", detail: "written to call_records" },
              ]}
            />
            <Steps
              items={[
                {
                  t: "Trigger",
                  d: "An upstream system posts the customer record to a QMS intake API, or someone uses the Phone test. The cart lands in the cart store keyed by reference id and the dial is scheduled.",
                },
                {
                  t: "Dial",
                  d: "The provider calls the customer and streams the audio back. Acefone resolves the destination from the API key, so its dial carries no URL at all.",
                },
                {
                  t: "Answer",
                  d: "The channel parses the provider's handshake, pulls the customer's number and the provider's call id, and looks the cart back up.",
                },
                {
                  t: "Greeting",
                  d: "Spoken from a local template rather than the brain, a measured saving of about a second with a live person holding a phone. The brain is told on a silent turn so it does not greet twice.",
                },
                {
                  t: "Each turn",
                  d: "Audio to Deepgram, turn strategies decide the customer is done, the context is rebuilt fresh, and the turn is posted to the brain.",
                },
                {
                  t: "Holds",
                  d: "If the reply is slow the pipeline speaks a line naming back what was asked for. It is composed in parallel from the moment the turn starts and dropped unheard if the answer wins.",
                },
                {
                  t: "Action",
                  d: "transfer_to_agent waits for the handoff line to finish playing, then calls Acefone and stops the bot leg without hanging up on the customer.",
                },
                {
                  t: "End",
                  d: "end_call carries the disposition, so the close is one turn rather than the three the old local model flow needed.",
                },
              ]}
            />

            <Sub id="walk-call-timeline">A worked call</Sub>
            <Timeline
              title="An outbound abandoned cart call"
              subtitle="the production flow as configured today"
              rows={[
                {
                  at: "T minus 10s",
                  who: "system",
                  text: "The Abandoned cart API in QMS receives the customer record",
                  under: "Validated into a CartContext, parked in the cart store under reference id PW-88213, dial scheduled for INGESTION_CALL_DELAY_SECS later.",
                },
                {
                  at: "0.0s",
                  who: "phone",
                  text: "Acefone click to call, the customer's phone rings",
                  under: "Acefone maps the API key to the streaming app in its own panel, so the dial sends no URL. The request also carries ACEFONE_AUTH_TOKEN as a Bearer header, which Acefone requires on every dial.",
                },
                {
                  at: "0.0s",
                  who: "system",
                  text: "Customer answers, the WebSocket opens",
                  under: "The start event carries call_sid and the customer number. The session id becomes voice-918595864036, so a call next week resumes this history. A TransferHandle is built, which is what puts transfer_to_agent in capabilities.",
                },
                {
                  at: "0.6s",
                  who: "bot",
                  text: "नमस्ते Happy जी, मैं रिया, PlaceholderWorks से बोल रही हूँ।",
                  under: "Local template again, about a second saved with a live person on the line.",
                },
                {
                  at: "4.0s",
                  who: "bot",
                  text: "आपकी दिल्ली से जयपुर की booking अधूरी रह गई थी, आठ हज़ार चार सौ निन्यानवे रुपये की।",
                  under: "First real turn. The cart came from voice_context, not from the model.",
                },
                {
                  at: "11.2s",
                  who: "user",
                  text: "हाँ पर थोड़ा महंगा लग रहा है",
                  under: "The brain calls voice_apply_discount. The tool computes the capped percentage and refuses outright if there is no real amount, because promising money off an unpriced booking is a promise the customer will hold you to.",
                },
                {
                  at: "13.4s",
                  who: "bot",
                  text: "आपके लिए दो सौ चौवन रुपये की छूट लगा दी है, अब आठ हज़ार दो सौ पैंतालीस रुपये।",
                  under: "callvoice skips the summary chain: the tool wrote its own spoken line, so this turn cost one model call rather than three.",
                },
                {
                  at: "22.0s",
                  who: "user",
                  text: "मुझे किसी से बात करनी है",
                  under: "The brain calls voice_transfer_to_agent, which returns a voice_action rather than doing anything itself.",
                },
                {
                  at: "23.1s",
                  who: "bot",
                  text: "जी बिलकुल, मैं आपको customer care से जोड़ रही हूँ। एक moment।",
                  under: "execute_after_speech is true, so the pipeline speaks first and holds the action.",
                },
                {
                  at: "26.2s",
                  who: "phone",
                  text: "BotStoppedSpeaking, the transfer fires",
                  under: "The gate waited for the audio to actually play out, then posted /call/options to Acefone. Auto hang up is disabled and the bot leg ends, deliberately with no EndTaskFrame, because the customer now belongs to a human.",
                },
              ]}
            />
          </Section>

          <Section id="walk-web" title="A browser session">
            <p className="lede">
              Same pipeline, different envelope. The reply comes back as <em>both</em> speech
              and a rendered carousel, streamed down the same socket.
            </p>

            <Sub id="walk-web-strip">The six stages</Sub>
            <FlowStrip
              note="One socket carries three things: audio down, audio up, and JSON events for the page."
              stages={[
                { icon: Mic, title: "Mic granted", who: "visitor", detail: "socket opens with the chosen rate" },
                { icon: Waves, title: "Greeting", who: "pipeline", tone: "bot", detail: "fresh session, every visit starts clean" },
                { icon: Mic, title: "Asks out loud", who: "visitor", detail: "WhatsApp chatbot कैसे काम करता है?" },
                { icon: Globe, title: "Runs the search", who: "brain", tone: "bot", detail: "webvoice, with the knowledge base tool" },
                { icon: Waves, title: "Speaks the answer", who: "pipeline", tone: "bot", detail: "one short Hinglish line" },
                { icon: Check, title: "Renders the cards", who: "page", tone: "done", detail: "8KB chunks into a shadow root" },
              ]}
            />

            <Sub id="walk-web-timeline">A worked session</Sub>
            <Timeline
              title="A browser session, start to finish"
              subtitle="illustrative, the timings are the shape to expect"
              rows={[
                {
                  at: "0.0s",
                  who: "system",
                  text: "Visitor presses start, microphone granted",
                  under: "The website socket opens. Session id webvoice-3f9a2c1e, fresh, so this visit starts clean.",
                },
                {
                  at: "0.4s",
                  who: "bot",
                  text: "नमस्ते! मैं आरिया, PlaceholderWorks से। बताइए, आज मैं आपकी क्या मदद कर सकती हूँ?",
                  under: "Spoken from the local greeting template. A silent greeting turn is recorded with the brain so it does not greet again.",
                },
                {
                  at: "6.2s",
                  who: "user",
                  text: "मुझे दिल्ली से गोवा की flight चाहिए",
                  under: "Deepgram transcribes the utterance. The turn strategies wait for the configured silence before closing the turn.",
                },
                {
                  at: "6.3s",
                  who: "system",
                  text: "POST /voice/chat, turn_kind=user, webvoice",
                  under: "voice_context carries channel, language, turn index and capabilities. The hold line compose fires at the same moment, in parallel.",
                },
                {
                  at: "7.5s",
                  who: "bot",
                  text: "जी, दिल्ली से गोवा की flights देख रही हूँ…",
                  under: "The contextual hold line, composed on a tiny prompt, and only spoken because the real answer had not landed by PW_CHAT_HOLD_DELAY_SECS. It names the route back, so the visitor knows they were heard.",
                },
                {
                  at: "9.8s",
                  who: "bot",
                  text: "दिल्ली से गोवा के लिए कल की flights मिल गई हैं, सबसे सस्ती पंद्रह हज़ार एक सौ चौबीस रुपये की है।",
                  under: "The brain ran search_flights, then the summary chain turned English prose with rupee symbols and URLs into one spoken Hinglish line. response_html streams down the same socket in 8KB chunks.",
                },
                {
                  at: "9.9s",
                  who: "screen",
                  text: "Flight carousel renders beside the mic",
                  under: "result_pending, then result_html chunks, then rendered in a shadow root. A latency row lands with it: STT 180, LLM 3100, TTS 240.",
                },
                {
                  at: "14.1s",
                  who: "user",
                  text: "सबसे सस्ती वाली दिखाओ",
                  under: "No new search. The result surface recognises the cheapest and costliest rule and re-filters the listing it already has.",
                },
                {
                  at: "31.0s",
                  who: "system",
                  text: "Visitor presses hangup",
                  under: "Nothing else can end this session: no duration timer, no idle nudge, no watchdog. A visitor reading cards is legitimately silent.",
                },
              ]}
            />
            <Callout tone="brand" title="What to watch in the Browser test">
              Every one of those rows shows up live: the carousel in the session card, the per
              turn bar in the Latency panel, and the hold line as the status under the orb. Run
              it at 8k to hear what a phone line would actually sound like.
            </Callout>
          </Section>


          <Section id="ops-latency" title="Latency and cost">
            <p className="lede">
              Three legs are timed on every turn, and every leg has a price attached to it.
            </p>
            <LatencyDiagram />

            <Sub id="ops-budget">The three legs</Sub>
            <p>
              <Code>LatencyObserver</Code> times transcription, the brain and synthesis per
              turn. <strong>Browser test</strong> renders them live as a stacked bar
              with a tick marking the browser measured end to end. Phone calls log the same
              breakdown at teardown.
            </p>
            <Callout tone="warn" title="Turn boundaries are detected by identity, not by name">
              The observer used to compare the frame source's name against a literal string
              with a zero suffix. pipecat numbers its objects with a global per process
              counter, so only the first call in a container ever matched, and every call after
              it silently captured nothing while still reporting cost. Identity against the
              actual aggregator instance has no such failure mode.
            </Callout>
            <p>
              The engine also has to declare that it can generate metrics. That flag defaults
              to off, which made every timing call on the brain leg a no op, and is why every
              figure in the console once read as a dash.
            </p>

            <Sub id="ops-cost">What a call costs</Sub>
            <Table
              head={["Leg", "Priced by", "Note"]}
              rows={[
                ["STT", "Per minute of call, by provider and model", "Flux is priced above nova-3; an unknown pair falls back to a conservative rate"],
                ["LLM", "Per prompt, cached prompt and completion token", "A cached prompt token is half the price of a fresh one"],
                ["TTS", "Per thousand characters synthesised", "Murf and Sarvam are priced separately"],
              ]}
            />
            <p>
              Costs are reported in rupees at a fixed conversion. Usage events are deduplicated
              with a high water mark per source, because the same metric can be emitted more
              than once per turn and counting both would quietly inflate every call in the
              ledger.
            </p>
            <Callout tone="brand" title="Why cached tokens are worth designing for">
              The prompt prefix is roughly twelve thousand tokens and it is sent on every turn
              of every call. Keeping it byte identical is what lets the provider serve it from
              cache at half price, and it is the single largest lever on the cost of a long
              call. That is the entire reason the per turn context block sits after the history
              rather than in front of it.
            </Callout>
          </Section>

          <Section id="ops-config" title="Configuration">
            <p className="lede">
              Configuration splits along the same line as the code. If it shapes sound or
              telephony it lives here. If it shapes what the bot says or can do, it lives in{" "}
              <Code>pw-llm-layer</Code>.
            </p>
            <ConfigDiagram />

            <Sub id="ops-resolution">Where a value comes from</Sub>
            <p className="docs-chain mono">
              settings store (Postgres) &rarr; registry default
            </p>
            <p>
              With <Code>USE_DB=true</Code> the database is the single source for every voice
              setting. A value saved on the Settings screen is final and applies to the next
              call; editing <Code>.env</Code> afterwards changes nothing. The process
              environment is read only for the handful of settings that need a restart
              (<Code>HOST</Code>, <Code>PORT</Code>, <Code>LOG_LEVEL</Code> and their kind) and
              for the bootstrap values listed below. With <Code>USE_DB=false</Code> the
              container reads <Code>.env</Code> and nothing else, and Settings is read only.
            </p>
            <Table
              head={["This service, 140 settings", "pw-llm-layer, 27 settings"]}
              rows={[
                ["ENABLE_*, *_WS_PATH, provider credentials", "VOICE_LLM_MODEL, TEMPERATURE, MAX_TOKENS"],
                ["STT_*, TTS_*, MURF_*, VAD_*, turn taking", "CALLVOICE_ and WEBVOICE_HISTORY_LIMIT"],
                ["MAX_CALL_DURATION_SECS, CALL_TRANSFER_*", "RETENTION_DISCOUNT_PERCENT, MIN, MAX"],
                ["PW_CHAT_*, how to reach the brain", "VOICE_WHATSAPP_*, the booking link"],
                ["INGESTION_*, DISPOSITION_LOG_WEBHOOK", "VOICE_SESSION_STATE_TTL_SECS"],
              ]}
            />
            <Callout tone="halt" title="One value has to match on both sides">
              <Code>PW_CHAT_API_TOKEN</Code> here must equal <Code>VOICE_API_TOKEN</Code>{" "}
              there. It authenticates every turn <em>and</em> the settings proxy, so if it
              drifts the bot goes mute and the Brain section stops loading at the same moment.
            </Callout>
            <Callout tone="brand" title="Reset means the default, not the file">
              <strong>Reset to default</strong> deletes the stored row, so the setting falls
              back to the registry default shipped with the code. It never re-reads{" "}
              <Code>.env</Code>. A row for a setting the code no longer has is dropped at boot,
              so the table always describes the running code.
            </Callout>

            <Sub id="ops-envonly">Env only by design</Sub>
            <p>
              16 values here and one in the chatbot are read from the environment and are
              deliberately <em>not</em> editable from the screen they configure.
            </p>
            <Table
              head={["Value", "Why it cannot live in the store"]}
              rows={[
                ["USE_DB, DATABASE_URL, DOCKER_DATABASE_URL", "They are how the store is reached at all"],
                ["DASHBOARD_* (6 values)", "They are who may open the screen and edit it"],
                ["INTERNAL_LOG_TOKEN", "The only credential on the log routes"],
                ["SMTP_* (5 values), DASHBOARD_PUBLIC_URL", "Invite and password emails go out before anyone can sign in"],
                ["VOICE_API_TOKEN (chatbot)", "The credential on the endpoint that edits these very settings"],
              ]}
            />
            <p>
              Putting any of them inside the store would mean changing the lock through the
              door it secures. A test asserts this list stays exactly this long, so a new key
              cannot quietly join it.
            </p>

            <Sub id="ops-bootstrap">First boot and recovery</Sub>
            <Steps
              ordered
              items={[
                { t: "First boot seeds the table", d: "When a service finds its settings table empty, it copies its own .env into it once, so switching the database on does not change how the bot behaves." },
                { t: "From then on the database decides", d: "Every later change is made on the Settings screen, recorded with who made it and when, and applied without a restart unless the setting says otherwise." },
                { t: "A bad stored value does not stop the service", d: "If the stored settings fail validation at boot, the container starts on its environment values, logs which setting to fix, and keeps the console reachable so it can be corrected." },
                { t: "An unreachable database does not stop it either", d: "The pipeline starts on the registry defaults and says so in the log; the Settings screen reports the database as unreachable." },
              ]}
            />
          </Section>

          <Section id="ops-settings" title="The Settings screen">
            <p className="lede">
              One screen, two services, 163 values, organised by the question you actually have
              rather than by which container owns the answer.
            </p>

            <Sub id="ops-layout">How it is organised</Sub>
            <Table
              head={["Section", "Answers", "Lives in"]}
              proseKey
              rows={[
                ["Website", "The browser voicebot: armed, path, its VAD and STT", "this service"],
                ["Call", "The phone line: Acefone, transfer, limits, QMS intake", "this service"],
                ["Common", "Language, STT, TTS, turn taking, the chatbot connection", "this service"],
                ["Brain", "Model parameters, memory, discount, WhatsApp booking link", "pw-llm-layer"],
              ]}
            />
            <p>
              Everything about a provider, armed or not, its path, its credentials, its VAD and
              STT tuning, is inside that provider's own group rather than split across a
              Telephony screen and a Deployment screen. Groups longer than six settings carry
              sub headings, and anything you would touch once a year is behind{" "}
              <strong>advanced</strong>.
            </p>

            <Sub id="ops-save">Where a save goes</Sub>
            <FlowStrip
              note="A draft touching both services is still one Apply. Each half is validated by the service that owns it before anything is written."
              stages={[
                { icon: Sliders, title: "You edit", who: "browser", tone: "brand", detail: "draft is local until Apply" },
                { icon: Globe, title: "One Apply", who: "dashboard", detail: "split by which service owns each key" },
                { icon: Database, title: "app_settings", who: "pw_voicebot", detail: "written directly" },
                { icon: Plug, title: "voice_settings", who: "pw-llm-layer", tone: "act", detail: "proxied over HTTP with X-Api-Token" },
                { icon: PhoneOut, title: "Next turn", who: "live call", tone: "done", detail: "no restart" },
              ]}
            />
            <Table
              head={["Endpoint", "Does"]}
              rows={[
                ["GET /api/admin/settings", "This service's catalog and values"],
                ["PUT /api/admin/settings", "Save here, validated against the whole running config"],
                ["POST /api/admin/settings/reset", "Delete stored rows so the registry default applies"],
                ["GET|PUT /api/admin/brain/settings", "Proxied to the chatbot's /voice/settings"],
                ["POST /api/admin/brain/settings/reset", "One delete per key, over the same proxy"],
              ]}
            />
            <p>
              The proxy's URL is <em>derived</em> from <Code>PW_CHAT_API_URL</Code> rather than
              being a second setting. The settings endpoint is the chat endpoint's sibling, so
              one cannot be right while the other is wrong. If the chatbot is unreachable the
              Brain section says so and names the address it tried, and everything else on the
              screen keeps working.
            </p>

            <Sub id="ops-inherit">Empty is a value</Sub>
            <p>
              16 settings are per-channel overrides, and 14 of them are empty right now. Empty
              means <em>this channel has nothing of its own, use the global</em>. They are not
              missing configuration, which is why the screen shows what each one resolves to
              rather than an empty box.
            </p>
            <Steps
              ordered
              items={[
                { t: "Fill one field", d: "Setting VAD_CONFIDENCE_ACEFONE to 0.9 makes Acefone listen at 0.9." },
                { t: "Only that key moves", d: "Acefone's start, stop and minimum volume still come from the globals. The override dictionary carries only keys that are actually filled in, so one field does not copy the whole block onto the channel." },
                { t: "No other channel changes", d: "The website stays on the global value." },
                { t: "It applies to the next call", d: "The analyzer is built during call setup, and the log line names which keys were overridden." },
                { t: "Clearing it returns to the global", d: "Empty the field and Apply, or use Reset. There is no third state." },
              ]}
            />
            <Callout tone="warn" title="Why PW_CHAT_BRAIN_* is empty on purpose">
              These pick which brain a channel runs, <Code>callvoice</Code> or{" "}
              <Code>webvoice</Code>. Filling both would write the same answer in two places,
              so changing <Code>PW_CHAT_USER_TYPE_PHONE</Code> later would leave a stale row
              and a channel quietly running the wrong prompt. They exist as an escape
              hatch: set <Code>PW_CHAT_BRAIN_WEBSITE=callvoice</Code> and a browser tab drives
              the full abandoned cart flow with no telephony at all.
            </Callout>

            <Sub id="ops-validate">Validation and secrets</Sub>
            <Steps
              ordered={false}
              items={[
                {
                  t: "Per field",
                  d: "Type, range and step are checked against the catalog, and a dropdown accepts only a listed option, which is why a voice name cannot be mistyped into the store.",
                },
                {
                  t: "Cross field",
                  d: "A candidate configuration is built from everything already in force before the write. The user turn stop timeout has to outlast the smart turn stop; the discount floor cannot sit above its ceiling. The pair is caught here rather than at the next boot.",
                },
                {
                  t: "If a bad value gets in anyway",
                  d: "The container starts on its environment values and logs which setting to fix, rather than refusing to boot.",
                },
                {
                  t: "Secrets reach the browser only on request",
                  d: "A stored secret shows as a masked field. Its value is loaded only when someone with Reveal secrets clicks into it or presses the eye, and each reveal is logged. Clearing is an explicit action, and the audit trail records secrets as set or cleared, never in the clear.",
                },
              ]}
            />
          </Section>
        </article>
      </div>
    </div>
  );
}

function Section({ id, title, children }) {
  const meta = META[id];
  const Icon = meta?.icon;
  return (
    <section id={id} className="docs-section">
      <header className="docs-section-head">
        {Icon && (
          <span className="docs-section-icon">
            <Icon size={16} />
          </span>
        )}
        <div>
          {meta?.part && (
            <div className="docs-section-topic tiny">
              <span className="mono">{String(meta.index).padStart(2, "0")}</span>
              {meta.part}
            </div>
          )}
          <h2>{title}</h2>
          {meta?.summary && <p className="docs-section-sum tiny">{meta.summary}</p>}
        </div>
      </header>
      {children}
    </section>
  );
}

function Sub({ id, children }) {
  return (
    <h3 id={id} className="docs-sub">
      {children}
    </h3>
  );
}

function Code({ children }) {
  return <code className="docs-code mono">{children}</code>;
}

function Callout({ tone = "brand", title, children }) {
  return (
    <div className={`docs-callout tone-${tone}`}>
      <div className="docs-callout-title">{title}</div>
      <div>{children}</div>
    </div>
  );
}

function Steps({ items, ordered = true }) {
  return (
    <ol className={`docs-steps ${ordered ? "" : "plain"}`}>
      {items.map((item, index) => (
        <li key={item.t}>
          {ordered && <span className="docs-step-n mono">{index + 1}</span>}
          <div>
            <strong>{item.t}</strong>
            <p>{item.d}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

function Table({ head, rows, proseKey = false }) {
  return (
    <div className={`table-wrap docs-table ${proseKey ? "prose-key" : ""}`}>
      <table className="table">
        <thead>
          <tr>
            {head.map((cell) => (
              <th key={cell}>{cell}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row[0]}>
              {row.map((cell, index) => (
                <td key={index} className={index === 0 ? "docs-td-key" : ""}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
