export default function FlowStrip({ stages, note }) {
  return (
    <figure className="flowstrip">
      <ol className="flowstrip-track">
        {stages.map((stage, index) => (
          <li
            key={stage.title}
            className={`flowstage tone-${stage.tone || "neutral"}`}
            style={{ "--i": index }}
          >
            <div className="flowstage-card">
              <span className="flowstage-icon">
                <stage.icon size={16} />
              </span>
              <span className="flowstage-title">{stage.title}</span>
              <span className="flowstage-who tiny">{stage.who}</span>
              {stage.detail && <span className="flowstage-detail tiny">{stage.detail}</span>}
            </div>
            {index < stages.length - 1 && (
              <div className="flowstage-link" aria-hidden="true">
                <span className="flowstage-pulse" style={{ "--i": index }} />
              </div>
            )}
          </li>
        ))}
      </ol>
      {note && <figcaption className="tiny faint">{note}</figcaption>}
    </figure>
  );
}
