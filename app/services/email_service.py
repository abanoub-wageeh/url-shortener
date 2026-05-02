import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from urllib.parse import quote

from app.core.config import settings


def _from_email() -> str:
    return settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME or ""


def _from_header() -> str:
    return formataddr((settings.SMTP_FROM_NAME, _from_email()))


def _ensure_smtp_configured() -> None:
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        raise RuntimeError("SMTP credentials are not configured")
    if not _from_email():
        raise RuntimeError("SMTP sender email is not configured")


def send_email(
    recipient_email: str, subject: str, text_body: str, html_body: str
) -> None:
    _ensure_smtp_configured()

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = _from_header()
    message["To"] = recipient_email
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    if settings.SMTP_USE_SSL:
        server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT)
    else:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)

    with server:
        if settings.SMTP_USE_STARTTLS and not settings.SMTP_USE_SSL:
            server.starttls()
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(message)


def send_verification_email(
    recipient_email: str, recipient_name: str, token: str
) -> None:
    verification_link = (
        f"{settings.APP_BASE_URL.rstrip('/')}"
        f"/api/v1/auth/verify-email?token={quote(token)}"
    )
    subject = "Verify your email"
    text_body = (
        f"Hi {recipient_name},\n\n"
        "Thanks for signing up. Verify your email by opening this link:\n"
        f"{verification_link}\n\n"
        "If you did not create this account, you can ignore this email."
    )
    html_body = f"""
    <p>Hi {recipient_name},</p>
    <p>Thanks for signing up. Verify your email by clicking the link below:</p>
    <p><a href=\"{verification_link}\">Verify email</a></p>
    <p>If you did not create this account, you can ignore this email.</p>
    """
    send_email(recipient_email, subject, text_body, html_body)


def send_password_reset_email(
    recipient_email: str, recipient_name: str, token: str
) -> None:
    reset_link = None
    if settings.FRONTEND_RESET_PASSWORD_URL:
        reset_link = (
            f"{settings.FRONTEND_RESET_PASSWORD_URL.rstrip('/')}?token={quote(token)}"
        )

    subject = "Reset your password"
    text_body = (
        f"Hi {recipient_name},\n\n"
        "Use the token below to reset your password with the reset password endpoint:\n"
        f"{token}\n\n"
        f"Endpoint: {settings.APP_BASE_URL.rstrip('/')}/api/v1/auth/reset-password\n"
    )
    html_body = f"""
    <p>Hi {recipient_name},</p>
    <p>Use the token below to reset your password with the reset password endpoint:</p>
    <p><code>{token}</code></p>
    <p>Endpoint: <code>{settings.APP_BASE_URL.rstrip('/')}/api/v1/auth/reset-password</code></p>
    """

    if reset_link:
        text_body += f"\nIf you have a frontend page configured, you can also open:\n{reset_link}\n"
        html_body += f'<p><a href="{reset_link}">Open reset page</a></p>'

    send_email(recipient_email, subject, text_body, html_body)
