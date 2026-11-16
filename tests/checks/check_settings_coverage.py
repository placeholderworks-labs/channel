import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from pw_channel.settings import registry
from pw_channel.settings.registry import SETTINGS, ValidationError

ROOT = pathlib.Path(__file__).resolve().parents[2]

BOOTSTRAP = {
    "USE_DB",
    "DATABASE_URL",
    "DOCKER_DATABASE_URL",
    "DASHBOARD_ENABLED",
    "DASHBOARD_SESSION_SECRET",
    "DASHBOARD_SESSION_HOURS",
    "DASHBOARD_ADMIN_EMAIL",
    "DASHBOARD_ADMIN_PASSWORD",
    "DASHBOARD_ADMIN_NAME",
    "INTERNAL_LOG_TOKEN",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASS",
    "SMTP_SENDER",
    "DASHBOARD_PUBLIC_URL",
}

PASS, FAIL = [], []


def registry_restart_keys():
    return [k for k, s in SETTINGS.items() if s.restart]


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{(' — ' + detail) if detail else ''}")


def keys_in(path):
    text = path.read_text(encoding="utf-8")
    return [m.group(1) for m in re.finditer(r"^([A-Z][A-Z0-9_]*)=", text, re.M)]


def main():
    known = set(SETTINGS)
    print(f"\nregistry carries {len(known)} settings\n")

    for name in (".env", ".env.example"):
        path = ROOT / name
        if not path.exists():
            check(f"{name} exists", False, "missing")
            continue

        keys = keys_in(path)
        seen = set(keys)

        print(f"{name}")
        voice = sorted((seen & known) - set(registry_restart_keys()))
        check(
            "  no voice setting is in the file",
            not voice,
            f"{len(voice)} present: {voice[:6]}" if voice else "",
        )

        extra = sorted(seen - known - BOOTSTRAP)
        check(
            "  nothing in the file is unconfigurable",
            not extra,
            f"{len(extra)} extra: {extra[:6]}" if extra else "",
        )

        dupes = sorted({k for k in keys if keys.count(k) > 1})
        check("  no key is listed twice", not dupes, str(dupes) if dupes else "")

    print("\nthe catalog itself")
    unlabelled = [k for k, s in SETTINGS.items() if not s.label or not s.help]
    check(
        "  nothing renders without a label and an explanation",
        not unlabelled,
        str(unlabelled) if unlabelled else "",
    )

    dangling = [k for k, s in SETTINGS.items() if s.inherits and s.inherits not in SETTINGS]
    check(
        "  every inherited fallback points at a real setting",
        not dangling,
        str(dangling) if dangling else "",
    )

    hidden = [
        k for k, s in SETTINGS.items() if s.depends_on and s.depends_on[0] not in SETTINGS
    ]
    check(
        "  no field hides behind a setting that does not exist",
        not hidden,
        str(hidden) if hidden else "",
    )

    empty_options = [k for k, s in SETTINGS.items() if s.type == "select" and not s.options]
    check(
        "  every dropdown has options",
        not empty_options,
        str(empty_options) if empty_options else "",
    )

    grouped = {s.key for group in registry.GROUPS for s in group.settings}
    check(
        "  every setting is reachable from a group",
        grouped == known,
        str(sorted(known - grouped)) if grouped != known else "",
    )

    print("\nthe values this container is running on")
    env_now = dict(
        m.groups()
        for m in re.finditer(
            r"^([A-Z][A-Z0-9_]*)=(.*)$", ((ROOT / ".env") if (ROOT / ".env").exists() else (ROOT / ".env.example")).read_text(encoding="utf-8"), re.M
        )
    )

    rejected = []
    for key in known:
        if key not in env_now:
            continue
        try:
            registry.coerce(key, env_now[key])
        except ValidationError as e:
            rejected.append(f"{key}={env_now[key]!r} ({e})")
    check(
        "  the Settings screen accepts every value in .env",
        not rejected,
        str(rejected[:4]) if rejected else "",
    )

    print("\nthe numbers the Docs page states")
    docs = ROOT / "ui" / "src" / "pages" / "Docs.jsx"
    if not docs.exists():
        check("  Docs.jsx exists", False, "missing")
    else:
        prose = docs.read_text(encoding="utf-8")
        overrides = sum(1 for s in SETTINGS.values() if s.inherits)
        murf = SETTINGS["MURF_TTS_VOICE"].options

        claims = [
            (f"{len(known)} settings", "this service's settings count"),
            (f"{len(BOOTSTRAP)} values here", "the env-only count"),
            (f"{overrides} settings are per-channel overrides", "the override count"),
        ]
        for text, what in claims:
            check(
                f"  Docs states {what}", text in prose,
                f"expected {text!r}" if text not in prose else "",
            )

        absent = [v for v in murf if v not in prose]
        check(
            "  Docs names every Murf voice on offer",
            not absent,
            f"missing from the page: {absent}" if absent else "",
        )

        brain = ROOT.parent / "pw-llm" / "pw_llm" / "settings" / "voice_registry.py"
        if brain.exists():
            count = brain.read_text(encoding="utf-8").count("VoiceSetting(\n")
            check(
                "  Docs states the brain's settings count",
                f"{count} settings" in prose,
                f"expected {count} from the chatbot registry"
                if f"{count} settings" not in prose else "",
            )
            total = len(known) + count
            check(
                "  and the total the screen shows",
                f"{total} values" in prose,
                f"expected {total}" if f"{total} values" not in prose else "",
            )

    print(f"\n{'=' * 58}\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
        print(
            "\nThe .env files and the Settings screen must describe the same set of "
            "knobs. A setting in one and not the other is either a knob nobody can "
            "find or a value nobody can change."
        )
    return 1 if FAIL else 0


sys.exit(main())
