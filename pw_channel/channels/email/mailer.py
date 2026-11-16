import html
import logging
import os
from pathlib import Path

from pw_channel.channels.email.providers.base import EmailMessageIn
from pw_channel.channels.email.providers.registry import provider

logger = logging.getLogger(__name__)

def brand() -> str:
    return f"{os.getenv('COMPANY_NAME', 'PlaceholderWorks')} Voice Studio"


ACCENT = "#e5145f"
LOGO_CID = "pw-logo"
LOGO_PATHS = (
    Path(__file__).resolve().parents[2] / "static" / "dashboard" / "pw-logo.png",
    Path(__file__).resolve().parents[3] / "ui" / "public" / "pw-logo.png",
)

HEADER = (
    '<tr><td style="padding:22px 28px 16px;border-bottom:1px solid #f2ecee;">'
    f'<img src="cid:{LOGO_CID}" alt="logo" height="52" style="display:block;height:52px;width:auto;border:0;">'
    f'<div style="margin-top:8px;font-size:13px;font-weight:600;color:{ACCENT};letter-spacing:.2px;">Voice Studio</div>'
    "</td></tr>"
)


def _logo() -> bytes | None:
    for path in LOGO_PATHS:
        if path.is_file():
            return path.read_bytes()
    return None


def dashboard_url() -> str:
    return os.getenv("DASHBOARD_PUBLIC_URL", "").strip() or "http://localhost:8420/dashboard"


def is_configured() -> bool:
    return provider().configured()


def send(to: str, subject: str, text: str, html_body: str) -> tuple[bool, str | None]:
    logo = _logo()
    if logo is None:
        html_body = html_body.replace(
            HEADER,
            f'<tr><td style="background:{ACCENT};padding:22px 28px;color:#ffffff;font-size:18px;font-weight:600;">{brand()}</td></tr>',
        )
    result = provider().send(EmailMessageIn(
        to=to, subject=subject, text=text, html=html_body, sender_name=brand(),
        inline_images={LOGO_CID: logo} if logo is not None else {},
    ))
    return result.ok, result.error or None


def _render(*, heading: str, intro: str, email: str, temp_password: str, footer: str) -> tuple[str, str]:
    url = dashboard_url()
    text = (
        f"{heading}\n\n{intro}\n\n"
        f"Sign in: {url}\n"
        f"Email: {email}\n"
        f"Temporary password: {temp_password}\n\n"
        "You will be asked to choose a new password the first time you sign in.\n\n"
        f"{footer}\n\n{brand()}\n"
    )
    e = html.escape
    body = f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f7f4f5;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1f2937;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f7f4f5;padding:32px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #ece4e7;">
{HEADER}
<tr><td style="padding:28px;">
<h1 style="margin:0 0 12px;font-size:20px;color:#111827;">{e(heading)}</h1>
<p style="margin:0 0 20px;font-size:15px;line-height:1.55;">{e(intro)}</p>
<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;background:#fdf3f7;border:1px solid #f5d3e0;border-radius:8px;margin:0 0 20px;">
<tr><td style="padding:14px 18px;font-size:14px;line-height:1.7;">
<div><span style="color:#6b7280;">Email</span><br><strong>{e(email)}</strong></div>
<div style="margin-top:8px;"><span style="color:#6b7280;">Temporary password</span><br>
<code style="font-family:SFMono-Regular,Menlo,Consolas,monospace;font-size:15px;background:#ffffff;border:1px solid #f5d3e0;border-radius:4px;padding:3px 8px;">{e(temp_password)}</code></div>
</td></tr></table>
<p style="margin:0 0 24px;"><a href="{e(url)}" style="display:inline-block;background:{ACCENT};color:#ffffff;text-decoration:none;font-weight:600;font-size:15px;padding:12px 22px;border-radius:8px;">Sign in to {brand()}</a></p>
<p style="margin:0 0 8px;font-size:13px;color:#4b5563;">You will be asked to choose a new password the first time you sign in.</p>
<p style="margin:0;font-size:13px;color:#4b5563;">{e(footer)}</p>
</td></tr>
<tr><td style="padding:16px 28px;border-top:1px solid #f2ecee;font-size:12px;color:#9ca3af;">{brand()} · <a href="{e(url)}" style="color:{ACCENT};text-decoration:none;">{e(url)}</a></td></tr>
</table>
</td></tr></table>
</body></html>"""
    return text, body


def send_invite(
    email: str, name: str, temp_password: str, role_label: str, invited_by: str
) -> tuple[bool, str | None]:
    text, body = _render(
        heading=f"Hi {name or email}, you've been invited",
        intro=f"{invited_by} has given you {role_label} access to {brand()}, "
        "the PlaceholderWorks voice console.",
        email=email,
        temp_password=temp_password,
        footer="If you weren't expecting this invitation, you can ignore this email.",
    )
    return send(email, f"You're invited to {brand()}", text, body)


def send_password_reset(
    email: str, name: str, temp_password: str, requested_by: str | None = None
) -> tuple[bool, str | None]:
    intro = (
        f"{requested_by} reset your {brand()} password."
        if requested_by
        else f"Someone asked to reset the password for your {brand()} account."
    )
    text, body = _render(
        heading=f"Hi {name or email}, your password was reset",
        intro=intro + " Your old password no longer works; use the temporary one below.",
        email=email,
        temp_password=temp_password,
        footer="If you didn't ask for this, sign in and change your password, and tell an admin.",
    )
    return send(email, f"Your {brand()} password was reset", text, body)


def send_login_code(email: str, name: str, code: str, minutes: int) -> tuple[bool, str | None]:
    url = dashboard_url()
    text = (
        f"Hi {name or email},\n\nYour {brand()} sign-in code is {code}.\n"
        f"It expires in {minutes} minutes and works once.\n\n"
        "If you did not just try to sign in, change your password and tell an admin.\n\n"
        f"{brand()}\n"
    )
    e = html.escape
    body = f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f7f4f5;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1f2937;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f7f4f5;padding:32px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #ece4e7;">
{HEADER}
<tr><td style="padding:28px;">
<h1 style="margin:0 0 12px;font-size:20px;color:#111827;">Your sign-in code</h1>
<p style="margin:0 0 18px;font-size:15px;line-height:1.55;">Hi {e(name or email)}, enter this code to finish signing in.</p>
<div style="font-family:SFMono-Regular,Menlo,Consolas,monospace;font-size:32px;letter-spacing:10px;font-weight:700;color:#111827;background:#fdf3f7;border:1px solid #f5d3e0;border-radius:10px;padding:16px 0;text-align:center;margin:0 0 18px;">{e(code)}</div>
<p style="margin:0 0 8px;font-size:13px;color:#4b5563;">It expires in {minutes} minutes and works once.</p>
<p style="margin:0;font-size:13px;color:#4b5563;">If you did not just try to sign in, change your password and tell an admin.</p>
</td></tr>
<tr><td style="padding:16px 28px;border-top:1px solid #f2ecee;font-size:12px;color:#9ca3af;">{brand()} · <a href="{e(url)}" style="color:{ACCENT};text-decoration:none;">{e(url)}</a></td></tr>
</table></td></tr></table></body></html>"""
    return send(email, f"{code} is your {brand()} sign-in code", text, body)


def send_reset_link(email: str, name: str, link: str, minutes: int) -> tuple[bool, str | None]:
    text = (
        f"Hi {name or email},\n\nSomeone asked to reset the password for your {brand()} account.\n"
        f"Set a new password here (the link works once, for {minutes} minutes):\n{link}\n\n"
        "If you didn't ask for this, ignore this email. Your current password still works.\n\n"
        f"{brand()}\n"
    )
    e = html.escape
    body = f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f7f4f5;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1f2937;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f7f4f5;padding:32px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #ece4e7;">
{HEADER}
<tr><td style="padding:28px;">
<h1 style="margin:0 0 12px;font-size:20px;color:#111827;">Reset your password</h1>
<p style="margin:0 0 20px;font-size:15px;line-height:1.55;">Hi {e(name or email)}, someone asked to reset the password for your {brand()} account. Choose a new one with the button below.</p>
<p style="margin:0 0 20px;"><a href="{e(link)}" style="display:inline-block;background:{ACCENT};color:#ffffff;text-decoration:none;font-weight:600;font-size:15px;padding:12px 22px;border-radius:8px;">Set a new password</a></p>
<p style="margin:0 0 8px;font-size:13px;color:#4b5563;">The link works once, for {minutes} minutes.</p>
<p style="margin:0;font-size:13px;color:#4b5563;">If you didn't ask for this, ignore this email. Your current password still works.</p>
</td></tr>
</table></td></tr></table></body></html>"""
    return send(email, f"Reset your {brand()} password", text, body)


def _card(title: str, intro: str, rows: list[tuple[str, str]], button: tuple[str, str] | None, foot: str) -> str:
    e = html.escape
    facts = "".join(
        f'<tr><td style="padding:6px 0;font-size:13px;color:#6b7280;width:120px;vertical-align:top;">{e(k)}</td>'
        f'<td style="padding:6px 0;font-size:14px;color:#111827;">{e(v)}</td></tr>'
        for k, v in rows if v
    )
    action = (
        f'<p style="margin:20px 0 0;"><a href="{e(button[1])}" style="display:inline-block;background:{ACCENT};'
        f'color:#ffffff;text-decoration:none;font-weight:600;font-size:15px;padding:12px 22px;border-radius:8px;">{e(button[0])}</a></p>'
        if button else ""
    )
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f7f4f5;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1f2937;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f7f4f5;padding:32px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #ece4e7;">
{HEADER}
<tr><td style="padding:28px;">
<h1 style="margin:0 0 12px;font-size:20px;color:#111827;">{e(title)}</h1>
<p style="margin:0 0 16px;font-size:15px;line-height:1.55;">{e(intro)}</p>
<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-top:1px solid #f2ecee;padding-top:8px;">{facts}</table>
{action}
<p style="margin:20px 0 0;font-size:13px;color:#4b5563;">{e(foot)}</p>
</td></tr>
</table></td></tr></table></body></html>"""


def send_access_request(email: str, name: str, *, request: dict, link: str) -> tuple[bool, str | None]:
    who = request["name"] or request["email"]
    rows = [
        ("Who", f"{who} ({request['email']})"),
        ("Role", request.get("roleLabel") or request["role"]),
        ("Wants", request["permissionLabel"]),
        ("From", request["page"]),
        ("Note", request["note"]),
    ]
    text = (
        f"Hi {name or email},\n\n{who} asked for the '{request['permissionLabel']}' permission on {brand()}.\n"
        + "".join(f"{k}: {v}\n" for k, v in rows if v)
        + f"\nReview it on the Team page: {link}\n\n{brand()}\n"
    )
    body = _card(
        "New access request",
        f"Hi {name or email}, {who} asked for a permission their role does not include.",
        rows,
        ("Review on the Team page", link),
        "Grant it by giving their role the permission, or moving them to a role that has it, then mark the request granted.",
    )
    return send(email, f"{who} asked for '{request['permissionLabel']}' on {brand()}", text, body)


def send_access_decision(email: str, name: str, *, request: dict, link: str) -> tuple[bool, str | None]:
    granted = request["status"] == "granted"
    outcome = "granted" if granted else "not granted"
    intro = (
        f"Hi {name or email}, your request for '{request['permissionLabel']}' was {outcome}."
        + (" Sign out and back in to pick it up." if granted else " Ask your admin if you still need it.")
    )
    text = f"{intro}\n\nDecided by: {request['resolvedBy']}\n\n{brand()}\n{link}\n"
    body = _card(
        "Access granted" if granted else "Access request closed",
        intro,
        [("Permission", request["permissionLabel"]), ("Decided by", request["resolvedBy"])],
        ("Open the dashboard", link) if granted else None,
        "This is an automatic message from the dashboard.",
    )
    return send(email, f"Your {brand()} access request was {outcome}", text, body)
