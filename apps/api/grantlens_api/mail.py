import smtplib
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Protocol


@dataclass
class Mail:
    to: str
    subject: str
    text: str
    html: str
    headers: dict[str, str] = field(default_factory=dict)


class Mailer(Protocol):
    def send(self, mail: Mail) -> None: ...


def _message(mail: Mail, sender: str) -> EmailMessage:
    # A long URL header (List-Unsubscribe) has no fold point; at the default 78-column limit the
    # library would turn it into an RFC 2047 encoded-word, which mail clients don't accept there.
    msg = EmailMessage(policy=policy.default.clone(max_line_length=998))
    msg["From"], msg["To"], msg["Subject"] = sender, mail.to, mail.subject
    msg["Date"], msg["Message-ID"] = formatdate(localtime=False), make_msgid(domain="grantlens")
    for k, v in mail.headers.items():
        msg[k] = v
    msg.set_content(mail.text)
    msg.add_alternative(mail.html, subtype="html")
    return msg


class SmtpMailer:
    def __init__(self, host: str, port: int, sender: str, user: str = "", password: str = "",
                 starttls: bool = True):
        self.host, self.port, self.sender = host, port, sender
        self.user, self.password, self.starttls = user, password, starttls

    def send(self, mail: Mail) -> None:
        with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
            if self.starttls:
                smtp.starttls()
            if self.user:
                smtp.login(self.user, self.password)
            smtp.send_message(_message(mail, self.sender))


class FileMailer:
    """Development backend: writes each email to <dir>/*.eml instead of sending anything."""

    def __init__(self, directory: str, sender: str):
        self.dir, self.sender = Path(directory), sender
        self.dir.mkdir(parents=True, exist_ok=True)

    def send(self, mail: Mail) -> None:
        stamp = formatdate(localtime=False).replace(" ", "_").replace(":", "")
        name = f"{stamp}-{mail.to.replace('@', '_at_')}.eml"
        (self.dir / name).write_bytes(bytes(_message(mail, self.sender)))


class MemoryMailer:
    """Test backend."""

    def __init__(self):
        self.sent: list[Mail] = []

    def send(self, mail: Mail) -> None:
        self.sent.append(mail)


def get_mailer(config) -> Mailer:
    backend = config.get("MAIL_BACKEND", "file")
    sender = config.get("MAIL_FROM", "GrantLens <alerts@localhost>")
    if backend == "smtp":
        return SmtpMailer(
            config["SMTP_HOST"], config.get("SMTP_PORT", 587), sender,
            config.get("SMTP_USER", ""), config.get("SMTP_PASSWORD", ""),
            config.get("SMTP_STARTTLS", True),
        )
    if backend == "memory":
        return config["MAIL_MEMORY"]
    return FileMailer(config.get("MAIL_OUTBOX", "outbox"), sender)
