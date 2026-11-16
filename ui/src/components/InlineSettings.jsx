import { useState } from "react";
import { Check, Info } from "./Icons";
import { SecretInput } from "./ui";
import { useAuth } from "../lib/auth";
import { api } from "../lib/api";
import { useToast } from "../lib/toast";

const SENTINEL = "__clear__";

export default function InlineSettings({
  title,
  blurb,
  settings = [],
  editable = true,
  columns = 2,
  onSaved,
}) {
  const toast = useToast();
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState(false);

  const dirty = Object.keys(draft);

  const valueOf = (setting) =>
    draft[setting.key] !== undefined ? draft[setting.key] : setting.value;

  const set = (key, value) =>
    setDraft((current) => {
      const next = { ...current };
      const original = settings.find((s) => s.key === key)?.value ?? "";
      if (String(value) === String(original)) delete next[key];
      else next[key] = value;
      return next;
    });

  async function save() {
    setSaving(true);
    try {
      const result = await api.saveSettings(draft, true);
      setDraft({});
      toast.ok(result.message);
      await onSaved?.();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (!settings.length) return null;

  return (
    <section className="card inline-settings">
      <div className="card-head">
        <div style={{ flex: 1 }}>
          <h3>{title}</h3>
          {blurb && <p>{blurb}</p>}
        </div>
        {dirty.length > 0 && (
          <div className="row" style={{ gap: 8 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => setDraft({})} disabled={saving}>
              Reset
            </button>
            <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>
              <Check size={13} />
              {saving ? "Applying…" : `Apply ${dirty.length}`}
            </button>
          </div>
        )}
      </div>

      <div className="card-body">
        <div className={`inline-grid cols-${columns}`}>
          {settings.map((setting) => (
            <Field
              key={setting.key}
              setting={setting}
              value={valueOf(setting)}
              changed={draft[setting.key] !== undefined}
              editable={editable}
              onChange={(v) => set(setting.key, v)}
            />
          ))}
        </div>

        {!editable && (
          <p className="hint row" style={{ gap: 6, marginTop: 12 }}>
            <Info size={13} />
            This server reads .env, so these are read-only. Set USE_DB=true to edit them here.
          </p>
        )}
      </div>
    </section>
  );
}

function Field({ setting, value, changed, editable, onChange }) {
  const { can } = useAuth();
  const canReveal = can("secrets.reveal");
  const id = `inline-${setting.key}`;
  const disabled = !editable;

  return (
    <div className={`inline-field ${changed ? "changed" : ""}`}>
      <label className="label" htmlFor={id} title={setting.help}>
        {setting.label}
        {changed && <span className="inline-dot" />}
      </label>

      {setting.type === "bool" ? (
        <button
          id={id}
          type="button"
          role="switch"
          aria-checked={String(value) === "true"}
          className={`toggle ${String(value) === "true" ? "on" : ""}`}
          disabled={disabled}
          onClick={() => onChange(String(value) === "true" ? "false" : "true")}
        >
          <span className="toggle-knob" />
        </button>
      ) : setting.options?.length ? (
        <select
          id={id}
          className="input"
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        >
          {setting.options.map((option) => {
            const val = typeof option === "object" ? option.value : option;
            const text = typeof option === "object" ? option.label || option.value : option;
            return (
              <option key={val} value={val}>
                {text}
              </option>
            );
          })}
        </select>
      ) : setting.secret ? (
        <SecretInput id={id} value={value} onChange={onChange} hasValue={setting.hasValue} clearValue={SENTINEL}
          disabled={disabled} reveal={canReveal ? () => api.revealSetting(setting.key) : null} />
      ) : (
        <div className={setting.unit ? "numwrap" : ""}>
          <input
            id={id}
            className={`input ${setting.type === "number" ? "mono" : ""}`}
            type={setting.type === "number" ? "number" : "text"}
            value={value}
            disabled={disabled}
            onChange={(e) => onChange(e.target.value)}
          />
          {setting.unit && <span className="numunit mono">{setting.unit}</span>}
        </div>
      )}

      {setting.help && <p className="hint">{setting.help}</p>}
    </div>
  );
}

export { SENTINEL };
