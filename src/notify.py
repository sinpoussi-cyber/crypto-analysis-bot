"""
Envoi de la note : Telegram (recommande, gratuit) et/ou email (SMTP).
Chaque canal est optionnel et actif selon config.yaml + variables d'environnement.
"""
from __future__ import annotations
import os
import smtplib
import ssl
from email.mime.text import MIMEText

import requests


def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        print("[WARN] Telegram : identifiants absents, envoi ignore.")
        return False
    # Telegram limite a 4096 caracteres -> on decoupe si besoin.
    ok = True
    for i in range(0, len(text), 3900):
        chunk = text[i:i + 3900]
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown",
                  "disable_web_page_preview": True},
            timeout=30,
        )
        if r.status_code != 200:
            print(f"[WARN] Telegram a repondu {r.status_code}: {r.text[:200]}")
            ok = False
    return ok


def send_email(text: str, subject: str) -> bool:
    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    pwd = os.environ.get("SMTP_PASSWORD")
    to = os.environ.get("EMAIL_TO")
    if not (host and user and pwd and to):
        print("[WARN] Email : configuration SMTP absente, envoi ignore.")
        return False
    port = int(os.environ.get("SMTP_PORT", "587"))
    msg = MIMEText(text, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(user, pwd)
            s.sendmail(user, [to], msg.as_string())
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] envoi email echoue : {e}")
        return False
