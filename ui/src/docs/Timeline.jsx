import { Mic, PhoneOut, Waves, Activity, Check } from "../components/Icons";

const ROLES = {
  user: { label: "customer", icon: Mic },
  bot: { label: "bot", icon: Waves },
  system: { label: "system", icon: Activity },
  screen: { label: "screen", icon: Check },
  phone: { label: "telephony", icon: PhoneOut },
};

export default function Timeline({ rows, title, subtitle }) {
  return (
    <figure className="timeline">
      {title && (
        <figcaption className="timeline-head">
          <strong>{title}</strong>
          {subtitle && <span className="tiny faint">{subtitle}</span>}
        </figcaption>
      )}
      <ol className="timeline-rows">
        {rows.map((row, index) => {
          const role = ROLES[row.who] || ROLES.system;
          const Icon = role.icon;
          return (
            <li key={index} className={`tl-row tl-${row.who}`} style={{ "--i": index }}>
              <span className="tl-at mono tiny">{row.at}</span>
              <span className="tl-marker">
                <Icon size={12} />
              </span>
              <div className="tl-body">
                <div className="tl-who tiny">{role.label}</div>
                <div className="tl-text">{row.text}</div>
                <div className="tl-under tiny">{row.under}</div>
              </div>
            </li>
          );
        })}
      </ol>
    </figure>
  );
}
