import { useEffect, useRef, useState } from "react";
import { api } from "./api";

export default function useAutoHindi(name, setHindi) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const manual = useRef(false);
  const first = useRef(true);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return undefined;
    }
    if (manual.current) return undefined;
    const text = (name || "").trim();
    if (!text) {
      setHindi("");
      return undefined;
    }
    let cancelled = false;
    const timer = setTimeout(async () => {
      setBusy(true);
      setError("");
      try {
        const r = await api.transliterate(text);
        if (!cancelled && !manual.current && r?.devanagari) setHindi(r.devanagari);
      } catch (e) {
        if (!cancelled) setError(e.message);
      } finally {
        if (!cancelled) setBusy(false);
      }
    }, 600);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [name]);

  return {
    busy,
    error,
    markManual: () => { manual.current = true; },
    hint: busy ? "Writing it in Hindi…" : error || (manual.current ? "Your spelling" : "Filled in automatically. Edit if needed."),
  };
}
