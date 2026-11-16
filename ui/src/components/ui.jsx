import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Alert, Eye, X } from "./Icons";

export function Toggle({ checked, onChange, disabled, label, size = "md" }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={!!checked}
      aria-label={label}
      disabled={disabled}
      className={`tgl tgl-${size} ${checked ? "on" : ""}`}
      onClick={() => onChange?.(!checked)}
    >
      <span className="tgl-knob" />
    </button>
  );
}

export function Slider({ value, onChange, min = 0, max = 100, step = 1, unit = "", disabled, format }) {
  const number = Number.isFinite(Number(value)) ? Number(value) : min;
  const pct = max > min ? ((Math.min(Math.max(number, min), max) - min) / (max - min)) * 100 : 0;
  const shown = format ? format(number) : `${number}${unit ? ` ${unit}` : ""}`;
  const decimals = String(step).includes(".") ? String(step).split(".")[1].length : 0;

  return (
    <div className={`sld ${disabled ? "off" : ""}`}>
      <div className="sld-track-wrap">
        <input
          type="range"
          className="sld-input"
          min={min}
          max={max}
          step={step}
          value={number}
          disabled={disabled}
          style={{ "--pct": `${pct}%` }}
          onChange={(e) => onChange?.(Number(Number(e.target.value).toFixed(decimals)))}
        />
        <span className="sld-bubble" style={{ left: `${pct}%` }}>{shown}</span>
      </div>
      <input
        type="number"
        className="input mono sld-num"
        min={min}
        max={max}
        step={step}
        value={number}
        disabled={disabled}
        onChange={(e) => e.target.value !== "" && onChange?.(Number(e.target.value))}
      />
    </div>
  );
}

export function Segmented({ value, onChange, options, size = "md", disabled }) {
  return (
    <div className={`segc segc-${size}`} role="radiogroup">
      {options.map((opt) => {
        const o = typeof opt === "string" ? { value: opt, label: opt } : opt;
        const on = String(value) === String(o.value);
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            disabled={disabled}
            className={`segc-btn ${on ? "on" : ""}`}
            onClick={() => onChange?.(o.value)}
          >
            {o.icon}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function Select({ value, onChange, options, placeholder, disabled, mono, className = "" }) {
  return (
    <select
      className={`input select ${mono ? "mono" : ""} ${className}`}
      value={value ?? ""}
      disabled={disabled}
      onChange={(e) => onChange?.(e.target.value)}
    >
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((opt) => {
        const o = typeof opt === "string" ? { value: opt, label: opt || "-" } : opt;
        return (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        );
      })}
    </select>
  );
}

export function TagInput({ value = [], onChange, placeholder = "Type and press Enter", disabled, mono }) {
  const [draft, setDraft] = useState("");
  const add = (text) => {
    const parts = text.split(/[,\n]/).map((t) => t.trim()).filter(Boolean);
    const next = [...value];
    for (const p of parts) if (!next.some((v) => v.toLowerCase() === p.toLowerCase())) next.push(p);
    if (next.length !== value.length) onChange?.(next);
    setDraft("");
  };
  return (
    <div className={`tags ${disabled ? "off" : ""}`}>
      {value.map((tag, i) => (
        <span key={`${tag}-${i}`} className={`tag ${mono ? "mono" : ""}`}>
          {tag}
          {!disabled && (
            <button type="button" aria-label={`Remove ${tag}`} onClick={() => onChange?.(value.filter((_, j) => j !== i))}>
              <X size={11} />
            </button>
          )}
        </span>
      ))}
      {!disabled && (
        <input
          className="tags-input"
          value={draft}
          placeholder={value.length ? "" : placeholder}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if ((e.key === "Enter" || e.key === ",") && draft.trim()) {
              e.preventDefault();
              add(draft);
            } else if (e.key === "Backspace" && !draft && value.length) {
              onChange?.(value.slice(0, -1));
            }
          }}
          onBlur={() => draft.trim() && add(draft)}
          onPaste={(e) => {
            const text = e.clipboardData.getData("text");
            if (/[,\n]/.test(text)) {
              e.preventDefault();
              add(text);
            }
          }}
        />
      )}
    </div>
  );
}

export function Field({ label, hint, error, required, children, aside, htmlFor, className = "" }) {
  return (
    <div className={`sfield ${className}`}>
      {(label || aside) && (
        <div className="sfield-head">
          {label && (
            <label className="label" htmlFor={htmlFor}>
              {label}
              {required && <span className="req-star"> *</span>}
            </label>
          )}
          {aside && <span className="sfield-aside">{aside}</span>}
        </div>
      )}
      {children}
      {error ? <p className="hint field-err">{error}</p> : hint ? <p className="hint">{hint}</p> : null}
    </div>
  );
}

export function Modal({ open, title, subtitle, onClose, children, footer, width = 560, dismissible = true, autoFocus = true }) {
  const ref = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const first = autoFocus && ref.current?.querySelector("input, textarea, select, button:not(.modal-x)");
    (first || ref.current)?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === "Escape" && dismissible && closeRef.current?.();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, dismissible]);

  if (!open) return null;
  return createPortal(
    <div className="modal-layer">
      <div className="modal-scrim" onClick={dismissible ? onClose : undefined} />
      <div ref={ref} tabIndex={-1} className="modal" role="dialog" aria-modal="true" aria-label={title} style={{ width: `min(${width}px, calc(100vw - 32px))` }}>
        <div className="modal-head">
          <div style={{ minWidth: 0, flex: 1 }}>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          {dismissible && (
            <button type="button" className="btn btn-ghost btn-icon btn-sm modal-x" onClick={onClose} aria-label="Close">
              <X size={15} />
            </button>
          )}
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>,
    document.body
  );
}

export function Confirm({ open, title, body, confirmLabel = "Confirm", danger, busy, onConfirm, onClose }) {
  return (
    <Modal
      open={open}
      title={title}
      onClose={onClose}
      width={440}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button className={`btn ${danger ? "btn-danger-solid" : "btn-primary"}`} onClick={onConfirm} disabled={busy}>
            {busy ? "Working…" : confirmLabel}
          </button>
        </>
      }
    >
      <div className="confirm-body">
        {danger && <span className="confirm-icon"><Alert size={18} /></span>}
        <div>{body}</div>
      </div>
    </Modal>
  );
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          type="button"
          aria-selected={value === t.id}
          className={`tab ${value === t.id ? "on" : ""}`}
          onClick={() => onChange(t.id)}
        >
          {t.icon}
          {t.label}
          {t.badge ? <span className={`tab-badge ${t.badgeTone || ""}`}>{t.badge}</span> : null}
        </button>
      ))}
    </div>
  );
}

export function SaveBar({ dirty, saving, onSave, onDiscard, message = "You have unsaved changes", disabled }) {
  return createPortal(
    <div className={`savebar ${dirty ? "show" : ""}`} aria-hidden={!dirty}>
      <span className="savebar-dot" />
      <span className="savebar-text">{message}</span>
      <span className="grow" />
      <button className="btn btn-ghost btn-sm savebar-ghost" onClick={onDiscard} disabled={saving}>Discard</button>
      <button className="btn btn-primary btn-sm" onClick={onSave} disabled={saving || disabled}>
        {saving ? "Saving…" : "Save changes"}
      </button>
    </div>,
    document.body
  );
}

export function PageHeader({ title, subtitle, actions, eyebrow, back }) {
  return (
    <header className="phead">
      <div className="phead-text">
        {back}
        {eyebrow && <div className="phead-eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div className="phead-actions">{actions}</div>}
    </header>
  );
}

export function Empty({ icon, title, children, action }) {
  return (
    <div className="empty2">
      {icon && <div className="empty2-icon">{icon}</div>}
      <h4>{title}</h4>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function Badge({ tone = "", children, dot }) {
  return (
    <span className={`badge ${tone}`}>
      {dot && <span className="badge-dot" />}
      {children}
    </span>
  );
}

export function Skeleton({ h = 16, w = "100%", r }) {
  return <div className="skeleton" style={{ height: h, width: w, borderRadius: r }} />;
}

export function useFieldId() {
  return useId();
}

export function Avatar({ name = "", email = "", size = 30, tone }) {
  const text = (name || email || "?")
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
  return (
    <span className={`avatar2 ${tone || ""}`} style={{ width: size, height: size, fontSize: size * 0.38 }}>
      {text}
    </span>
  );
}

export function PasswordInput({ value, onChange, autoComplete = "current-password", invalid, placeholder, id }) {
  const [show, setShow] = useState(false);
  return (
    <div className="pw-wrap">
      <input
        id={id}
        className={`input ${invalid ? "err" : ""}`}
        type={show ? "text" : "password"}
        autoComplete={autoComplete}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        type="button"
        className={`btn btn-ghost btn-icon btn-sm pw-eye ${show ? "on" : ""}`}
        onClick={() => setShow((v) => !v)}
        aria-label={show ? "Hide password" : "Show password"}
        aria-pressed={show}
        title={show ? "Hide password" : "Show password"}
      >
        <Eye size={15} />
      </button>
    </div>
  );
}

export function FieldActions({ dirty, saving, onSave, onRevert, label = "this change" }) {
  if (!dirty) return null;
  return (
    <span className="fact" role="group" aria-label={`Unsaved: ${label}`}>
      <button type="button" className="fact-btn ok" onClick={onSave} disabled={saving}
        title={`Save ${label}`} aria-label={`Save ${label}`}>
        {saving ? <span className="fact-spin" /> : <CheckIcon />}
      </button>
      <button type="button" className="fact-btn no" onClick={onRevert} disabled={saving}
        title={`Undo ${label}`} aria-label={`Undo ${label}`}>
        <X size={12} />
      </button>
    </span>
  );
}

function CheckIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="m5 12.5 4.5 4.5L19 7.5" />
    </svg>
  );
}

export function AutoTextarea({ value, onChange, minRows = 1, className = "", ...rest }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight + 2}px`;
  }, [value]);
  return (
    <textarea
      ref={ref}
      rows={minRows}
      className={`input autogrow ${className}`}
      value={value ?? ""}
      onChange={onChange}
      {...rest}
    />
  );
}

const SECRET_MASK = "••••••••••••";

export function SecretInput({ id, value, onChange, hasValue, reveal, clearValue, disabled }) {
  const [stored, setStored] = useState(null);
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const cleared = value === clearValue;
  const masked = hasValue && !cleared && value === "" && stored === null;

  const typed = useRef(null);

  useEffect(() => {
    if (value === "" && typed.current !== null && typed.current !== stored) setStored(null);
    if (value === "") typed.current = null;
  }, [value]);

  const load = async () => {
    if (stored !== null || !hasValue || !reveal) return;
    setBusy(true);
    setError("");
    try {
      setStored((await reveal()).value ?? "");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const shown = cleared ? "" : value !== "" ? value : stored !== null ? stored : masked ? SECRET_MASK : "";

  const change = (text) => {
    if (masked) text = text.replaceAll("•", "");
    typed.current = text;
    if (stored !== null && text === stored) return onChange("");
    if (text === "" && hasValue) return onChange(clearValue);
    onChange(text);
  };

  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div className="pw-wrap">
        <input
          id={id}
          className="input mono"
          type={show && !masked ? "text" : "password"}
          autoComplete="off"
          value={shown}
          disabled={disabled}
          readOnly={busy}
          placeholder={cleared ? "will be cleared when you save" : hasValue ? "" : "not set"}
          onFocus={(e) => { if (masked && reveal) load(); else if (masked) e.target.select(); }}
          onChange={(e) => change(e.target.value)}
        />
        <button
          type="button"
          className={`btn btn-ghost btn-icon btn-sm pw-eye ${show ? "on" : ""}`}
          disabled={busy || (masked && !reveal)}
          onClick={async () => { if (!show) await load(); setShow((v) => !v); }}
          aria-label={show ? "Hide value" : "Show value"}
          title={masked && !reveal ? "Needs the Reveal secrets permission" : show ? "Hide" : "Show"}
        >
          <Eye size={14} />
        </button>
      </div>
      {error && <p className="hint field-err">{error}</p>}
    </div>
  );
}
