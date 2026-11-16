export const SAMPLE_CUSTOMER = "Rahul";

export function fillPersona(text, persona, customer = SAMPLE_CUSTOMER, variables = [], { greeting = false } = {}) {
  const agent = persona?.agent_name || "";
  let out = text || "";
  if (greeting && out && !out.includes("{customer_name}")) {
    const salutation = /^\s*(नमस्ते|नमस्कार|namaste|hello|hi|hey)(?:\s+there)?(?=[\s,!।.]|$)[\s,!।.]*/i;
    const hindi = /[\u0900-\u097F]/.test(out);
    out = salutation.test(out)
      ? out.replace(salutation, (_, word) => `${word} {customer_name}, `)
      : `${hindi ? "नमस्ते" : "Hello"} {customer_name}, ${out}`;
  }
  if (/[\u0900-\u097F]/.test(out)) out = out.replace(/\{customer_name\}(?!\s*जी)/g, "{customer_name} जी");
  for (const v of variables || []) if (v.key) out = out.replaceAll(`{${v.key}}`, v.value || "");
  return out
    .replaceAll("{customer_name}", customer)
    .replaceAll("{agent_name_hindi}", persona?.agent_name_hindi || agent)
    .replaceAll("{agent_name}", agent)
    .replaceAll("{company}", persona?.company || "");
}
