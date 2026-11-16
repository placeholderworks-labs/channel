import asyncio
import logging
import time

from pipecat.frames.frames import (
    LLMContextFrame,
    LLMFullResponseStartFrame,
    MetricsFrame,
)
from pipecat.metrics.metrics import (
    LLMUsageMetricsData,
    TTFAMetricsData,
    TTSUsageMetricsData,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.metrics.frame_processor_metrics import TTFBMetricsData

from pw_channel import config
from pw_channel.channels.voice.metrics.cost import compute_call_cost, format_cost_lines

_GREEN = "\033[92m"
_RESET = "\033[0m"

logger = logging.getLogger("latency_metrics")


class LatencyObserver(BaseObserver):

    def __init__(
        self,
        call_id: str = "unknown",
        user_aggregator=None,
        engine=None,
        on_turn=None,
        stt_provider=None,
        stt_model=None,
    ):
        super().__init__()
        self._call_id = call_id
        self._stt_provider = stt_provider
        self._stt_model = stt_model
        self._user_aggregator = user_aggregator
        self._engine_name = getattr(engine, "name", None)
        self._on_turn = on_turn
        self._lock = asyncio.Lock()
        self._last_asr_ttfb_s = None
        self._current = None
        self._turns = []
        self._call_started_at = None
        self._call_ended_at = None
        self._call_llm_prompt_tokens = 0
        self._call_llm_cached_prompt_tokens = 0
        self._call_llm_completion_tokens = 0
        self._call_tts_characters = 0
        self._usage_hwm = {}
        self._usage_events = 0
        self._usage_events_deduped = 0
        self._usage_anomalies = 0

    def note_llm_usage(self, tokens: dict) -> None:
        if not tokens:
            return
        prompt = int(tokens.get("input") or 0)
        completion = int(tokens.get("output") or 0)
        cached = int(tokens.get("cached") or 0)

        self._call_llm_prompt_tokens += prompt
        self._call_llm_completion_tokens += completion
        self._call_llm_cached_prompt_tokens += cached

        if self._current is not None:
            self._current["llm_prompt_tokens"] += prompt
            self._current["llm_completion_tokens"] += completion
            self._current["llm_cached_prompt_tokens"] += cached

    def call_totals(self) -> dict:
        return {
            "promptTokens": self._call_llm_prompt_tokens,
            "cachedTokens": self._call_llm_cached_prompt_tokens,
            "completionTokens": self._call_llm_completion_tokens,
            "totalTokens": self._call_llm_prompt_tokens + self._call_llm_completion_tokens,
            "ttsCharacters": self._call_tts_characters,
            "turns": len(self._turns),
        }

    def mark_call_started(self):
        if self._call_started_at is None:
            self._call_started_at = time.monotonic()

    def mark_call_ended(self):
        if self._call_ended_at is None:
            self._call_ended_at = time.monotonic()

    def _call_duration_s(self):
        if self._call_started_at is None:
            return 0.0
        end = self._call_ended_at if self._call_ended_at is not None else time.monotonic()
        return max(0.0, end - self._call_started_at)

    def _is_turn_boundary(self, source) -> bool:
        if self._user_aggregator is not None:
            return source is self._user_aggregator
        return getattr(source, "name", "").startswith("LLMUserAggregator")

    def _is_brain(self, processor: str) -> bool:
        if self._engine_name and self._engine_name in processor:
            return True
        return "LLMService" in processor or "VoiceEngine" in processor

    def _new_turn(self, asr_ttfb_s):
        return {
            "asr_ttfb_s": asr_ttfb_s,
            "llm_ttft_s": None,
            "tts_ttfc_s": None,
            "llm_prompt_tokens": 0,
            "llm_cached_prompt_tokens": 0,
            "llm_completion_tokens": 0,
            "tts_characters": 0,
            "tts_silence_s": None,
        }

    def _close_current_turn(self):
        if self._current is None:
            return
        if self._current["llm_ttft_s"] is not None and self._current["tts_ttfc_s"] is not None:
            total_s = (
                (self._current["asr_ttfb_s"] or 0.0)
                + self._current["llm_ttft_s"]
                + self._current["tts_ttfc_s"]
                + (self._current["tts_silence_s"] or 0.0)
            )
            self._current["total_ms"] = total_s * 1000
            self._turns.append(self._current)
            self._publish(self._current, len(self._turns))
        self._current = None

    def _publish(self, turn, number):
        if self._on_turn is None:
            return
        try:
            self._on_turn(
                {
                    "turn": number,
                    "sttMs": (
                        turn["asr_ttfb_s"] * 1000
                        if turn["asr_ttfb_s"] is not None
                        else None
                    ),
                    "llmMs": turn["llm_ttft_s"] * 1000,
                    "ttsMs": turn["tts_ttfc_s"] * 1000,
                    "silenceMs": (
                        turn["tts_silence_s"] * 1000
                        if turn["tts_silence_s"] is not None
                        else None
                    ),
                    "totalMs": turn["total_ms"],
                    "promptTokens": turn["llm_prompt_tokens"],
                    "cachedTokens": turn["llm_cached_prompt_tokens"],
                    "completionTokens": turn["llm_completion_tokens"],
                    "totalTokens": turn["llm_prompt_tokens"] + turn["llm_completion_tokens"],
                    "ttsCharacters": turn["tts_characters"],
                    "call": self.call_totals(),
                }
            )
        except Exception:
            logger.debug("[latency_metrics] turn listener raised", exc_info=True)

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame

        if isinstance(frame, LLMContextFrame) and self._is_turn_boundary(data.source):
            async with self._lock:
                self._close_current_turn()
                self._current = self._new_turn(self._last_asr_ttfb_s)
            return

        if isinstance(frame, LLMFullResponseStartFrame):
            source_name = getattr(data.source, "name", None)
            if source_name:
                async with self._lock:
                    self._usage_hwm[source_name] = {
                        "prompt": 0,
                        "cached": 0,
                        "completion": 0,
                    }
            return

        if not isinstance(frame, MetricsFrame):
            return

        for metric in frame.data:
            if metric.processor != data.source.name:
                continue

            if isinstance(metric, LLMUsageMetricsData):
                
                cached = metric.value.cache_read_input_tokens or 0
                async with self._lock:
                    key = metric.processor
                    hwm = self._usage_hwm.get(key)
                    self._usage_events += 1

                    if hwm is None:
                        hwm = {"prompt": 0, "cached": 0, "completion": 0}
                        self._usage_hwm[key] = hwm
                        self._usage_anomalies += 1
                        logger.warning(
                            f"[latency_metrics] call={self._call_id}: usage from {key} "
                            f"with no preceding LLMFullResponseStartFrame — counting it "
                            f"in full"
                        )
                    elif hwm["prompt"] and metric.value.prompt_tokens != hwm["prompt"]:
                        self._usage_anomalies += 1
                        logger.warning(
                            f"[latency_metrics] call={self._call_id}: {key} reported "
                            f"prompt_tokens={metric.value.prompt_tokens} after "
                            f"{hwm['prompt']} within one response — upstream usage "
                            f"semantics changed, re-check the dedupe"
                        )

                    delta_prompt = max(0, metric.value.prompt_tokens - hwm["prompt"])
                    delta_cached = max(0, cached - hwm["cached"])
                    delta_completion = max(
                        0, metric.value.completion_tokens - hwm["completion"]
                    )

                    if delta_prompt == 0 and delta_completion == 0:
                        self._usage_events_deduped += 1

                    hwm["prompt"] = max(hwm["prompt"], metric.value.prompt_tokens)
                    hwm["cached"] = max(hwm["cached"], cached)
                    hwm["completion"] = max(
                        hwm["completion"], metric.value.completion_tokens
                    )

                    self._call_llm_prompt_tokens += delta_prompt
                    self._call_llm_cached_prompt_tokens += delta_cached
                    self._call_llm_completion_tokens += delta_completion
                    if self._current is not None:
                        self._current["llm_prompt_tokens"] += delta_prompt
                        self._current["llm_cached_prompt_tokens"] += delta_cached
                        self._current["llm_completion_tokens"] += delta_completion
                continue

            if isinstance(metric, TTSUsageMetricsData):
                async with self._lock:
                    self._call_tts_characters += metric.value
                    if self._current is not None:
                        self._current["tts_characters"] += metric.value
                continue

            if isinstance(metric, TTFAMetricsData):
                async with self._lock:
                    self._record_leading_silence(metric)
                continue

            if not isinstance(metric, TTFBMetricsData):
                continue

            if metric.value <= 0.0:
                continue

            processor = metric.processor

            async with self._lock:
                if "STTService" in processor:
                    self._last_asr_ttfb_s = metric.value
                elif self._is_brain(processor):
                    if self._current is not None and self._current["llm_ttft_s"] is None:
                        self._current["llm_ttft_s"] = metric.value
                elif "TTSService" in processor:
                    if self._current is not None and self._current["tts_ttfc_s"] is None:
                        self._current["tts_ttfc_s"] = metric.value
                        self._close_current_turn()

    def _record_leading_silence(self, metric) -> None:
        silence = float(getattr(metric, "leading_silence", 0.0) or 0.0)
        if silence <= 0.0:
            return
        turn = self._turns[-1] if self._turns else None
        if turn is None or turn.get("tts_silence_s") is not None:
            return
        turn["tts_silence_s"] = silence
        if turn.get("total_ms") is not None:
            turn["total_ms"] += silence * 1000
        self._publish(turn, self._turns.index(turn) + 1)

    def snapshot(self, providers: dict | None = None) -> dict:
        turns = [
            {
                "turn": n,
                "sttMs": t["asr_ttfb_s"] * 1000 if t["asr_ttfb_s"] is not None else None,
                "llmMs": t["llm_ttft_s"] * 1000,
                "ttsMs": t["tts_ttfc_s"] * 1000,
                "silenceMs": t["tts_silence_s"] * 1000 if t["tts_silence_s"] is not None else None,
                "totalMs": t["total_ms"],
                "promptTokens": t["llm_prompt_tokens"],
                "cachedTokens": t["llm_cached_prompt_tokens"],
                "completionTokens": t["llm_completion_tokens"],
            }
            for n, t in enumerate(self._turns, start=1)
        ]
        totals = [t["totalMs"] for t in turns]

        def avg(key):
            values = [t[key] for t in turns if t[key] is not None]
            return sum(values) / len(values) if values else None

        try:
            cost = compute_call_cost(
                call_duration_s=self._call_duration_s(),
                llm_prompt_tokens=self._call_llm_prompt_tokens,
                llm_cached_prompt_tokens=self._call_llm_cached_prompt_tokens,
                llm_completion_tokens=self._call_llm_completion_tokens,
                tts_characters=self._call_tts_characters,
                tts_provider=(providers or {}).get("tts", {}).get("provider") or config.TTS_PROVIDER,
                stt_provider=self._stt_provider,
                stt_model=self._stt_model,
            )
            cost = {k: v for k, v in cost.items() if isinstance(v, (int, float, str, bool)) or v is None}
        except Exception:
            cost = None
        return {
            "turns": turns,
            "averageMs": sum(totals) / len(totals) if totals else None,
            "minMs": min(totals) if totals else None,
            "maxMs": max(totals) if totals else None,
            "averageSttMs": avg("sttMs"),
            "averageLlmMs": avg("llmMs"),
            "averageTtsMs": avg("ttsMs"),
            "durationSecs": self._call_duration_s(),
            "tokens": self.call_totals(),
            "providers": providers or {},
            "cost": cost,
        }

    def log_call_latency(self):
        self._close_current_turn()
        self.mark_call_ended()

        if not self._turns:
            logger.info(
                f"{_GREEN}[latency_metrics] call={self._call_id}: "
                f"no complete turn captured this call{_RESET}"
            )
            self._log_token_totals()
            self._log_call_cost()
            return

        breakdown_lines = []
        for turn_number, turn in enumerate(self._turns, start=1):
            asr = turn["asr_ttfb_s"]
            asr_text = f"{asr:.3f}s" if asr is not None else "n/a"
            breakdown_lines.append(
                f"Turn {turn_number} : "
                f"asr_ttfb={asr_text} "
                f"llm_ttft={turn['llm_ttft_s']:.3f}s "
                f"tts_ttfc={turn['tts_ttfc_s']:.3f}s "
                f"tts_silence={(turn.get('tts_silence_s') or 0.0):.3f}s "
                f"total={turn['total_ms'] / 1000:.3f}s "
                f"tokens={turn['llm_prompt_tokens']}in"
                f"/{turn['llm_cached_prompt_tokens']}cached"
                f"/{turn['llm_completion_tokens']}out"
            )
        logger.info(
            f"{_GREEN}[latency_metrics] call={self._call_id} turn breakdown:\n"
            + "\n".join(breakdown_lines) + _RESET
        )

        totals_ms = [turn["total_ms"] for turn in self._turns]
        min_ms = min(totals_ms)
        max_ms = max(totals_ms)
        min_turn = totals_ms.index(min_ms) + 1
        max_turn = totals_ms.index(max_ms) + 1
        average_ms = sum(totals_ms) / len(totals_ms)

        lines = [f"Call ID: {self._call_id}", ""]
        for turn_number, turn in enumerate(self._turns, start=1):
            lines.append(f"Turn {turn_number} : {turn['total_ms']:.0f} ms")

        lines.append("")
        lines.append(f"Average : {average_ms:.0f} ms")
        lines.append(f"Min     : {min_ms:.0f} ms (Turn {min_turn})")
        lines.append(f"Max     : {max_ms:.0f} ms (Turn {max_turn})")

        logger.info(
            f"{_GREEN}[latency_metrics] call summary:\n" + "\n".join(lines) + _RESET
        )

        self._log_token_totals()
        self._log_call_cost()

    def _log_token_totals(self) -> None:
        totals = self.call_totals()
        hit = (
            self._call_llm_cached_prompt_tokens / self._call_llm_prompt_tokens * 100
            if self._call_llm_prompt_tokens
            else 0.0
        )
        per_turn = (
            totals["totalTokens"] // totals["turns"] if totals["turns"] else 0
        )
        lines = [
            f"Call ID: {self._call_id}",
            "",
            f"Input  (prompt)     : {totals['promptTokens']}",
            f"  of which cached   : {totals['cachedTokens']}  ({hit:.1f}% cache hit)",
            f"Output (completion) : {totals['completionTokens']}",
            f"Total               : {totals['totalTokens']}",
            "",
            f"Turns               : {totals['turns']}",
            f"Average per turn    : {per_turn}",
            f"TTS characters      : {totals['ttsCharacters']}",
        ]
        logger.info(
            f"{_GREEN}[latency_metrics] llm token usage:\n" + "\n".join(lines) + _RESET
        )

    def _log_call_cost(self):
        cost = compute_call_cost(
            call_duration_s=self._call_duration_s(),
            llm_prompt_tokens=self._call_llm_prompt_tokens,
            llm_cached_prompt_tokens=self._call_llm_cached_prompt_tokens,
            llm_completion_tokens=self._call_llm_completion_tokens,
            tts_characters=self._call_tts_characters,
            tts_provider=config.TTS_PROVIDER,
            stt_provider=self._stt_provider,
            stt_model=self._stt_model,
        )

        cost_lines = format_cost_lines(
            cost,
            llm_prompt_tokens=self._call_llm_prompt_tokens,
            llm_completion_tokens=self._call_llm_completion_tokens,
            tts_characters=self._call_tts_characters,
        )

        logger.info(
            f"{_GREEN}[latency_metrics] call={self._call_id} cost breakdown:\n"
            + "\n".join(cost_lines) + _RESET
        )

        logger.info(
            f"{_GREEN}[latency_metrics] call={self._call_id} llm usage events: "
            f"{self._usage_events} seen, {self._usage_events_deduped} duplicate, "
            f"{self._usage_anomalies} anomalous{_RESET}"
        )
