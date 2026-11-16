import { useCallback, useEffect, useRef, useState } from "react";
import { MAX_RESULTS, mergeResult } from "../lib/results";


const MIC_CHUNK = 2048;
const PENDING_LIMIT_MS = 20000;

function floatToPcm16(input) {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

function downsample(input, inRate, outRate, state) {
  if (inRate === outRate) return input;

  const ratio = inRate / outRate;
  const out = new Float32Array(Math.ceil((input.length - state.pos) / ratio) + 1);
  let count = 0;
  let pos = state.pos;

  while (pos < input.length) {
    const from = Math.floor(pos);
    const to = Math.min(input.length, Math.floor(pos + ratio));
    let sum = 0;
    let taken = 0;
    for (let i = from; i < to; i++) {
      sum += input[i];
      taken++;
    }
    out[count++] = taken ? sum / taken : input[from] || 0;
    pos += ratio;
  }

  state.pos = Math.max(0, pos - input.length);
  return out.subarray(0, count);
}

function pcm16ToFloat(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const n = Math.floor(bytes.byteLength / 2);
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) out[i] = view.getInt16(i * 2, true) / 32768;
  return out;
}

export default function useVoiceSession({ wsPath, sampleRate = 8000, tts = {}, useCase = "", testRecord = "" }) {
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [botSpeaking, setBotSpeaking] = useState(false);
  const [userSpeaking, setUserSpeaking] = useState(false);
  const [muted, setMuted] = useState(false);
  const [results, setResults] = useState([]);
  const [startedAt, setStartedAt] = useState(null);
  const [turns, setTurns] = useState([]);
  const [workingOn, setWorkingOn] = useState("");
  const [usage, setUsage] = useState(null);

  const levelRef = useRef(0);
  const orbLevelRef = useRef(0);

  const wsRef = useRef(null);
  const micCtxRef = useRef(null);
  const outCtxRef = useRef(null);
  const streamRef = useRef(null);
  const nodeRef = useRef(null);
  const sourceRef = useRef(null);
  const playHeadRef = useRef(0);
  const sourcesRef = useRef([]);
  const stoppingRef = useRef(false);
  const mutedRef = useRef(false);
  const botLevelRef = useRef(0);
  const botDecayRef = useRef(0);

  const downsampleRef = useRef({ pos: 0 });

  const chunksRef = useRef(new Map());
  const openRef = useRef(new Set());
  const transferRef = useRef(0);

  const spokeAtRef = useRef(0);
  const awaitingRef = useRef(false);
  const turnSeqRef = useRef(0);
  const heldRef = useRef(false);

  const flushPlayback = useCallback(() => {
    for (const src of sourcesRef.current) {
      try {
        src.stop();
      } catch {
      }
    }
    sourcesRef.current = [];
    playHeadRef.current = 0;
    botLevelRef.current = 0;
  }, []);

  const playChunk = useCallback((bytes) => {
    const ctx = outCtxRef.current;
    if (!ctx || bytes.byteLength < 2) return;

    if (awaitingRef.current) {
      awaitingRef.current = false;
      const e2e = performance.now() - spokeAtRef.current;
      const id = ++turnSeqRef.current;
      const held = heldRef.current;
      heldRef.current = false;
      setTurns((list) => [...list, { id, e2eMs: e2e, held, at: Date.now() }].slice(-40));
    }

    const samples = pcm16ToFloat(bytes);

    let sum = 0;
    for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
    botLevelRef.current = Math.sqrt(sum / Math.max(1, samples.length));
    botDecayRef.current = performance.now();

    const buffer = ctx.createBuffer(1, samples.length, sampleRate);
    buffer.copyToChannel(samples, 0);

    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(ctx.destination);

    const lead = transferRef.current > 0 ? 0.18 : 0.06;
    const startAt = Math.max(ctx.currentTime + lead, playHeadRef.current);
    src.start(startAt);
    playHeadRef.current = startAt + buffer.duration;

    sourcesRef.current.push(src);
    src.onended = () => {
      sourcesRef.current = sourcesRef.current.filter((s) => s !== src);
    };
  }, [sampleRate]);

  const toggleMute = useCallback(() => {
    setMuted((prev) => {
      const next = !prev;
      mutedRef.current = next;
      const stream = streamRef.current;
      if (stream) stream.getAudioTracks().forEach((t) => (t.enabled = !next));
      if (next) levelRef.current = 0;
      return next;
    });
  }, []);

  const settleResult = useCallback((seq, patch) => {
    openRef.current.delete(seq);
    chunksRef.current.delete(seq);
    setResults((list) => mergeResult(list, seq, patch));
  }, []);

  const openResult = useCallback((seq) => {
    openRef.current.add(seq);
    chunksRef.current.delete(seq);
    setResults((list) =>
      list.some((r) => r.seq === seq)
        ? list
        : [...list, { seq, status: "pending", at: Date.now() }].slice(-MAX_RESULTS)
    );
    setTimeout(() => {
      if (!openRef.current.has(seq)) return;
      openRef.current.delete(seq);
      setResults((list) =>
        list.map((r) => (r.seq === seq && r.status === "pending" ? { ...r, status: "error" } : r))
      );
    }, PENDING_LIMIT_MS);
  }, []);

  const collectResult = useCallback(
    (msg) => {
      const { seq, chunk, chunks } = msg;
      const pieces = chunksRef.current.get(seq) || new Array(chunks).fill(null);
      pieces[chunk] = msg.html;
      chunksRef.current.set(seq, pieces);
      transferRef.current = seq;

      if (pieces.some((piece) => piece === null)) return;

      const html = pieces.join("");
      const resultId = msg.result_id || "";
      setTimeout(() => {
        if (transferRef.current === seq) transferRef.current = 0;
        settleResult(seq, { status: "ready", html, resultId });
      }, 0);
    },
    [settleResult]
  );

  const stop = useCallback(() => {
    stoppingRef.current = true;
    flushPlayback();

    if (wsRef.current) {
      try {
        if (wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: "hangup" }));
        }
      } catch {
      }
      try {
        wsRef.current.close(1000, "client hangup");
      } catch {
      }
      wsRef.current = null;
    }
    if (nodeRef.current) {
      try {
        nodeRef.current.disconnect();
      } catch {
      }
      nodeRef.current = null;
    }
    if (sourceRef.current) {
      try {
        sourceRef.current.disconnect();
      } catch {
      }
      sourceRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (micCtxRef.current) {
      try {
        micCtxRef.current.close();
      } catch {
      }
      micCtxRef.current = null;
    }
    if (outCtxRef.current) {
      try {
        outCtxRef.current.close();
      } catch {
      }
      outCtxRef.current = null;
    }

    mutedRef.current = false;
    levelRef.current = 0;
    botLevelRef.current = 0;
    setMuted(false);
    setStatus("idle");
    setBotSpeaking(false);
    setUserSpeaking(false);
    setStartedAt(null);
  }, [flushPlayback]);

  const start = useCallback(async () => {
    setError("");
    setResults([]);
    setTurns([]);
    setWorkingOn("");
    setUsage(null);
    turnSeqRef.current = 0;
    awaitingRef.current = false;
    heldRef.current = false;
    chunksRef.current = new Map();
    openRef.current = new Set();
    transferRef.current = 0;
    stoppingRef.current = false;
    mutedRef.current = false;
    setMuted(false);
    setStatus("requesting-mic");

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (e) {
      setStatus("idle");
      setError(
        e && e.name === "NotAllowedError"
          ? "Microphone permission was denied. Allow it in the browser's site settings."
          : "No microphone found. Check that a device is connected."
      );
      return;
    }

    streamRef.current = stream;
    setStatus("connecting");

    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    const micCtx = new AudioCtx();
    const outCtx = new AudioCtx();
    micCtxRef.current = micCtx;
    outCtxRef.current = outCtx;
    downsampleRef.current = { pos: 0 };
    await micCtx.resume();
    await outCtx.resume();

    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const sid = Math.random().toString(36).slice(2, 10);
    const query = new URLSearchParams({ session_id: `web-${sid}`, sample_rate: String(sampleRate) });
    if (tts.provider) query.set("tts_provider", tts.provider);
    if (tts.voice) query.set("tts_voice", tts.voice);
    if (tts.model) query.set("tts_model", tts.model);
    if (useCase) query.set("use_case", useCase);
    if (testRecord) query.set("test_record", testRecord);
    const ws = new WebSocket(`${proto}//${location.host}${wsPath}?${query}`);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus("live");
      setStartedAt(Date.now());

      if (micCtx.state !== "running") micCtx.resume().catch(() => {});
      if (outCtx.state !== "running") outCtx.resume().catch(() => {});

      const source = micCtx.createMediaStreamSource(stream);
      const node = micCtx.createScriptProcessor(MIC_CHUNK, 1, 1);
      sourceRef.current = source;
      nodeRef.current = node;

      node.onaudioprocess = (event) => {
        if (ws.readyState !== WebSocket.OPEN) return;
        const input = event.inputBuffer.getChannelData(0);
        const outgoing = downsample(
          input,
          micCtx.sampleRate,
          sampleRate,
          downsampleRef.current
        );

        if (mutedRef.current) {
          ws.send(new Int16Array(outgoing.length).buffer);
          return;
        }

        let sum = 0;
        for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
        levelRef.current = Math.sqrt(sum / input.length);

        ws.send(floatToPcm16(outgoing).buffer);
      };

      source.connect(node);
      node.connect(micCtx.destination);
    };

    ws.onmessage = (event) => {
      if (typeof event.data !== "string") {
        playChunk(new Uint8Array(event.data));
        return;
      }

      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }

      switch (msg.type) {
        case "user_started_speaking":
          setUserSpeaking(true);
          setWorkingOn("");
          heldRef.current = false;
          break;
        case "user_stopped_speaking":
          setUserSpeaking(false);
          spokeAtRef.current = performance.now();
          awaitingRef.current = true;
          break;
        case "latency":
          if (msg.call) setUsage(msg.call);
          setTurns((list) => {
            const amended = list.find((t) => t.turn === msg.turn);
            if (amended) return list.map((t) => (t === amended ? { ...t, ...msg } : t));
            const open = [...list].reverse().find((t) => t.sttMs === undefined);
            if (!open) return [...list, { id: ++turnSeqRef.current, at: Date.now(), ...msg }].slice(-40);
            return list.map((t) => (t.id === open.id ? { ...t, ...msg } : t));
          });
          break;
        case "status":
          setWorkingOn(msg.text || "");
          heldRef.current = true;
          break;
        case "result_pending":
          openResult(msg.seq);
          break;
        case "result_html":
          collectResult(msg);
          break;
        case "result_empty":
          settleResult(msg.seq, null);
          break;
        case "result_error":
          settleResult(msg.seq, { status: "error" });
          break;
        case "bot_started_speaking":
          setBotSpeaking(true);
          break;
        case "bot_stopped_speaking":
          setBotSpeaking(false);
          break;
        case "interruption":
          flushPlayback();
          awaitingRef.current = false;
          setBotSpeaking(false);
          break;
        default:
          break;
      }
    };

    ws.onerror = () => {
      if (!stoppingRef.current) setError("Connection trouble. Check that the server is reachable.");
    };

    ws.onclose = () => {
      if (!stoppingRef.current) {
        setError((prev) => prev || "The session ended.");
        stop();
      }
    };
  }, [collectResult, flushPlayback, openResult, playChunk, sampleRate, settleResult, stop, tts.model, tts.provider, tts.voice, useCase, testRecord, wsPath]);

  useEffect(() => () => stop(), [stop]);

  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const sinceBot = performance.now() - botDecayRef.current;
      if (sinceBot > 220) botLevelRef.current *= 0.86;
      const bot = botLevelRef.current;
      orbLevelRef.current = bot > 0.006 ? bot : mutedRef.current ? 0 : levelRef.current;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  return {
    status,
    error,
    botSpeaking,
    userSpeaking,
    muted,
    results,
    turns,
    workingOn,
    usage,
    startedAt,
    orbLevelRef,
    start,
    stop,
    toggleMute,
    dismissResult: (seq) => settleResult(seq, null),
  };
}
