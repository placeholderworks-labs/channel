import { Toggle } from "./ui";

export function testFields(intake, fields) {
  if (intake?.kind !== "cart") return fields;
  return fields.map((f) => (f.key === "status" ? { ...f, fixed: "payment_pending" } : f));
}

const valueOf = (field, value) => field.fixed ?? value?.[field.key];

export function isRequired(field, value) {
  if (field.required) return true;
  const cond = field.required_if;
  return !!cond && String(value?.[cond.field] ?? "").toLowerCase() === String(cond.equals).toLowerCase();
}

export function missingFields(fields, value) {
  return fields.filter((f) => {
    const v = valueOf(f, value);
    return isRequired(f, value) && (v === undefined || v === null || String(v).trim() === "");
  });
}

export function toRecord(fields, value) {
  const out = {};
  for (const f of fields) {
    const v = valueOf(f, value);
    if (v === undefined || v === null || String(v).trim() === "") continue;
    if (f.type === "number" || f.type === "integer") out[f.key] = Number(v);
    else if (f.type === "boolean") out[f.key] = !!v;
    else if (f.type === "datetime") out[f.key] = String(v).length === 16 ? `${v}:00+05:30` : v;
    else out[f.key] = typeof v === "string" ? v.trim() : v;
  }
  return out;
}

function Input({ field, value, onChange, invalid }) {
  const cls = `input ${invalid ? "err" : ""} ${["phone", "number", "integer", "date", "datetime"].includes(field.type) ? "mono" : ""}`;
  const set = (e) => onChange(e.target.value);
  if (field.fixed !== undefined) return <input className="input mono" value={String(field.fixed).replaceAll("_", " ")} disabled />;
  switch (field.type) {
    case "enum":
      return (
        <select className={`input select ${invalid ? "err" : ""}`} value={value ?? ""} onChange={set}>
          <option value="">Choose…</option>
          {(field.options || []).map((o) => <option key={o} value={o}>{o.replaceAll("_", " ")}</option>)}
        </select>
      );
    case "boolean":
      return <div style={{ paddingTop: 6 }}><Toggle checked={!!value} onChange={onChange} label={field.label} /></div>;
    case "number":
    case "integer":
      return <input className={cls} type="number" step={field.type === "integer" ? 1 : "any"} min={field.min ?? undefined} max={field.max ?? undefined}
        value={value ?? ""} onChange={set} placeholder={field.example !== undefined ? String(field.example) : ""} />;
    case "date":
      return <input className={cls} type="date" value={value ?? ""} onChange={set} />;
    case "datetime":
      return <input className={cls} type="datetime-local" value={value ?? ""} onChange={set} />;
    case "phone":
      return <input className={cls} inputMode="tel" value={value ?? ""} onChange={set} placeholder={String(field.example ?? "9876543210")} />;
    case "email":
      return <input className={cls} type="email" value={value ?? ""} onChange={set} placeholder={String(field.example ?? "")} />;
    default:
      return <input className={cls} value={value ?? ""} onChange={set} placeholder={field.example !== undefined ? String(field.example) : ""} />;
  }
}

export default function RecordForm({ fields, value, onChange, errors = {}, touched = false, hide = [] }) {
  const shown = fields.filter((f) => !hide.includes(f.key));
  return (
    <div className="grid grid-2" style={{ gap: 12 }}>
      {shown.map((f) => {
        const required = isRequired(f, value);
        const empty = valueOf(f, value) === undefined || String(valueOf(f, value) ?? "").trim() === "";
        const error = errors[f.key] || (touched && required && empty ? "required" : "");
        return (
          <div className="field" key={f.key}>
            <label className="label">
              {f.label || f.key}
              {required && <span className="req-star"> *</span>}
              <span className="label-note mono">{f.key}</span>
            </label>
            <Input field={f} value={value[f.key]} invalid={!!error} onChange={(v) => onChange({ ...value, [f.key]: v })} />
            {error ? <p className="hint field-err">{error}</p> : f.fixed !== undefined ? <p className="hint">Fixed for tests. Other values come from the live intake.</p> : f.description ? <p className="hint">{f.description}</p> : null}
          </div>
        );
      })}
    </div>
  );
}
