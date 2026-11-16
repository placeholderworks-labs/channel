import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes, useParams } from "react-router-dom";
import Shell, { ChangePassword } from "./components/Shell";
import ActiveCalls from "./pages/ActiveCalls";
import Call from "./pages/Call";
import CallData from "./pages/CallData";
import Docs from "./pages/Docs";
import Guardrails from "./pages/Guardrails";
import Roles from "./pages/Roles";
import Settings from "./pages/Settings";
import Tools from "./pages/Tools";
import UseCaseEditor from "./pages/UseCaseEditor";
import UseCases from "./pages/UseCases";
import History from "./pages/History";
import QMS from "./pages/QMS";
import Login from "./pages/Login";
import Logs from "./pages/Logs";
import Overview from "./pages/Overview";
import Team from "./pages/Team";
import Clients from "./pages/Clients";
import WebRTC from "./pages/WebRTC";
import { api } from "./lib/api";
import { useAuth } from "./lib/auth";
import RequestAccess from "./components/RequestAccess";

function Guard({ perm, title, children }) {
  const { can } = useAuth();
  return can(perm) ? children : <RequestAccess perm={perm} title={title} />;
}

export default function App() {
  const { user, checking } = useAuth();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setStatus(await api.status());
    } catch {
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!user) {
      setStatus(null);
      return;
    }
    reload();
    const id = setInterval(reload, 20000);
    return () => clearInterval(id);
  }, [user, reload]);

  if (checking) {
    return (
      <div style={{ display: "grid", placeItems: "center", minHeight: "100vh" }}>
        <div className="eyebrow">Loading the console…</div>
      </div>
    );
  }

  const resetLink = /\/reset\/?$/.test(window.location.pathname) && new URLSearchParams(window.location.search).has("token");
  if (!user || resetLink) return <Login />;

  return (
    <Shell status={status}>
      <ChangePassword open={!!user.mustChangePassword} forced />
      <Routes>
        <Route path="/" element={<Guard perm="overview.view" title="the Overview"><Overview status={status} reload={reload} loading={loading} /></Guard>} />
        <Route path="/agents" element={<Guard perm="usecases.view" title="Agents"><UseCases /></Guard>} />
        <Route path="/agents/new" element={<Guard perm="usecases.edit" title="creating agents"><UseCases startNew /></Guard>} />
        <Route path="/agents/:slug" element={<Guard perm="usecases.view" title="this agent"><UseCaseEditor /></Guard>} />
        <Route path="/usecases" element={<Navigate to="/agents" replace />} />
        <Route path="/usecases/new" element={<Navigate to="/agents/new" replace />} />
        <Route path="/usecases/:slug" element={<OldAgentLink />} />
        <Route path="/tools" element={<Guard perm="tools.view" title="Tools"><Tools /></Guard>} />
        <Route path="/guardrails" element={<Guard perm="usecases.view" title="Guardrails"><Guardrails /></Guard>} />
        <Route path="/live-calls" element={<Guard perm="calls.live.view" title="Live calls"><ActiveCalls /></Guard>} />
        <Route path="/qms" element={<Guard perm="ingestion.view" title="QMS"><QMS /></Guard>} />
        <Route path="/history" element={<Guard perm="ingestion.view" title="History"><History /></Guard>} />
        <Route path="/ingestion" element={<Navigate to="/qms" replace />} />
        <Route path="/playground/webrtc" element={<Guard perm="calls.place" title="the Browser test"><WebRTC status={status} /></Guard>} />
        <Route path="/playground/call" element={<Guard perm="calls.place" title="the Phone test"><Call status={status} reload={reload} /></Guard>} />
        <Route path="/settings" element={<Guard perm="settings.view" title="Settings"><Settings reload={reload} /></Guard>} />
        <Route path="/settings/raw" element={<Navigate to="/settings" replace />} />
        <Route path="/database" element={<Guard perm="data.view" title="the Database"><CallData /></Guard>} />
        <Route path="/call-data" element={<Navigate to="/database" replace />} />
        <Route path="/docs" element={<Docs />} />
        <Route path="/logs" element={<Guard perm="logs.view" title="Logs"><Logs /></Guard>} />
        <Route path="/clients" element={<Guard perm="team.view" title="Clients"><Clients /></Guard>} />
        <Route path="/team" element={<Guard perm="team.view" title="Team"><Team /></Guard>} />
        <Route path="/roles" element={<Guard perm="team.view" title="Roles & access"><Roles /></Guard>} />
        <Route path="/playground" element={<Navigate to="/playground/webrtc" replace />} />
        <Route path="/configuration" element={<Navigate to="/settings" replace />} />
        <Route path="/calls" element={<Navigate to="/playground/call" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  );
}

function OldAgentLink() {
  const { slug } = useParams();
  return <Navigate to={`/agents/${slug}`} replace />;
}
