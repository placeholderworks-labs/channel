import * as secure from "./secure";

const TOKEN_KEY = "voicebot.session";
const BASE = "/api/admin";

let onUnauthorized = () => {};

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
  }
}

export class ApiError extends Error {
  constructor(message, status, errors = []) {
    super(message);
    this.status = status;
    this.errors = errors;
  }
}

async function request(path, { method = "GET", body, auth = true } = {}, retried = false) {
  if (!secure.available()) {
    throw new ApiError("This browser can't open a secure session. Use HTTPS or localhost.", 0);
  }
  let session;
  try {
    session = await secure.ensureSession(BASE);
  } catch {
    throw new ApiError("Can't reach the server. Check that it's running.", 0);
  }

  const url = `${BASE}${path}`;
  const headers = { "X-Enc-Kid": session.kid };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(await secure.seal(session, method, url, body)),
    });
  } catch {
    throw new ApiError("Can't reach the server. Check that it's running.", 0);
  }

  if (response.status === 409 && !retried && response.headers.get("x-enc") !== "1") {
    const peek = await response.clone().json().catch(() => null);
    if (peek?.detail === "encryption key expired") {
      secure.dropSession();
      return request(path, { method, body, auth }, true);
    }
  }

  if (response.status === 401 && auth) {
    setToken("");
    onUnauthorized();
    throw new ApiError("Your session expired. Sign in again.", 401);
  }

  let text = await response.text();
  if (text && response.headers.get("x-enc") === "1") {
    try {
      text = await secure.open(session, method, url, JSON.parse(text));
    } catch {
      throw new ApiError("The server's reply could not be decrypted. Reload the page.", response.status);
    }
  }
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { detail: text };
    }
  }

  if (!response.ok) {
    const detail = payload?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : typeof detail?.message === "string"
        ? detail.message
        : `Request failed (${response.status})`;
    throw new ApiError(message, response.status, detail?.errors || []);
  }

  return payload;
}

export const api = {
  login: (email, password) =>
    request("/login", { method: "POST", body: { email, password }, auth: false }),
  verifyLogin: (challenge, code) =>
    request("/login/verify", { method: "POST", body: { challenge, code }, auth: false }),
  resendLogin: (challenge) =>
    request("/login/resend", { method: "POST", body: { challenge }, auth: false }),
  me: () => request("/me"),
  status: () => request("/status"),

  settings: () => request("/settings"),
  saveSettings: (values, apply = true) =>
    request("/settings", { method: "PUT", body: { values, apply } }),
  applySettings: () => request("/settings/apply", { method: "POST" }),
  settingsHistory: (limit = 40) => request(`/settings/history?limit=${limit}`),
  resetSettings: (keys) => request("/settings/reset", { method: "POST", body: { keys } }),
  playground: () => request("/playground"),

  brainSettings: () => request("/brain/settings"),
  saveBrainSettings: (values) =>
    request("/brain/settings", { method: "PUT", body: { values, apply: true } }),
  resetBrainSettings: (keys) =>
    request("/brain/settings/reset", { method: "POST", body: { keys } }),


  revealSetting: (key) => request(`/settings/${encodeURIComponent(key)}/reveal`),
  revealBrainSetting: (key) => request(`/brain/settings/${encodeURIComponent(key)}/reveal`),

  dataTables: () => request("/data"),
  dataRows: (table, { limit = 50, offset = 0, q = "" } = {}) =>
    request(`/data/${table}?limit=${limit}&offset=${offset}&q=${encodeURIComponent(q)}`),
  dataRow: (table, id) => request(`/data/${table}/${id}`),
  deleteDataRow: (table, id) => request(`/data/${table}/${id}`, { method: "DELETE" }),
  purgeDataTable: (table, olderThanDays = 0) =>
    request(`/data/${table}/purge`, { method: "POST", body: { olderThanDays } }),
  purgeAllData: (olderThanDays = 0) =>
    request("/data/purge", { method: "POST", body: { olderThanDays } }),

  placeCall: (payload) => request("/calls", { method: "POST", body: payload }),
  calls: (limit = 50) => request(`/calls?limit=${limit}`),

  activeCalls: (did = "") =>
    request(`/calls/active${did ? `?did=${encodeURIComponent(did)}` : ""}`),
  callDids: () => request("/calls/dids"),
  callTranscript: (id) => request(`/calls/${id}/transcript`),
  callBrief: (id) => request(`/calls/${id}/summary`, { method: "POST" }),


  qms: () => request("/qms"),
  qmsForAgent: (agent) => request(`/qms/for-agent/${encodeURIComponent(agent)}`),
  qmsCatalog: () => request("/qms/catalog"),
  connectIntake: (id, payload) => request(`/qms/intakes/${id}/connection`, { method: "PUT", body: payload }),
  releaseIntake: (id) => request(`/qms/intakes/${id}/release`, { method: "POST" }),
  globals: () => request("/globals"),
  saveGlobals: (variables) => request("/globals", { method: "PUT", body: { variables } }),
  createIntake: (payload) => request("/qms/intakes", { method: "POST", body: payload }),
  updateIntake: (id, payload) => request(`/qms/intakes/${id}`, { method: "PUT", body: payload }),
  deleteIntake: (id) => request(`/qms/intakes/${id}`, { method: "DELETE" }),
  newIntakeToken: (id) => request(`/qms/intakes/${id}/token`, { method: "POST" }),
  createTestRecord: (payload) => request("/test-records", { method: "POST", body: payload }),
  history: ({ limit = 200, status = "", q = "", agent = "", source = "" } = {}) =>
    request(
      `/history?limit=${limit}&status=${encodeURIComponent(status)}&q=${encodeURIComponent(q)}` +
        `&agent=${encodeURIComponent(agent)}&source=${encodeURIComponent(source)}`
    ),
  ingestionEvent: (id) => request(`/ingestion/${id}`),
  cancelIngestion: (id) => request(`/ingestion/${id}/cancel`, { method: "POST" }),
  retryIngestion: (id) => request(`/ingestion/${id}/retry`, { method: "POST" }),
  callDetail: (id) => request(`/history/${id}/call`),
  callSummary: (id, refresh = false) => request(`/history/${id}/summary${refresh ? "?refresh=true" : ""}`, { method: "POST" }),

  users: () => request("/users"),
  clients: () => request("/clients"),
  createClient: (payload) => request("/clients", { method: "POST", body: payload }),
  updateClient: (id, payload) => request(`/clients/${id}`, { method: "PATCH", body: payload }),
  deleteClient: (id) => request(`/clients/${id}`, { method: "DELETE" }),
  addClientMember: (id, payload) => request(`/clients/${id}/members`, { method: "POST", body: payload }),
  addUser: (payload) => request("/users", { method: "POST", body: payload }),
  updateUser: (id, payload) => request(`/users/${id}`, { method: "PATCH", body: payload }),
  resetUserPassword: (id) => request(`/users/${id}/reset-password`, { method: "POST" }),
  deleteUser: (id) => request(`/users/${id}`, { method: "DELETE" }),
  changePassword: (currentPassword, newPassword) =>
    request("/password", { method: "POST", body: { currentPassword, newPassword } }),
  resetPassword: (token, newPassword) =>
    request("/password/reset", { method: "POST", body: { token, newPassword }, auth: false }),
  forgotPassword: (email) =>
    request("/password/forgot", { method: "POST", body: { email }, auth: false }),

  roles: () => request("/roles"),
  requestAccess: (permission, page, note = "") => request("/access-requests", { method: "POST", body: { permission, page, note } }),
  myAccessRequests: () => request("/access-requests/mine"),
  accessRequests: () => request("/access-requests"),
  resolveAccessRequest: (id, status) => request(`/access-requests/${id}/resolve`, { method: "POST", body: { status } }),
  createRole: (payload) => request("/roles", { method: "POST", body: payload }),
  updateRole: (name, payload) =>
    request(`/roles/${encodeURIComponent(name)}`, { method: "PUT", body: payload }),
  deleteRole: (name) => request(`/roles/${encodeURIComponent(name)}`, { method: "DELETE" }),

  usecases: () => request("/usecases"),
  usecase: (slug) => request(`/usecases/${slug}`),
  createUsecase: (payload) => request("/usecases", { method: "POST", body: payload }),
  updateUsecase: (slug, payload) => request(`/usecases/${slug}`, { method: "PUT", body: payload }),
  deleteUsecase: (slug) => request(`/usecases/${slug}`, { method: "DELETE" }),
  duplicateUsecase: (slug, payload) =>
    request(`/usecases/${slug}/duplicate`, { method: "POST", body: payload }),
  usecaseVersions: (slug) => request(`/usecases/${slug}/versions`),
  rollbackUsecase: (slug, version) =>
    request(`/usecases/${slug}/rollback`, { method: "POST", body: { version } }),
  previewUsecase: (slug, language = "hindi") =>
    request(`/usecases/${slug}/preview?language=${language}`),
  setUsecaseDefaults: (defaults) =>
    request("/usecases/defaults", { method: "PUT", body: defaults }),
  llmOptions: () => request("/llm/options"),
  suggestRefusals: (payload) => request("/usecases/suggest-refusals", { method: "POST", body: payload }),
  suggestGreetings: (payload) => request("/usecases/suggest-greetings", { method: "POST", body: payload }),
  transliterate: (text) => request("/transliterate", { method: "POST", body: { text } }),

  guardrails: () => request("/guardrails"),
  createGuardrail: (payload) => request("/guardrails", { method: "POST", body: payload }),
  updateGuardrail: (id, payload) => request(`/guardrails/${id}`, { method: "PUT", body: payload }),
  deleteGuardrail: (id) => request(`/guardrails/${id}`, { method: "DELETE" }),

  tools: () => request("/tools"),
  customTool: (name) => request(`/tools/custom/${name}`),
  createTool: (payload) => request("/tools/custom", { method: "POST", body: payload }),
  updateTool: (name, payload) => request(`/tools/custom/${name}`, { method: "PUT", body: payload }),
  deleteTool: (name) => request(`/tools/custom/${name}`, { method: "DELETE" }),
  testTool: (name, args, tool) => request(`/tools/custom/${name}/test`, { method: "POST", body: { args, tool } }),
  syncMcp: (name) => request(`/tools/custom/${name}/sync`, { method: "POST" }),
  discoverMcp: (payload) => request("/tools/mcp/discover", { method: "POST", body: payload }),
  switchBuiltinTool: (name, enabled) => request(`/tools/builtin/${name}`, { method: "PUT", body: { enabled } }),
};

export async function logCalls() {
  const r = await fetch(`/internal/logs/calls?token=${encodeURIComponent(getToken())}`);
  if (!r.ok) throw new ApiError(`Could not load calls (${r.status})`, r.status);
  return r.json();
}

export async function logCall(callId) {
  const r = await fetch(`/internal/logs/calls/${encodeURIComponent(callId)}?token=${encodeURIComponent(getToken())}`);
  if (!r.ok) throw new ApiError(`Could not load that call (${r.status})`, r.status);
  return r.json();
}

export function logStreamUrl(lines = 300) {
  return `/internal/logs/stream?lines=${lines}&token=${encodeURIComponent(getToken())}`;
}
