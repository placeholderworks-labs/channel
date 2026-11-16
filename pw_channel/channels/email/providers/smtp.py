import logging
import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from pw_channel.channels.email.providers.base import EmailMessageIn, EmailProvider, EmailResult

logger = logging.getLogger(__name__)

TIMEOUT_SECS = 15


class SmtpEmail(EmailProvider):
    name = "smtp"

    def settings(self) -> dict:
        port = os.getenv("SMTP_PORT", "").strip()
        return {
            "host": os.getenv("SMTP_HOST", "").strip(),
            "port": int(port) if port.isdigit() else 587,
            "user": os.getenv("SMTP_USER", "").strip(),
            "password": os.getenv("SMTP_PASS", ""),
            "sender": os.getenv("EMAIL_SENDER", "").strip() or os.getenv("SMTP_SENDER", "").strip() or os.getenv("SMTP_USER", "").strip(),
            "ssl": os.getenv("SMTP_SSL", "").strip().lower() in ("1", "true", "yes"),
        }

    def configured(self) -> bool:
        current = self.settings()
        return bool(current["host"] and current["sender"])

    def send(self, message: EmailMessageIn) -> EmailResult:
        current = self.settings()
        if not self.configured():
            return EmailResult(ok=False, error="SMTP is not configured")
        mail = EmailMessage()
        mail["Subject"] = message.subject
        mail["From"] = formataddr((message.sender_name or os.getenv("COMPANY_NAME", ""), current["sender"]))
        mail["To"] = message.to
        message_id = make_msgid(domain=current["sender"].split("@")[-1])
        mail["Message-ID"] = message_id
        for key, value in message.headers.items():
            mail[key] = value
        mail.set_content(message.text)
        if message.html:
            mail.add_alternative(message.html, subtype="html")
            for cid, data in message.inline_images.items():
                mail.get_payload()[1].add_related(data, "image", "png", cid=f"<{cid}>")
        try:
            connect = smtplib.SMTP_SSL if current["ssl"] else smtplib.SMTP
            with connect(current["host"], current["port"], timeout=TIMEOUT_SECS) as smtp:
                smtp.ehlo()
                if not current["ssl"]:
                    smtp.starttls()
                    smtp.ehlo()
                if current["user"]:
                    smtp.login(current["user"], current["password"])
                smtp.send_message(mail)
        except (smtplib.SMTPException, OSError) as error:
            logger.warning(f"[email] could not send '{message.subject}' to {message.to}: {type(error).__name__}: {error}")
            return EmailResult(ok=False, error=f"{type(error).__name__}: {error}")
        logger.info(f"[email] sent '{message.subject}' to {message.to}")
        return EmailResult(ok=True, message_id=message_id)
