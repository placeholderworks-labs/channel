USD_TO_INR = 95.39


STT_INR_PER_MINUTE = {
    "deepgram:nova-3": 0.5533,
    "deepgram:nova-2": 0.5533,
    "deepgram_flux:flux-general-multi": 0.7440,
    "deepgram_flux:flux-general-en": 0.6200,
}
_STT_FALLBACK_INR_PER_MINUTE = 0.9539

LLM_INR_PER_PROMPT_TOKEN = 0.00001431
LLM_INR_PER_CACHED_PROMPT_TOKEN = 0.00000715
LLM_INR_PER_COMPLETION_TOKEN = 0.00005723

TTS_INR_PER_1K_CHARACTERS = {
    "murf": 0.9539,
    "sarvam": 3.0,
}


def compute_call_cost(
    call_duration_s,
    llm_prompt_tokens,
    llm_completion_tokens,
    tts_characters,
    tts_provider,
    llm_cached_prompt_tokens=0,
    stt_provider=None,
    stt_model=None,
):
    provider = (tts_provider or "").lower()

    stt_provider = (stt_provider or "deepgram").lower()
    stt_model = stt_model or "nova-3"
    stt_rate = STT_INR_PER_MINUTE.get(f"{stt_provider}:{stt_model}")
    stt_priced = stt_rate is not None
    if not stt_priced:
        stt_rate = _STT_FALLBACK_INR_PER_MINUTE
    stt_inr = (call_duration_s / 60.0) * stt_rate

    cached = max(0, min(llm_cached_prompt_tokens, llm_prompt_tokens))
    uncached = llm_prompt_tokens - cached

    llm_uncached_prompt_inr = uncached * LLM_INR_PER_PROMPT_TOKEN
    llm_cached_prompt_inr = cached * LLM_INR_PER_CACHED_PROMPT_TOKEN
    llm_prompt_inr = llm_uncached_prompt_inr + llm_cached_prompt_inr
    llm_completion_inr = llm_completion_tokens * LLM_INR_PER_COMPLETION_TOKEN
    llm_inr = llm_prompt_inr + llm_completion_inr

    tts_rate = TTS_INR_PER_1K_CHARACTERS.get(provider)
    tts_priced = tts_rate is not None
    tts_inr = (tts_characters / 1000.0) * tts_rate if tts_priced else 0.0

    total_inr = stt_inr + llm_inr + tts_inr

    return {
        "call_duration_s": call_duration_s,
        "stt_inr": stt_inr,
        "stt_provider": stt_provider,
        "stt_model": stt_model,
        "stt_rate": stt_rate,
        "stt_priced": stt_priced,
        "llm_prompt_inr": llm_prompt_inr,
        "llm_uncached_prompt_inr": llm_uncached_prompt_inr,
        "llm_cached_prompt_inr": llm_cached_prompt_inr,
        "llm_cached_prompt_tokens": cached,
        "llm_uncached_prompt_tokens": uncached,
        "llm_cache_hit_rate": (cached / llm_prompt_tokens) if llm_prompt_tokens else 0.0,
        "llm_completion_inr": llm_completion_inr,
        "llm_inr": llm_inr,
        "tts_inr": tts_inr,
        "tts_provider": provider or "unknown",
        "tts_priced": tts_priced,
        "total_inr": total_inr,
        "total_usd": total_inr / USD_TO_INR,
    }


def format_cost_lines(
    cost,
    llm_prompt_tokens,
    llm_completion_tokens,
    tts_characters,
):
    duration_s = cost["call_duration_s"]
    minutes = int(duration_s // 60)
    seconds = duration_s - (minutes * 60)
    stt_label = f"STT ({cost['stt_provider']} {cost['stt_model']})".ljust(23)

    lines = [
        f"Call duration : {minutes}m {seconds:.1f}s ({duration_s:.1f}s)",
        "",
        f"{stt_label}: Rs {cost['stt_inr']:.4f}"
        f"  [{duration_s / 60.0:.3f} min @ Rs {cost['stt_rate']}/min"
        + ("" if cost["stt_priced"] else ", estimated — no rate configured")
        + "]",
    ]

    brain_is_remote = not llm_prompt_tokens and not llm_completion_tokens
    if brain_is_remote:
        lines.append("LLM                    : billed to pw-llm-layer, not measured here")
    else:
        lines += [
            f"LLM input (uncached)   : Rs {cost['llm_uncached_prompt_inr']:.4f}"
            f"  [{cost['llm_uncached_prompt_tokens']} tok @ Rs {LLM_INR_PER_PROMPT_TOKEN}/tok]",
            f"LLM input (cached)     : Rs {cost['llm_cached_prompt_inr']:.4f}"
            f"  [{cost['llm_cached_prompt_tokens']} tok @ Rs {LLM_INR_PER_CACHED_PROMPT_TOKEN}/tok"
            f", {cost['llm_cache_hit_rate'] * 100:.1f}% of {llm_prompt_tokens} prompt tok]",
            f"LLM output tokens      : Rs {cost['llm_completion_inr']:.4f}"
            f"  [{llm_completion_tokens} tok @ Rs {LLM_INR_PER_COMPLETION_TOKEN}/tok]",
            f"LLM subtotal           : Rs {cost['llm_inr']:.4f}",
        ]

    tts_label = f"TTS ({cost['tts_provider']})".ljust(23)
    if cost["tts_priced"]:
        rate = TTS_INR_PER_1K_CHARACTERS[cost["tts_provider"]]
        lines.append(
            f"{tts_label}: Rs {cost['tts_inr']:.4f}"
            f"  [{tts_characters} chars @ Rs {rate}/1k chars]"
        )
    else:
        lines.append(
            f"{tts_label}: not priced"
            f"  [{tts_characters} chars, no rate configured]"
        )

    lines.append("")
    lines.append(f"TOTAL : Rs {cost['total_inr']:.4f}  (${cost['total_usd']:.6f})")

    if not cost["tts_priced"]:
        lines.append("Note  : total excludes TTS (no rate configured for this provider)")

    return lines
