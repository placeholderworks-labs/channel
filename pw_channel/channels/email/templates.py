import html
import os

from pw_sdk import config as client_config

DEFAULT_TEMPLATES = {
    "cart_followup": {
        "subject": "Your {company} booking is waiting",
        "text": "Hi {name},\n\nYou left {summary} unfinished. Pick up where you left off: {link}\n\nReference: {reference_id}\n\nTo stop these emails: {unsubscribe}",
        "html": (
            "<p>Hi {name},</p><p>You left <b>{summary}</b> unfinished.</p>"
            '<p><a href="{link}" style="display:inline-block;padding:12px 20px;background:#111;color:#fff;'
            'text-decoration:none;border-radius:6px">Continue</a></p><p style="color:#666">Reference: {reference_id}</p>'
            '<p style="font-size:12px;color:#999"><a href="{unsubscribe}">Unsubscribe</a></p>'
        ),
    },
}


def template(name: str) -> dict:
    custom = (client_config.current().get("email.templates") or {}).get(name)
    found = {**DEFAULT_TEMPLATES.get(name, {}), **(custom or {})}
    if not found.get("subject"):
        raise KeyError(name)
    return found


def render(name: str, values: dict) -> tuple[str, str, str]:
    found = template(name)
    values = {"company": os.getenv("COMPANY_NAME", ""), **values}
    escaped = {key: html.escape(str(value)) if key not in ("link", "unsubscribe") else value for key, value in values.items()}
    subject = found["subject"].format(**values)
    text = found.get("text", "").format(**values)
    body = found.get("html", "").format(**escaped)
    return subject, text, body
