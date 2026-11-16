export const TYPE_LABELS = {
  text: "Text", number: "Number", integer: "Whole number", date: "Date", datetime: "Date and time",
  enum: "Choice", phone: "Phone", email: "Email", url: "Link", boolean: "Yes / no",
};

export function span(secs) {
  const s = Number(secs);
  if (!Number.isFinite(s) || s <= 0) return "0 s";
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${+(s / 60).toFixed(1)} min`;
  if (s < 86400) return `${+(s / 3600).toFixed(1)} h`;
  return `${+(s / 86400).toFixed(1)} d`;
}

export const delayOf = (s) => s.delaySecs ?? s.delayDefault;
export const dedupeOf = (s) => s.dedupeWindowSecs ?? s.dedupeDefault;

export function triggerText(s) {
  const delay = Number(delayOf(s));
  return [
    delay > 0 ? `${span(delay)} after a record arrives` : "As soon as a record arrives",
    s.callHoursStart && s.callHoursEnd ? `only ${s.callHoursStart}–${s.callHoursEnd} IST` : "at any hour",
  ].join(", ");
}

export function endpointOf(s, base) {
  return `${(base || window.location.origin).replace(/\/$/, "")}${s.path}`;
}

export function stateOf(s, globallyOn = true) {
  if (!globallyOn) return { label: "QMS off", tone: "halt", live: false };
  if (!s.enabled) return { label: "Off", tone: "", live: false };
  if (!s.tokenSet) return { label: "No token", tone: "warn", live: false };
  if (!s.agent) return { label: "No agent", tone: "warn", live: false };
  if (s.agentReady === false) return { label: "Agent not live", tone: "warn", live: false };
  return { label: "Active", tone: "ok", live: true };
}

export function curlFor(s, base) {
  return [
    `curl -X POST '${endpointOf(s, base)}'`,
    `  -H 'Content-Type: application/json'`,
    `  -H 'X-API-Key: <token>'`,
    `  -d '${JSON.stringify(s.samplePayload)}'`,
  ].join(" \\\n");
}
