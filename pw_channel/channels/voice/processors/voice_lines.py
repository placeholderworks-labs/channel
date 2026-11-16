import re

_PUNCTUATION = "।.,!?—-…\"'“”‘’ "

HOLD_LINES = {
    "hindi": (
        "जी, देख रही हूँ आपके लिए।",
        "ठीक है, options निकाल रही हूँ।",
        "हाँ, अभी check कर रही हूँ।",
        "अभी देखती हूँ, ज़रा रुकिए।",
        "बताती हूँ, list निकल रही है।",
        "एक second, देख लेती हूँ।",
    ),
    "english": (
        "Sure, let me check that for you.",
        "Alright, pulling up the options now.",
        "Yes, I'm looking into it right now.",
        "Just a moment, let me see.",
        "One second, checking on that.",
    ),
}

SECOND_HOLD_LINES = {
    "hindi": (
        "थोड़ा time लग रहा है, बस आ रही है list।",
        "अभी भी search चल रहा है, एक moment और।",
    ),
    "english": (
        "It's taking a little longer, almost there.",
        "Still searching, just one more moment.",
    ),
}

COMING_LINES = {
    "hindi": (
        "जी, बताती हूँ।",
        "हाँ, अभी बताती हूँ।",
        "जी, एक second।",
        "बस एक moment, बताती हूँ।",
    ),
    "english": (
        "Yes, let me tell you.",
        "Right, I'll explain.",
        "One second.",
        "Just a moment, I'll tell you.",
    ),
}

ACK_LINES = {
    "hindi": (
        "समझ गई, एक second।",
        "जी, समझ रही हूँ — एक moment।",
        "अच्छा — एक पल दीजिए।",
        "जी बिल्कुल, एक moment।",
    ),
    "english": (
        "I see, one second.",
        "Understood — just a moment.",
        "Right, one moment please.",
        "Of course — one second.",
    ),
}

ACTION_LINES = {
    "hindi": (
        "जी, अभी करती हूँ।",
        "ठीक है, एक moment।",
        "हाँ, अभी कर रही हूँ।",
        "जी, बस एक second।",
    ),
    "english": (
        "Yes, doing that now.",
        "Alright, one moment.",
        "Sure, I'm on it.",
        "Yes, just one second.",
    ),
}

WAIT_LINES = {
    "hindi": (
        "जी, बस एक moment।",
        "एक second और, जी।",
    ),
    "english": (
        "Just a moment, please.",
        "One more second.",
    ),
}

REGISTER_LINES = {
    "search": HOLD_LINES,
    "coming": COMING_LINES,
    "ack": ACK_LINES,
    "action": ACTION_LINES,
    "neutral": WAIT_LINES,
}

FAILURE_LINES = {
    "hindi": (
        "माफ़ कीजिए, अभी system से जवाब नहीं आ पाया — एक बार फिर बताइए आपको क्या चाहिए?",
        "थोड़ी technical दिक्कत आ रही है, ज़रा एक minute में फिर पूछिए।",
    ),
    "english": (
        "I'm sorry, our system didn't respond just now — could you tell me again what you need?",
        "We're having a small technical issue, please ask me again in a minute.",
    ),
}

REPROMPT_LINES = {
    "hindi": {
        "no_transcript": (
            "Sir, आपकी आवाज़ साफ़ नहीं आ रही — क्या आप मुझे सुन पा रहे हैं?",
            "Sir, लगता है network में दिक्कत है। सुन पा रहे हैं तो ज़रा फिर से बोलिए।",
            "Sir, connection में अभी दिक्कत आ रही है — मैं आपसे थोड़ी देर बाद connect करती हूँ।",
        ),
        "idle": (
            "Sir, क्या आप line पर हैं?",
            "Sir, अगर आप अभी busy हैं तो मैं थोड़ी देर बाद call कर सकती हूँ।",
            "Sir, लगता है आप अभी available नहीं हैं — मैं आपको थोड़ी देर बाद call करती हूँ।",
        ),
    },
    "english": {
        "no_transcript": (
            "Sir, your voice isn't coming through clearly — can you hear me?",
            "Sir, there seems to be a network issue. If you can hear me, please say that again.",
            "Sir, the connection is troubling us right now — I'll connect with you a little later.",
        ),
        "idle": (
            "Sir, are you still on the line?",
            "Sir, if you're busy right now I can call you back a little later.",
            "Sir, it seems you're not available — I'll call you back a little later.",
        ),
    },
}

CLOSING_LINES = {
    "hindi": (
        "PlaceholderWorks से बात करने के लिए शुक्रिया। कुछ भी पूछना हो तो आप हमें "
        "contact at placeholder works dot com पर email कर सकते हैं, या WhatsApp पर "
        "हमारी team को message कर सकते हैं। आपका दिन शुभ हो!",
    ),
    "english": (
        "Thank you for talking to PlaceholderWorks. If you have any question you can email us "
        "at contact at placeholder works dot com, or message our team on WhatsApp. "
        "Have a lovely day!",
    ),
}

TRANSFER_FAILED_LINES = {
    "hindi": (
        "माफ़ कीजिए, मैं आपको transfer नहीं कर पाई। आप contact at placeholder works dot com "
        "पर लिख सकते हैं, या WhatsApp पर हमारी team को message कर सकते हैं।",
    ),
    "english": (
        "I'm sorry, I couldn't transfer you. You can write to us at contact at placeholder "
        "works dot com, or message our team on WhatsApp.",
    ),
}


def language_key(language) -> str:
    key = (language or "").strip().lower()
    return key if key in ("hindi", "english") else "hindi"


_BACKCHANNEL_MAX_WORDS = 6

_BACKCHANNEL_WORDS = frozenset(
    """
    हां हाँ हा जी जीहां हांजी बोलिए बोलिये बताइए बताइये कहिए कहिये ठीक है हैं
    अच्छा सही यह ये वो ओके हूँ हूं नमस्ते नमस्कार सुनिए सुनिये क्या
    ok okay yes yeah yep ya haan ji hello hi hey sure right fine
    go ahead tell say speak please
    """.split()
)

_ASSISTANT_NAMES = frozenset(
    "रिया रीया riya riyaa आरिया आर्या आरया aria arya".split()
)

_PROBLEM_WORDS = frozenset(
    """
    issue issues problem problems error failed failing decline declined stuck
    दिक्कत परेशानी समस्या गलत महंगा महँगा ज़्यादा ज्यादा नहीं अटक कटा काट
    """.split()
)

_ACTION_WORDS = frozenset(
    """
    transfer connect send share resend cancel confirm whatsapp link
    भेज भेजो भेजिए भेजना जोड़ो जोड़िए लिंक रद्द करवा करा
    """.split()
)


def _words(text: str) -> list:
    return [w for w in (w.strip(_PUNCTUATION).lower() for w in (text or "").split()) if w]


def register_of(user_text: str) -> str:
    words = _words(user_text)
    if not words:
        return "neutral"
    if len(words) <= _BACKCHANNEL_MAX_WORDS and all(
        w in _BACKCHANNEL_WORDS or w in _ASSISTANT_NAMES for w in words
    ):
        return "coming"
    unique = set(words)
    if unique & _PROBLEM_WORDS:
        return "ack"
    if unique & _ACTION_WORDS:
        return "action"
    return "search"


def register_key(register) -> str:
    key = (register or "").strip().lower()
    return key if key in REGISTER_LINES else "neutral"


def hold_pool(register, language) -> tuple:
    return REGISTER_LINES[register_key(register)][language_key(language)]


def second_pool(register, language) -> tuple:
    pools = SECOND_HOLD_LINES if register_key(register) == "search" else WAIT_LINES
    return pools[language_key(language)]


def key_of(line: str) -> str:
    return re.sub(r"\s+", " ", (line or "").strip(_PUNCTUATION)).lower()


class LinePool:

    def __init__(self):
        self._said: list = []
        self._spoken: list = []

    def remember(self, line: str) -> None:
        key = key_of(line)
        if key:
            self._said.append(key)
            self._spoken.append(line)

    def said(self, line: str) -> bool:
        return key_of(line) in self._said

    def recent(self, count: int) -> list:
        return self._spoken[-count:] if count else []

    def unused(self, pool) -> str:
        for line in pool:
            if not self.said(line):
                return line
        return ""

    def least_recent(self, pool) -> str:
        if not pool:
            return ""
        ordered = sorted(
            pool,
            key=lambda line: (
                self._said.index(key_of(line)) if key_of(line) in self._said else -1
            ),
        )
        return ordered[0]

    def pick(self, pool) -> str:
        line = self.unused(pool) or self.least_recent(pool)
        if line:
            self.remember(line)
        return line


def reprompt_line(reason: str, attempt: int, language) -> str:
    pools = REPROMPT_LINES[language_key(language)]
    lines = pools.get(reason) or pools["idle"]
    index = max(0, min(attempt - 1, len(lines) - 1))
    return lines[index]


def branded(text: str) -> str:
    import os

    return (text.replace("contact at placeholder works dot com", os.getenv("COMPANY_EMAIL_SPOKEN", "contact at placeholder works dot com"))
            .replace("PlaceholderWorks", os.getenv("COMPANY_NAME", "PlaceholderWorks")))


def closing_line(language) -> str:
    return branded(CLOSING_LINES[language_key(language)][0])


def transfer_failed_line(language) -> str:
    return branded(TRANSFER_FAILED_LINES[language_key(language)][0])
