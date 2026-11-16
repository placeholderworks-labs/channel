const INFO = new TextEncoder().encode("pw-voice-studio/v1");
let session = null;
let pending = null;

const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
const unb64 = (text) => Uint8Array.from(atob(text), (c) => c.charCodeAt(0));

export function available() {
  return typeof crypto !== "undefined" && !!crypto.subtle;
}

async function handshake(base) {
  const pair = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, false, ["deriveBits"]);
  const publicKey = await crypto.subtle.exportKey("raw", pair.publicKey);
  const response = await fetch(`${base}/session-key`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ publicKey: b64(publicKey) }),
  });
  if (!response.ok) throw new Error(`secure session refused (${response.status})`);
  const answer = await response.json();
  const peer = await crypto.subtle.importKey("raw", unb64(answer.publicKey), { name: "ECDH", namedCurve: "P-256" }, false, []);
  const bits = await crypto.subtle.deriveBits({ name: "ECDH", public: peer }, pair.privateKey, 256);
  const hkdf = await crypto.subtle.importKey("raw", bits, "HKDF", false, ["deriveKey"]);
  const key = await crypto.subtle.deriveKey(
    { name: "HKDF", hash: "SHA-256", salt: unb64(answer.salt), info: INFO },
    hkdf,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"]
  );
  return { kid: answer.kid, key };
}

export async function ensureSession(base) {
  if (session) return session;
  if (!pending) {
    pending = handshake(base)
      .then((s) => (session = s))
      .finally(() => (pending = null));
  }
  return pending;
}

export function dropSession() {
  session = null;
}

const aad = (method, path) => new TextEncoder().encode(`${method.toUpperCase()} ${decodeURIComponent(path.split("?")[0])}`);

export async function seal(s, method, path, body) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const plain = new TextEncoder().encode(JSON.stringify({ ts: Date.now(), body }));
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv, additionalData: aad(method, path) }, s.key, plain);
  return { iv: b64(iv), ct: b64(ct) };
}

export async function open(s, method, path, envelope) {
  const plain = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: unb64(envelope.iv), additionalData: aad(method, path) },
    s.key,
    unb64(envelope.ct)
  );
  return new TextDecoder().decode(plain);
}
