"""Submitter email notifications (stdlib smtplib). Never raises into the caller."""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

log = logging.getLogger("stratindex.notify")


def smtp_config():
    cfg = {k: (os.environ.get(k) or "").strip() for k in
           ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_TLS")}
    if not cfg["SMTP_HOST"] or not cfg["SMTP_FROM"]:
        return None
    cfg["SMTP_TLS"] = (cfg["SMTP_TLS"] or "starttls").lower()
    cfg["SMTP_PORT"] = int(cfg["SMTP_PORT"] or (465 if cfg["SMTP_TLS"] == "ssl" else 587))
    return cfg


def send(to: str, subject: str, body: str) -> tuple[bool, str]:
    """Returns (sent, status_text). Skips cleanly when SMTP is not configured."""
    cfg = smtp_config()
    if cfg is None:
        log.warning("SMTP not configured — skipped email to %s (%s)", to, subject)
        return False, "skipped: SMTP not configured"
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = cfg["SMTP_FROM"], to, subject
    msg.set_content(body)
    try:
        ctx = ssl.create_default_context()
        if cfg["SMTP_TLS"] == "ssl":
            server = smtplib.SMTP_SSL(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=15, context=ctx)
        else:
            server = smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=15)
        with server:
            if cfg["SMTP_TLS"] == "starttls":
                server.starttls(context=ctx)
            if cfg["SMTP_USER"]:
                server.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
            server.send_message(msg)
        log.info("emailed %s: %s", to, subject)
        return True, f"sent to {to}"
    except Exception as e:  # noqa: BLE001
        log.error("email to %s failed: %s", to, e)
        return False, f"error: {type(e).__name__}: {e}"[:300]


def approved_email(name, slug, position, field, base_url):
    url = f"{base_url.rstrip('/')}/race/{slug}"
    pos = f"P{position} of {field}" if position else "pending its first backtest"
    return (f"Your strategy \"{name}\" is on the StratIndex grid",
            f"Hi,\n\nGood news: your strategy \"{name}\" was approved and has joined the StratIndex Grand Prix.\n\n"
            f"After the re-run it is currently {pos} (ranked by out-of-sample Sharpe).\n\n"
            f"See its metrics, equity curve and reproduction steps:\n{url}\n\n"
            "Rankings update as new candles arrive. Not investment advice.\n\n— StratIndex\n")


def rejected_email(name):
    return (f"Your StratIndex submission \"{name}\"",
            f"Hi,\n\nThanks for submitting \"{name}\" to the StratIndex Grand Prix. After review we won't be adding it "
            "to the grid this time. You're welcome to adjust the rules and submit again.\n\nThanks for taking part,\n— StratIndex\n")
