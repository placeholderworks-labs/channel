import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useTheme } from "../lib/theme";
import { useToast } from "../lib/toast";
import { Wordmark } from "./Brand";
import { Building } from "./Icons";
import {
  ArrowLeft,
  Bot,
  Chevron,
  Database,
  FileText,
  Dashboard,
  Headset,
  PhoneCall,
  Mic2,
  Gear,
  Inbox,
  History,
  Lock,
  LogOut,
  Menu,
  Moon,
  Shield,
  Sun,
  Terminal,
  Users,
  Wrench,
  Key,
} from "./Icons";
import { Avatar, Field, Modal, PasswordInput } from "./ui";

const NAV = [
  {
    items: [{ to: "/", label: "Overview", icon: Dashboard, end: true, perm: "overview.view" }],
  },
  {
    section: "Build",
    items: [
      { to: "/agents", label: "Agents", icon: Bot, perm: "usecases.view" },
      { to: "/tools", label: "Tools", icon: Wrench, perm: "tools.view" },
      { to: "/guardrails", label: "Guardrails", icon: Shield, perm: "usecases.view" },
    ],
  },
  {
    section: "Test",
    items: [
      { to: "/playground/webrtc", label: "Browser test", icon: Mic2, perm: "calls.place" },
      { to: "/playground/call", label: "Phone test", icon: PhoneCall, perm: "calls.place" },
    ],
  },
  {
    section: "Operate",
    items: [
      { to: "/live-calls", label: "Live calls", icon: Headset, perm: "calls.live.view" },
      { to: "/qms", label: "QMS", icon: Inbox, perm: "ingestion.view" },
      { to: "/history", label: "History", icon: History, perm: "ingestion.view" },
      { to: "/database", label: "Database", icon: Database, perm: "data.view" },
      { to: "/logs", label: "Logs", icon: Terminal, perm: "logs.view" },
    ],
  },
  {
    section: "Admin",
    items: [
      { to: "/settings", label: "Settings", icon: Gear, perm: "settings.view" },
      { to: "/clients", label: "Clients", icon: Building, perm: "team.view" },
      { to: "/roles", label: "Roles & access", icon: Key, perm: "team.view" },
      { to: "/docs", label: "Docs", icon: FileText },
    ],
  },
];

export default function Shell({ children, status }) {
  const { user, can } = useAuth();
  const [open, setOpen] = useState(false);
  const location = useLocation();

  useEffect(() => setOpen(false), [location.pathname]);

  return (
    <div className="shell">
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <Link to="/" className="brand2">
          <Wordmark className="on-dark" />
          <span className="brand2-tag">{user?.orgName ? `Voice Studio · ${user.orgName}` : "Voice Studio"}</span>
        </Link>

        <nav className="nav">
          {NAV.map((group, i) => {
            const items = user?.orgId ? group.items.filter((item) => !item.perm || can(item.perm)) : group.items;
            if (!items.length) return null;
            return (
              <div key={group.section || i}>
                {group.section && <div className="nav-section">{group.section}</div>}
                {items.map((item) => {
                  const locked = item.perm && !can(item.perm);
                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.end}
                      className={({ isActive }) => `nav-item ${isActive ? "on" : ""} ${locked ? "locked" : ""}`}
                      title={locked ? "You don't have access. Open to request it." : undefined}
                    >
                      <item.icon size={16} />
                      {item.label}
                      {locked && <Lock size={12} className="nav-lock" />}
                    </NavLink>
                  );
                })}
              </div>
            );
          })}
        </nav>

        <UserMenu user={user} />
      </aside>

      {open && <button onClick={() => setOpen(false)} aria-label="Close menu" className="scrim" />}

      <div className="main">
        <header className="topbar">
          <button className="btn btn-ghost btn-icon mobile-only" onClick={() => setOpen((v) => !v)} aria-label="Menu">
            <Menu size={18} />
          </button>
          <Crumbs />
          <div className="grow" />
          <LineStatus status={status} />
          <ThemeButton />
        </header>
        <div className="main-body">{children}</div>
        <AppFooter />
      </div>
    </div>
  );
}

const SECTION_OF = Object.fromEntries(
  NAV.flatMap((g) => g.items.map((i) => [i.to, { section: g.section, label: i.label }]))
);

const NESTED = [
  { match: /^\/agents\/new$/, parent: "/agents", label: () => "New agent" },
  { match: /^\/agents\/([^/]+)$/, parent: "/agents", label: (m) => m[1] },
];

export function crumbsFor(pathname) {
  for (const n of NESTED) {
    const m = pathname.match(n.match);
    if (m) {
      const parent = SECTION_OF[n.parent];
      return { back: n.parent, crumbs: [parent.section, { to: n.parent, label: parent.label }, n.label(m)].filter(Boolean) };
    }
  }
  const own = SECTION_OF[pathname];
  if (!own) return { back: null, crumbs: [] };
  return { back: pathname === "/" ? null : "history", crumbs: [own.section, own.label].filter(Boolean) };
}

function Crumbs() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { back, crumbs } = crumbsFor(pathname);

  const goBack = () => {
    if (back && back !== "history") return navigate(back);
    if ((window.history.state?.idx ?? 0) > 0) return navigate(-1);
    return navigate("/");
  };

  return (
    <div className="crumbs">
      {back && (
        <button className="crumb-back" onClick={goBack} aria-label="Go back" title="Back">
          <ArrowLeft size={15} />
        </button>
      )}
      <nav aria-label="Breadcrumb" className="crumb-trail">
        {crumbs.map((c, i) => {
          const last = i === crumbs.length - 1;
          const label = typeof c === "string" ? c : c.label;
          return (
            <span key={i} className="row" style={{ gap: 6 }}>
              {i > 0 && <Chevron size={12} dir="right" />}
              {typeof c === "object" && !last ? (
                <Link to={c.to} className="crumb">{label}</Link>
              ) : (
                <span className={`crumb ${last ? "on" : ""}`}>{label}</span>
              )}
            </span>
          );
        })}
      </nav>
    </div>
  );
}

export function AppFooter({ className = "" }) {
  return (
    <footer className={`app-foot ${className}`}>
      <span>Built by <strong>PlaceholderWorks</strong></span>
      <span className="app-foot-sep" aria-hidden="true" />
      <span>© {new Date().getFullYear()} placeholderworks.com</span>
    </footer>
  );
}

function ThemeButton() {
  const { theme, toggle } = useTheme();
  return (
    <button className="btn btn-ghost btn-icon btn-sm" onClick={toggle} aria-label="Toggle theme"
      title={theme === "dark" ? "Light theme" : "Dark theme"}>
      <span key={theme} className="theme-icon">{theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}</span>
    </button>
  );
}

function UserMenu({ user }) {
  const { signOut } = useAuth();
  const { theme, toggle } = useTheme();
  const [menu, setMenu] = useState(false);
  const [pw, setPw] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!menu) return undefined;
    const onDoc = (e) => !ref.current?.contains(e.target) && setMenu(false);
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [menu]);

  return (
    <div className="sidebar-foot2" ref={ref} style={{ position: "relative" }}>
      {menu && (
        <div className="me-menu" role="menu">
          <button onClick={() => { setMenu(false); setPw(true); }}>
            <Lock size={15} /> Change password
          </button>
          <button onClick={toggle}>
            {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
            {theme === "dark" ? "Light theme" : "Dark theme"}
          </button>
          <hr />
          <button onClick={signOut}>
            <LogOut size={15} /> Sign out
          </button>
        </div>
      )}
      <button className="me" onClick={() => setMenu((v) => !v)} aria-haspopup="menu" aria-expanded={menu}>
        <Avatar name={user?.name} email={user?.email} size={32} tone={user?.role === "super_admin" ? "super" : ""} />
        <span style={{ minWidth: 0, flex: 1 }}>
          <span className="me-name ellipsis" style={{ display: "block" }}>{user?.name || user?.email}</span>
          <span className="me-role">{user?.roleLabel || user?.role}</span>
        </span>
      </button>
      <ChangePassword open={pw} onClose={() => setPw(false)} />
    </div>
  );
}

export function passwordScore(pw) {
  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score++;
  if (/\d/.test(pw) && /[^A-Za-z0-9]/.test(pw)) score++;
  return Math.min(score, 4);
}

export function ChangePassword({ open, onClose, forced }) {
  const toast = useToast();
  const { refresh } = useAuth();
  const [form, setForm] = useState({ current: "", next: "", again: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const mismatch = form.again && form.next !== form.again;
  const ok = form.current && form.next.length >= 8 && form.next === form.again;

  const submit = async (e) => {
    e?.preventDefault();
    if (!ok) return;
    setBusy(true);
    setError("");
    try {
      await api.changePassword(form.current, form.next);
      toast.ok("Password changed");
      setForm({ current: "", next: "", again: "" });
      await refresh().catch(() => {});
      onClose?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      dismissible={!forced}
      title={forced ? "Set your own password" : "Change password"}
      subtitle={forced ? "You signed in with a temporary password. Choose a new one to continue." : "At least 8 characters."}
      width={440}
      autoFocus={false}
      footer={
        <>
          {!forced && <button className="btn btn-ghost" onClick={onClose}>Cancel</button>}
          <button className="btn btn-primary" onClick={submit} disabled={!ok || busy}>
            {busy ? "Saving…" : "Update password"}
          </button>
        </>
      }
    >
      <form onSubmit={submit} className="stack-lg">
        <Field label={forced ? "Temporary password" : "Current password"}>
          <PasswordInput autoComplete="current-password" value={form.current}
            onChange={(v) => setForm({ ...form, current: v })} />
        </Field>
        <Field label="New password">
          <PasswordInput autoComplete="new-password" value={form.next}
            onChange={(v) => setForm({ ...form, next: v })} />
          <div className="pw-meter" data-score={passwordScore(form.next)}><span /><span /><span /><span /></div>
        </Field>
        <Field label="Repeat it" error={mismatch ? "Doesn't match" : ""}>
          <PasswordInput autoComplete="new-password" invalid={mismatch} value={form.again}
            onChange={(v) => setForm({ ...form, again: v })} />
        </Field>
        {error && <div className="notice halt"><span>{error}</span></div>}
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}

function LineStatus({ status }) {
  if (!status) return <span className="status-chip"><span className="lamp" />Connecting…</span>;

  const armed = (status.channels || []).filter((c) => c.enabled);
  const dialers = armed.filter((c) => c.dialer);
  const blocked = dialers.filter((c) => c.missing.length);
  const stack = status.stack || {};
  const stackReady = ["stt", "llm", "tts"].every((k) => stack[k]?.ready);

  let tone = "ok";
  let text = "All systems ready";
  if (!armed.length) [tone, text] = ["halt", "No channel armed"];
  else if (!stackReady) [tone, text] = ["halt", "Voice stack needs a key"];
  else if (blocked.length) [tone, text] = ["warn", `${blocked.length} dialer not ready`];

  return (
    <Link to="/" className={`status-chip ${tone}`} title={`${stack.stt?.provider} · ${stack.llm?.provider} · ${stack.tts?.provider}`}>
      <span className={`lamp ${tone === "ok" ? "on pulse" : tone}`} />
      {text}
      <span className="status-chip-sub desktop-only">{armed.length} channel{armed.length === 1 ? "" : "s"} live</span>
    </Link>
  );
}
