import { useLayoutEffect, useRef } from "react";


const MODE_TOKEN = {
  idle: "--faint",
  listening: "--ok",
  speaking: "--brand",
  muted: "--halt",
};

function hexToRgb(hex, fallback) {
  const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec((hex || "").trim());
  if (!m) return fallback;
  let h = m[1];
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const n = parseInt(h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}
function mix(c1, c2, t) {
  return [lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t)];
}
function rgb(c, alpha) {
  const s = `${Math.round(c[0])},${Math.round(c[1])},${Math.round(c[2])}`;
  return alpha == null ? `rgb(${s})` : `rgba(${s},${alpha})`;
}

const FALLBACK = [134, 151, 170];

export default function VoiceOrb({ mode = "idle", levelRef, size = 200 }) {
  const canvasRef = useRef(null);
  const wrapRef = useRef(null);
  const modeRef = useRef(mode);
  modeRef.current = mode;

  useLayoutEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);

    const root = getComputedStyle(document.documentElement);
    let col = FALLBACK.slice();

    let raf = 0;
    let t = 0;
    let energy = 0;

    const cx = size / 2;
    const cy = size / 2;
    const baseR = size * 0.285;

    const draw = () => {
      const target = hexToRgb(root.getPropertyValue(MODE_TOKEN[modeRef.current] || MODE_TOKEN.idle), col);
      col = mix(col, target, 0.09);

      const active = modeRef.current !== "idle" && modeRef.current !== "muted";
      const raw = active ? Math.min(1, ((levelRef && levelRef.current) || 0) * 3.1) : 0.1;
      energy += (raw - energy) * (raw > energy ? 0.34 : 0.07);

      t += 0.016;
      ctx.clearRect(0, 0, size, size);

      const breathe = Math.sin(t * 1.25) * (active ? 0.022 : 0.01);
      const pump = energy * 0.2;
      const r = baseR * (1 + breathe + pump);

      const halo = ctx.createRadialGradient(cx, cy, r * 0.85, cx, cy, r * 1.95);
      halo.addColorStop(0, rgb(col, 0.22 + energy * 0.22));
      halo.addColorStop(0.55, rgb(col, 0.07 + energy * 0.09));
      halo.addColorStop(1, rgb(col, 0));
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(cx, cy, r * 1.95, 0, Math.PI * 2);
      ctx.fill();

      for (let ring = 0; ring < 2 && active; ring++) {
        const rr = r * (1.16 + ring * 0.15) + energy * (5 + ring * 4);
        ctx.beginPath();
        for (let i = 0; i <= 72; i++) {
          const a = (i / 72) * Math.PI * 2;
          const wob =
            Math.sin(a * 3 + t * (1.5 + ring * 0.5)) * (2.2 + energy * 5.5) +
            Math.sin(a * 5 - t * (2.1 - ring * 0.4)) * (1.3 + energy * 3.2);
          const rad = rr + wob;
          const x = cx + Math.cos(a) * rad;
          const y = cy + Math.sin(a) * rad;
          i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.strokeStyle = rgb(col, 0.26 - ring * 0.1 + energy * 0.24);
        ctx.lineWidth = 1.5 - ring * 0.4;
        ctx.stroke();
      }

      ctx.beginPath();
      for (let i = 0; i <= 96; i++) {
        const a = (i / 96) * Math.PI * 2;
        const wob =
          Math.sin(a * 2 + t * 1.15) * (1.6 + energy * 9) +
          Math.sin(a * 4 - t * 1.75) * (1.1 + energy * 6.5) +
          Math.sin(a * 7 + t * 2.4) * (0.5 + energy * 3.4);
        const rad = r + wob;
        const x = cx + Math.cos(a) * rad;
        const y = cy + Math.sin(a) * rad;
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.closePath();

      const g = ctx.createRadialGradient(cx - r * 0.34, cy - r * 0.4, r * 0.12, cx, cy, r * 1.28);
      g.addColorStop(0, rgb(mix(col, [255, 255, 255], 0.34)));
      g.addColorStop(0.48, rgb(col));
      g.addColorStop(1, rgb(mix(col, [0, 0, 0], 0.3)));
      ctx.fillStyle = g;
      ctx.shadowColor = rgb(col, 0.32 + energy * 0.2);
      ctx.shadowBlur = 22 + energy * 26;
      ctx.shadowOffsetY = 6;
      ctx.fill();
      ctx.shadowColor = "transparent";
      ctx.shadowBlur = 0;
      ctx.shadowOffsetY = 0;

      const gloss = ctx.createRadialGradient(
        cx - r * 0.36, cy - r * 0.46, 0,
        cx - r * 0.36, cy - r * 0.46, r * 0.92
      );
      gloss.addColorStop(0, "rgba(255,255,255,.4)");
      gloss.addColorStop(0.42, "rgba(255,255,255,.08)");
      gloss.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = gloss;
      ctx.fill();

      if (wrapRef.current) {
        wrapRef.current.style.setProperty("--glow", (0.8 + energy * 0.42).toFixed(3));
        wrapRef.current.style.setProperty("--glowop", (0.42 + energy * 0.5).toFixed(3));
      }

      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [size, levelRef]);

  return (
    <div className={`orb-wrap orb-${mode}`} ref={wrapRef}>
      <div className="orb-glow" />
      <div className="orb-ring r1" />
      <div className="orb-ring r2" />
      <canvas ref={canvasRef} className="orb-canvas" style={{ width: size, height: size }} aria-hidden="true" />
    </div>
  );
}
