import numpy as np
from scipy.signal import butter, sosfilt


_LOOP_SECONDS = 12.0

_BABBLE_BANDS = [(300, 800), (500, 1500), (700, 2200), (900, 3000)]


def _bandpass(signal: np.ndarray, sample_rate: int, low: float, high: float) -> np.ndarray:
    nyq = sample_rate / 2.0
    sos = butter(4, [low / nyq, min(high / nyq, 0.999)], btype="band", output="sos")
    return sosfilt(sos, signal)


def _make_babble(n: int, sample_rate: int, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(n) / sample_rate
    babble = np.zeros(n)

    for low, high in _BABBLE_BANDS:
        voice = _bandpass(rng.standard_normal(n), sample_rate, low, high)
        voice /= np.max(np.abs(voice)) + 1e-9

        mod_rate = rng.uniform(0.15, 0.4)
        phase = rng.uniform(0, 2 * np.pi)
        envelope = 0.5 + 0.5 * np.sin(2 * np.pi * mod_rate * t + phase)
        envelope = 0.3 + 0.7 * envelope

        babble += voice * envelope

    babble /= np.max(np.abs(babble)) + 1e-9
    return babble


def _make_transients(n: int, sample_rate: int, rng: np.random.Generator) -> np.ndarray:
    track = np.zeros(n)
    duration_secs = n / sample_rate
    num_events = int(duration_secs * 1.5)

    for _ in range(num_events):
        start = rng.integers(0, n - 1)
        click_len = int(rng.uniform(0.005, 0.03) * sample_rate)
        click_len = min(click_len, n - start)
        if click_len <= 8:
            continue

        low = rng.uniform(400, 2000)
        high = min(low + rng.uniform(800, 3000), sample_rate / 2 - 100)
        burst = rng.standard_normal(click_len)
        burst = _bandpass(burst, sample_rate, low, high)
        burst /= np.max(np.abs(burst)) + 1e-9

       
        decay = np.exp(-np.linspace(0, 6, click_len))
        track[start : start + click_len] += burst * decay * rng.uniform(0.4, 1.0)

    if np.max(np.abs(track)) > 0:
        track /= np.max(np.abs(track)) + 1e-9
    return track


def _generate_loop(sample_rate: int) -> np.ndarray:
    n = int(_LOOP_SECONDS * sample_rate)
    rng = np.random.default_rng(seed=1234)

    babble = _make_babble(n, sample_rate, rng)
    transients = _make_transients(n, sample_rate, rng)

    hum = np.cumsum(rng.standard_normal(n))
    hum -= hum.mean()
    hum = _bandpass(hum, sample_rate, 40, 200)
    hum /= np.max(np.abs(hum)) + 1e-9

    loop = babble * 0.7 + transients * 0.5 + hum * 0.4

    fade_len = int(1.0 * sample_rate)
    fade = np.linspace(0.0, 1.0, fade_len)
    loop[:fade_len] = loop[:fade_len] * fade + loop[-fade_len:] * (1 - fade)

    loop /= np.max(np.abs(loop)) + 1e-9
    return loop.astype(np.float64)


class AmbienceLoop:

    def __init__(self, level_db: float):
        self._gain = 10 ** (level_db / 20.0)
        self._loops: dict[int, np.ndarray] = {}
        self._cursor: dict[int, int] = {}

    def _loop_for(self, sample_rate: int) -> np.ndarray:
        if sample_rate not in self._loops:
            self._loops[sample_rate] = _generate_loop(sample_rate)
            self._cursor[sample_rate] = 0
        return self._loops[sample_rate]

    def _advance(self, sample_rate: int, frames: int) -> np.ndarray:
        loop = self._loop_for(sample_rate)
        cursor = self._cursor[sample_rate]
        idx = (np.arange(frames) + cursor) % len(loop)
        self._cursor[sample_rate] = (cursor + frames) % len(loop)
        return loop[idx] * self._gain * 32767.0

    def mix(self, pcm: bytes, sample_rate: int, num_channels: int) -> bytes:
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
        frames = len(samples) // num_channels if num_channels > 1 else len(samples)

        noise = self._advance(sample_rate, frames)
        if num_channels > 1:
            noise = np.repeat(noise, num_channels)

        mixed = np.clip(samples + noise, -32768, 32767).astype(np.int16)
        return mixed.tobytes()

    def generate(self, sample_rate: int, num_channels: int, num_frames: int) -> bytes:
        noise = self._advance(sample_rate, num_frames)
        if num_channels > 1:
            noise = np.repeat(noise, num_channels)

        return np.clip(noise, -32768, 32767).astype(np.int16).tobytes()
