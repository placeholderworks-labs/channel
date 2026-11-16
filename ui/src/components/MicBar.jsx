import VoiceOrb from "./VoiceOrb";
import { Hangup, Mic, Refresh } from "./Icons";

export default function MicBar({ session, mode, live, busy, armed, stateText, hint, onRestart }) {
  return (
    <div className="micbar">
      <VoiceOrb mode={mode} levelRef={session.orbLevelRef} size={88} />

      <div className="micbar-text">
        <div className="micbar-state">{stateText}</div>
        <div className={`micbar-hint ${session.error ? "err" : ""}`}>{session.error || hint}</div>
      </div>

      <div className="micbar-controls">
        {live ? (
          <>
            <button
              className={`ctrl ${session.muted ? "on" : ""}`}
              onClick={session.toggleMute}
              title={session.muted ? "Turn the microphone on" : "Turn the microphone off"}
              aria-label={session.muted ? "Unmute" : "Mute"}
            >
              <Mic off={session.muted} size={19} />
            </button>
            <button
              className="ctrl end"
              onClick={session.stop}
              title="End the session"
              aria-label="End the session"
            >
              <Hangup size={19} />
            </button>
            <button className="ctrl" onClick={onRestart} title="Start over" aria-label="Start over">
              <Refresh size={18} />
            </button>
          </>
        ) : (
          <button className="btn btn-live" onClick={session.start} disabled={busy || !armed}>
            <Mic size={15} />
            {busy ? "Connecting…" : "Start talking"}
          </button>
        )}
      </div>
    </div>
  );
}
