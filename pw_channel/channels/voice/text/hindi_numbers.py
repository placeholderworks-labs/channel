import re

_ONES = (
    "शून्य", "एक", "दो", "तीन", "चार", "पांच", "छह", "सात", "आठ", "नौ",
    "दस", "ग्यारह", "बारह", "तेरह", "चौदह", "पंद्रह", "सोलह", "सत्रह", "अठारह", "उन्नीस",
    "बीस", "इक्कीस", "बाईस", "तेईस", "चौबीस", "पच्चीस", "छब्बीस", "सत्ताईस", "अट्ठाईस", "उनतीस",
    "तीस", "इकतीस", "बत्तीस", "तैंतीस", "चौंतीस", "पैंतीस", "छत्तीस", "सैंतीस", "अड़तीस", "उनतालीस",
    "चालीस", "इकतालीस", "बयालीस", "तैंतालीस", "चवालीस", "पैंतालीस", "छियालीस", "सैंतालीस", "अड़तालीस", "उनचास",
    "पचास", "इक्यावन", "बावन", "तिरपन", "चौवन", "पचपन", "छप्पन", "सत्तावन", "अट्ठावन", "उनसठ",
    "साठ", "इकसठ", "बासठ", "तिरसठ", "चौंसठ", "पैंसठ", "छियासठ", "सड़सठ", "अड़सठ", "उनहत्तर",
    "सत्तर", "इकहत्तर", "बहत्तर", "तिहत्तर", "चौहत्तर", "पचहत्तर", "छिहत्तर", "सतहत्तर", "अठहत्तर", "उनासी",
    "अस्सी", "इक्यासी", "बयासी", "तिरासी", "चौरासी", "पचासी", "छियासी", "सत्तासी", "अट्ठासी", "नवासी",
    "नब्बे", "इक्यानवे", "बानवे", "तिरानवे", "चौरानवे", "पंचानवे", "छियानवे", "सत्तानवे", "अट्ठानवे", "निन्यानवे",
)

_HUNDRED = "सौ"
_THOUSAND = "हज़ार"
_LAKH = "लाख"
_CRORE = "करोड़"

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

_DIGIT_RUN_RULE = re.compile(
    r"(?<![A-Za-z0-9])[0-9०-९](?:[,٬]?[0-9०-९])*(?![A-Za-z0-9])"
)


def to_hindi_words(n: int) -> str:
    if n < 0:
        return f"ऋण {to_hindi_words(-n)}"
    if n < 100:
        return _ONES[n]

    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thousand, n = divmod(n, 1_000)
    hundred, remainder = divmod(n, 100)

    parts = []
    if crore:
        parts.append(f"{to_hindi_words(crore)} {_CRORE}")
    if lakh:
        parts.append(f"{to_hindi_words(lakh)} {_LAKH}")
    if thousand:
        parts.append(f"{to_hindi_words(thousand)} {_THOUSAND}")
    if hundred:
        parts.append(f"{_ONES[hundred]} {_HUNDRED}")
    if remainder:
        parts.append(_ONES[remainder])

    return " ".join(parts)


_PHONE_RULE = re.compile(
    r"(?<![A-Za-z0-9०-९])\+?[0-9०-९](?:[ \-.]?[0-9०-९]){7,14}(?![A-Za-z0-9०-९])"
)
_ISO_DATE_RULE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ENGLISH_DIGITS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
_ENGLISH_DIGIT_RUN_RULE = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|oh)(?:[\s,\-]+(?:zero|one|two|three|four|five|six|seven|eight|nine|oh)){5,}\b",
    re.IGNORECASE,
)


def spell_phone_number(raw: str) -> str:
    digits = raw.translate(_DEVANAGARI_DIGITS)
    groups = re.split(r"[ \-.]+", digits.lstrip("+"))
    words = ", ".join(" ".join(_ONES[int(ch)] for ch in group) for group in groups if group)
    return ("प्लस " if digits.startswith("+") else "") + words


def _spell_phones(text: str) -> str:
    def _phone(match: re.Match) -> str:
        found = match.group(0)
        if _ISO_DATE_RULE.match(found.translate(_DEVANAGARI_DIGITS)):
            return found
        return spell_phone_number(found)

    text = _PHONE_RULE.sub(_phone, text)

    def _english(match: re.Match) -> str:
        words = re.findall(r"[a-z]+", match.group(0).lower())
        return " ".join(_ONES[0 if w in ("zero", "oh") else _ENGLISH_DIGITS.index(w)] for w in words)

    return _ENGLISH_DIGIT_RUN_RULE.sub(_english, text)


def spell_out_digits(text: str) -> str:

    def _replace(match: re.Match) -> str:
        digits = match.group(0).translate(_DEVANAGARI_DIGITS).replace(",", "").replace("٬", "")
        if not digits:
            return match.group(0)
        return to_hindi_words(int(digits))

    return _DIGIT_RUN_RULE.sub(_replace, _spell_phones(text))
