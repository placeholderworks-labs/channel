import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from pw_channel.channels.voice.text.hindi_numbers import spell_out_digits

PASS, FAIL = [], []


def check(name, got, want):
    ok = got == want
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f" — got {got!r}"))


check("a landline with a hyphen is read digit by digit",
      spell_out_digits("011-43131313 पर कॉल करें।"),
      "शून्य एक एक, चार तीन एक तीन एक तीन एक तीन पर कॉल करें।")
check("a ten-digit mobile is read digit by digit",
      spell_out_digits("number 9876543210 है"), "number नौ आठ सात छह पांच चार तीन दो एक शून्य है")
check("a +91 number keeps its groups as pauses",
      spell_out_digits("+91 98765 43210"), "प्लस नौ एक, नौ आठ सात छह पांच, चार तीन दो एक शून्य")
check("a toll-free number is read digit by digit",
      spell_out_digits("1800-103-3434"), "एक आठ शून्य शून्य, एक शून्य तीन, तीन चार तीन चार")
check("a number read back in English digit words is said in Hindi",
      spell_out_digits("nine eight seven six five four three two one zero"),
      "नौ आठ सात छह पांच चार तीन दो एक शून्य")
check("an amount stays an amount", spell_out_digits("12,499 रुपये"), "बारह हज़ार चार सौ निन्यानवे रुपये")
check("a plain amount without commas stays an amount", spell_out_digits("15000 रुपये"), "पंद्रह हज़ार रुपये")
check("a year stays a year", spell_out_digits("2026 में"), "दो हज़ार छब्बीस में")
check("an ISO date is not taken for a phone number",
      spell_out_digits("2026-11-18"), "दो हज़ार छब्बीस-ग्यारह-अठारह")
check("a PNR glued to letters is left alone", spell_out_digits("PNR AB12345678"), "PNR AB12345678")

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
