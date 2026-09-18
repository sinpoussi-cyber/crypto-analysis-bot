"""
Client CoinGecko partage : cle demo (gratuite), throttling et backoff sur 429.

Pourquoi : l'API publique CoinGecko exige desormais une cle demo (sinon 401),
et limite le debit (sinon 429). Ce module centralise :
  - l'entete d'authentification `x-cg-demo-api-key` si COINGECKO_API_KEY est definie,
  - un intervalle minimal entre appels (throttle),
  - des reessais avec backoff exponentiel sur 429 (respecte Retry-After).

Toutes les requetes CoinGecko du projet passent par cg_get().
"""
from __future__ import annotations
import os
import time

import requests

BASE = os.environ.get("COINGECKO_API_BASE", "https://api.coingecko.com/api/v3")
HEADERS_BASE = {"User-Agent": "crypto-analysis-bot/1.0", "accept": "application/json"}
MIN_INTERVAL = float(os.environ.get("COINGECKO_MIN_INTERVAL", "1.6"))  # secondes entre appels
MAX_RETRIES = int(os.environ.get("COINGECKO_MAX_RETRIES", "5"))

_last_call = [0.0]  # horodatage du dernier appel (mutable pour cloture)


def _headers() -> dict:
    h = dict(HEADERS_BASE)
    key = os.environ.get("COINGECKO_API_KEY")
    if key:
        h["x-cg-demo-api-key"] = key
    return h


def cg_get(path: str, params: dict | None = None) -> dict | list:
    """GET CoinGecko avec throttle + backoff. `path` commence par '/'."""
    url = BASE + path
    for attempt in range(MAX_RETRIES):
        # throttle : respecter l'intervalle minimal entre deux appels
        wait = MIN_INTERVAL - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        r = requests.get(url, params=params, headers=_headers(), timeout=40)
        _last_call[0] = time.time()
        if r.status_code == 429:
            retry_after = float(r.headers.get("Retry-After", 0) or 0)
            back = max(retry_after, MIN_INTERVAL * (2 ** attempt))
            print(f"[CG] 429 sur {path} -> attente {back:.1f}s (essai {attempt+1}/{MAX_RETRIES})")
            time.sleep(back)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"CoinGecko: 429 persistant sur {path} apres {MAX_RETRIES} essais")
