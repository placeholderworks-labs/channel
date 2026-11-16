import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Bot, Check, Eye, Lock, Shield, Wrench } from "../components/Icons";
import { AppFooter } from "../components/Shell";
import { Field } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useToast } from "../lib/toast";
import { Facets, Wordmark } from "../components/Brand";

function resetToken() {
  const params = new URLSearchParams(window.location.search);
  return window.location.pathname.replace(/\/+$/, "").endsWith("/reset") ? params.get("token") || "" : "";
}

export default function Login() {
  const [token] = useState(resetToken);
  const [mode, setMode] = useState(token ? "reset" : "signin");
  const backToSignIn = () => {
    window.history.replaceState(null, "", "/dashboard/");
    setMode("signin");
  };

  return (
    <div className="auth">
      <section className="auth-art" aria-hidden="true">
        <Facets className="auth-facets" />
        <div className="auth-brand"><Wordmark className="on-dark" /></div>

        <div className="auth-copy">
          <div className="auth-eyebrow">Voice Studio</div>
          <h1>Voice agents that make it to production.</h1>
          <p>
            Design, test and run the voice agents PlaceholderWorks ships to production: prompts,
            tools, guardrails and channels, all managed from one place.
          </p>
          <div className="auth-points">
            <div className="auth-point"><i><Bot size={14} /></i>Create an agent and put it on a phone line or the website in minutes.</div>
            <div className="auth-point"><i><Wrench size={14} /></i>Give each agent exactly the tools it needs, built-in or your own APIs.</div>
            <div className="auth-point"><i><Shield size={14} /></i>Guardrails, versioning and role-based access for every change.</div>
          </div>
        </div>

        <Wave />
        <div className="auth-foot">Internal tool · PlaceholderWorks Voice Studio</div>
      </section>

      <section className="auth-panel">
        <AppFooter className="auth-panel-foot" />
        {mode === "signin" ? (
          <SignIn onForgot={() => setMode("forgot")} />
        ) : mode === "reset" ? (
          <ResetPassword token={token} onDone={backToSignIn} onAskAgain={() => { backToSignIn(); setMode("forgot"); }} />
        ) : (
          <Forgot onBack={backToSignIn} />
        )}
      </section>
    </div>
  );
}

function CardLogo() {
  return <Wordmark className="auth-card-logo" />;
}

function Wave() {
  const bars = useMemo(
    () => Array.from({ length: 64 }, (_, i) => ({
      h: 18 + Math.abs(Math.sin(i * 0.55) * 34) + (i % 5) * 2,
      d: (i % 16) * 0.07,
    })),
    []
  );
  return (
    <div className="auth-wave">
      {bars.map((b, i) => (
        <span key={i} style={{ height: b.h, animationDelay: `${b.d}s` }} />
      ))}
    </div>
  );
}

function SignIn({ onForgot }) {
  const { startSignIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [step, setStep] = useState(null);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setStep(await startSignIn(email.trim(), password));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (step) {
    return <CodeStep step={step} onBack={() => { setStep(null); setPassword(""); }} />;
  }

  return (
    <div className="auth-card">
      <CardLogo />
      <h2>Welcome back</h2>
      <p className="lead">Sign in with your PlaceholderWorks email to open Voice Studio.</p>
      <form className="auth-form" onSubmit={submit}>
        <Field label="Work email" htmlFor="login-email">
          <input id="login-email" className="input" type="email" autoComplete="username" autoFocus
            placeholder="name@placeholderworks.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </Field>
        <Field
          label="Password"
          htmlFor="login-pw"
          aside={<button type="button" className="auth-link" onClick={onForgot}>Forgot password?</button>}
        >
          <div className="pw-wrap">
            <input id="login-pw" className="input" type={show ? "text" : "password"} autoComplete="current-password"
              value={password} onChange={(e) => setPassword(e.target.value)} required />
            <button type="button" className="btn btn-ghost btn-icon btn-sm pw-eye"
              onClick={() => setShow((v) => !v)} aria-label={show ? "Hide password" : "Show password"}>
              <Eye size={15} />
            </button>
          </div>
        </Field>
        {error && (
          <div className="notice halt"><Alert size={15} /><span>{error}</span></div>
        )}
        <button className="btn btn-primary btn-block" type="submit" disabled={busy || !email || !password}>
          {busy ? "Checking…" : "Continue"}
        </button>
        <p className="hint" style={{ textAlign: "center", margin: 0 }}>
          No account? Ask a Voice Studio admin to invite you.
        </p>
      </form>
    </div>
  );
}

const CODE_LENGTH = 6;

function CodeStep({ step, onBack }) {
  const { finishSignIn } = useAuth();
  const toast = useToast();
  const [digits, setDigits] = useState(() => Array(CODE_LENGTH).fill(""));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sentTo, setSentTo] = useState(step.sentTo);
  const [wait, setWait] = useState(step.resendIn || 30);
  const boxes = useRef([]);

  useEffect(() => { boxes.current[0]?.focus(); }, []);
  useEffect(() => {
    if (wait <= 0) return undefined;
    const id = setTimeout(() => setWait((w) => w - 1), 1000);
    return () => clearTimeout(id);
  }, [wait]);

  const verify = async (code) => {
    setBusy(true);
    setError("");
    try {
      await finishSignIn(step.challenge, code);
    } catch (e) {
      setError(e.message);
      setDigits(Array(CODE_LENGTH).fill(""));
      boxes.current[0]?.focus();
      setBusy(false);
    }
  };

  const fill = (index, text) => {
    const clean = text.replace(/\D/g, "");
    if (!clean && text) return;
    const next = [...digits];
    if (clean.length > 1) {
      clean.slice(0, CODE_LENGTH - index).split("").forEach((d, i) => { next[index + i] = d; });
    } else {
      next[index] = clean;
    }
    setDigits(next);
    const filled = next.findIndex((d) => !d);
    boxes.current[filled === -1 ? CODE_LENGTH - 1 : Math.min(filled, CODE_LENGTH - 1)]?.focus();
    if (next.every(Boolean)) verify(next.join(""));
  };

  const onKey = (index, event) => {
    if (event.key === "Backspace" && !digits[index] && index > 0) boxes.current[index - 1]?.focus();
    if (event.key === "ArrowLeft" && index > 0) boxes.current[index - 1]?.focus();
    if (event.key === "ArrowRight" && index < CODE_LENGTH - 1) boxes.current[index + 1]?.focus();
  };

  const resend = async () => {
    setError("");
    try {
      const r = await api.resendLogin(step.challenge);
      setSentTo(r.sentTo);
      setWait(r.resendIn || 30);
      setDigits(Array(CODE_LENGTH).fill(""));
      boxes.current[0]?.focus();
      toast.ok("A new code is on its way");
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="auth-card">
      <span className="otp-badge"><Lock size={18} /></span>
      <h2>Check your email</h2>
      <p className="lead">We sent a 6-digit code to <strong>{sentTo}</strong>. It expires in {Math.round((step.expiresIn || 300) / 60)} minutes.</p>
      <form className="auth-form" onSubmit={(e) => { e.preventDefault(); verify(digits.join("")); }}>
        <div className="otp-boxes" role="group" aria-label="Sign-in code">
          {digits.map((d, i) => (
            <input key={i} ref={(el) => { boxes.current[i] = el; }} className="otp-box" inputMode="numeric"
              autoComplete={i === 0 ? "one-time-code" : "off"} maxLength={i === 0 ? CODE_LENGTH : 1} value={d}
              aria-label={`Digit ${i + 1}`} disabled={busy}
              onChange={(e) => fill(i, e.target.value)} onKeyDown={(e) => onKey(i, e)}
              onFocus={(e) => e.target.select()} />
          ))}
        </div>
        {error && <div className="notice halt"><Alert size={15} /><span>{error}</span></div>}
        <button className="btn btn-primary btn-block" type="submit" disabled={busy || digits.some((d) => !d)}>
          {busy ? "Verifying…" : "Verify and sign in"}
        </button>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <button type="button" className="auth-link" onClick={onBack}>Use a different account</button>
          <button type="button" className="auth-link" onClick={resend} disabled={wait > 0}>
            {wait > 0 ? `Resend code in ${wait}s` : "Resend code"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Forgot({ onBack }) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.forgotPassword(email.trim());
      setSent(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-card">
      <h2>Reset your password</h2>
      <p className="lead">We'll email a link to set a new password. Your current password keeps working until you use it.</p>
      {sent ? (
        <div className="stack-lg">
          <div className="notice ok">
            <Check size={15} />
            <span>If <strong>{email}</strong> has an account, a reset link is on its way. It works once, for 15 minutes.</span>
          </div>
          <button className="btn btn-primary btn-block" onClick={onBack}>Back to sign in</button>
        </div>
      ) : (
        <form className="auth-form" onSubmit={submit}>
          <Field label="Work email">
            <input className="input" type="email" autoFocus value={email} onChange={(e) => setEmail(e.target.value)} required />
          </Field>
          {error && <div className="notice halt"><Alert size={15} /><span>{error}</span></div>}
          <button className="btn btn-primary btn-block" type="submit" disabled={busy || !email}>
            {busy ? "Sending…" : "Email me a reset link"}
          </button>
          <button type="button" className="auth-link" style={{ justifySelf: "center" }} onClick={onBack}>
            Back to sign in
          </button>
        </form>
      )}
    </div>
  );
}

function ResetPassword({ token, onDone, onAskAgain }) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const tooShort = password.length > 0 && password.length < 8;
  const mismatch = confirm.length > 0 && confirm !== password;

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.resetPassword(token, password);
      setDone(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <div className="auth-card">
        <span className="otp-badge"><Check size={18} /></span>
        <h2>Password changed</h2>
        <p className="lead">Sign in with your new password. You'll get a code by email as usual.</p>
        <button className="btn btn-primary btn-block" onClick={onDone}>Go to sign in</button>
      </div>
    );
  }

  return (
    <div className="auth-card">
      <span className="otp-badge"><Lock size={18} /></span>
      <h2>Set a new password</h2>
      <p className="lead">At least 8 characters. Your old password stops working once you save this.</p>
      <form className="auth-form" onSubmit={submit}>
        <Field label="New password" error={tooShort ? "At least 8 characters" : ""}>
          <div className="pw-wrap">
            <input className="input" type={show ? "text" : "password"} autoComplete="new-password" autoFocus
              value={password} onChange={(e) => setPassword(e.target.value)} required />
            <button type="button" className="btn btn-ghost btn-icon btn-sm pw-eye"
              onClick={() => setShow((v) => !v)} aria-label={show ? "Hide password" : "Show password"}>
              <Eye size={15} />
            </button>
          </div>
        </Field>
        <Field label="Confirm new password" error={mismatch ? "Doesn't match" : ""}>
          <input className="input" type={show ? "text" : "password"} autoComplete="new-password"
            value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
        </Field>
        {error && (
          <div className="notice halt"><Alert size={15} /><span>{error}</span></div>
        )}
        <button className="btn btn-primary btn-block" type="submit"
          disabled={busy || password.length < 8 || confirm !== password}>
          {busy ? "Saving…" : "Save new password"}
        </button>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <button type="button" className="auth-link" onClick={onDone}>Back to sign in</button>
          <button type="button" className="auth-link" onClick={onAskAgain}>Email me a new link</button>
        </div>
      </form>
    </div>
  );
}
