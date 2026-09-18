"""
Client CoinGecko partage : cle demo (gratuite), throttling, backoff sur 429,
et DIAGNOSTIC clair des erreurs (affiche la vraie cause dans le log).
"""
from __future__ import annotations
import os
import time

import requests

BASE = os.environ.get("COINGECKO_API_BASE", "https://api.coingecko.com/api/v3")
HEADERS_BASE = {"User-Agent": "crypto-analysis-bot/1.0", "accept": "application/json"}
MIN_INTERVAL = float(os.environ.get("COINGECKO_MIN_INTERVAL", "2.2"))  # secondes entre appels
MAX_RETRIES = int(os.environ.get("COINGECKO_MAX_RETRIES", "5"))

_last_call = [0.0]


def _headers() -> dict:
    h = dict(HEADERS_BASE)
    key = os.environ.get("COINGECKO_API_KEY")
    if key:
        h["x-cg-demo-api-key"] = key
    return h


def _key_present() -> bool:
    return bool(os.environ.get("COINGECKO_API_KEY"))


def cg_get(path, params=None):
    """GET CoinGecko avec throttle + backoff. `path` commence par '/'."""
    url = BASE + path
    for attempt in range(MAX_RETRIES):
        wait = MIN_INTERVAL - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.get(url, params=params, headers=_headers(), timeout=40)
        except requests.RequestException as e:
            print("[CG] erreur reseau sur " + path + " : " + str(e))
            time.sleep(MIN_INTERVAL * (2 ** attempt))
            continue
        _last_call[0] = time.time()

        if r.status_code == 200:
            return r.json()

        body = (r.text or "")[:200]
        if r.status_code == 429:
            retry_after = float(r.headers.get("Retry-After", 0) or 0)
            back = max(retry_after, MIN_INTERVAL * (2 ** attempt))
            print("[CG] 429 (debit) sur " + path
                  + " -> attente " + format(back, ".1f") + "s"
                  + " (essai " + str(attempt + 1) + "/" + str(MAX_RETRIES) + ")")
            time.sleep(back)
            continue
        if r.status_code in (401, 403):
            hint = ("cle absente : ajoute le secret COINGECKO_API_KEY"
                    if not _key_present()
                    else "cle refusee : verifie la valeur de COINGECKO_API_KEY (format CG-...)")
            raise RuntimeError("CoinGecko " + str(r.status_code) + " sur " + path
                               + " -> " + hint + ". Reponse: " + body)
        raise RuntimeError("CoinGecko " + str(r.status_code) + " sur " + path
                           + ". Reponse: " + body)

    raise RuntimeError("CoinGecko: 429 persistant sur " + path
                       + " apres " + str(MAX_RETRIES) + " essais (debit depasse).")
