"""MailPilot Pro: user-owned SMTP relay settings and restricted TLS transports.

No SMTP credentials are stored here or in SQLite. Connections to arbitrary
hosts/ports are intentionally not supported in the public signup edition.
"""
from __future__ import annotations
import smtplib
import socket
import ssl
from email.message import EmailMessage
from typing import NamedTuple


class Relay(NamedTuple):
    host: str
    port: int
    security: str


PROVIDERS: dict[str, Relay] = {
    'Gmail': Relay('smtp.gmail.com', 587, 'STARTTLS'),
    'Titan Email': Relay('smtp.titan.email', 465, 'SSL/TLS'),
    'Microsoft 365': Relay('smtp.office365.com', 587, 'STARTTLS'),
    'Outlook.com': Relay('smtp-mail.outlook.com', 587, 'STARTTLS'),
    'Brevo': Relay('smtp-relay.brevo.com', 587, 'STARTTLS'),
    'Yahoo Mail': Relay('smtp.mail.yahoo.com', 465, 'SSL/TLS'),
}


def provider_config(name: str) -> Relay:
    if name not in PROVIDERS:
        raise ValueError('Choose one of the supported SMTP providers.')
    return PROVIDERS[name]


def validate_sender(provider: str, username: str, sender: str) -> None:
    from core import valid_email
    provider_config(provider)
    if not username or not sender or not valid_email(sender):
        raise ValueError('Enter your SMTP username and a valid From email address.')
    # SMTP login is an email address for these providers; match it to the From
    # address so shared hosting cannot be used to forge arbitrary From headers.
    if provider != 'Brevo' and sender.lower() != username.lower():
        raise ValueError('For this provider, From email must match your SMTP login.')
    # Brevo uses a separate SMTP login; sender must be verified inside Brevo.


def _connect(provider: str, username: str, password: str, timeout: int = 15):
    if not username or not password:
        raise ValueError('Enter your own SMTP login and app password / SMTP key.')
    relay = provider_config(provider)
    ctx = ssl.create_default_context()
    if relay.security == 'SSL/TLS':
        client = smtplib.SMTP_SSL(relay.host, relay.port, timeout=timeout, context=ctx)
    else:
        client = smtplib.SMTP(relay.host, relay.port, timeout=timeout)
    try:
        if relay.security == 'STARTTLS':
            client.ehlo()
            client.starttls(context=ctx)
            client.ehlo()
        client.login(username, password)
        return client
    except Exception:
        client.close()
        raise


def test_smtp_login(provider: str, username: str, password: str, *, timeout=15) -> None:
    """Check authentication without sending an email."""
    client = _connect(provider, username, password, timeout)
    try:
        client.quit()
    except (smtplib.SMTPException, OSError):
        client.close()


def send_via_user_smtp(provider: str, username: str, password: str,
                       message: EmailMessage, *, timeout=15) -> None:
    """Send using only the logged-in user's current-session SMTP password."""
    client = _connect(provider, username, password, timeout)
    try:
        client.send_message(message)
    finally:
        try:
            client.quit()
        except (smtplib.SMTPException, OSError):
            client.close()


def friendly_error(exc: Exception) -> str:
    """Human-readable failures without exposing server response containing secrets."""
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return 'Authentication failed. Check your SMTP username and app password / key.'
    if isinstance(exc, (socket.gaierror, socket.timeout, TimeoutError, ConnectionError)):
        return 'Could not reach the SMTP server. Check the network and provider availability.'
    if isinstance(exc, (ssl.SSLError, smtplib.SMTPNotSupportedError)):
        return 'TLS encryption could not be established with this provider.'
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return 'The SMTP server refused the recipient address.'
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return 'The provider rejected your From address. Verify this sender with your provider.'
    if isinstance(exc, smtplib.SMTPException):
        return 'SMTP server rejected the request. Check provider access and sending permissions.'
    if isinstance(exc, ValueError):
        return str(exc)
    return 'SMTP operation failed. Please retry after checking your provider configuration.'