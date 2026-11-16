import { signatureOf } from "./resultHtml.js";

export const MAX_RESULTS = 4;

export function mergeResult(list, seq, patch, max = MAX_RESULTS) {
  if (patch === null) return list.filter((r) => r.seq !== seq);

  const row = { seq, at: Date.now(), ...patch };
  if (patch.html) row.sig = patch.resultId || signatureOf(patch.html);

  const found = list.some((r) => r.seq === seq);
  let next = found
    ? list.map((r) => (r.seq === seq ? { ...r, ...row } : r))
    : [...list, row];

  if (row.sig) {
    next = next.filter((r) => r.seq === seq || r.sig !== row.sig);
    next = next.filter((r) => r.seq === seq || r.status !== "error");
  }

  if (patch.status === "error") {
    next = next.filter((r) => r.seq === seq || r.status !== "error");
  }

  return next.length > max ? next.slice(next.length - max) : next;
}
