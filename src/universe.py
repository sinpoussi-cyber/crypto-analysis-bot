"""
Construction de l'UNIVERS de cryptos a analyser.

Deux modes (config.yaml -> section `universe`) :
  - mode: list   -> on utilise la liste explicite `cryptos` du config.
  - mode: top_n  -> on recupere dynamiquement les N premieres cryptos par
                    capitalisation (CoinGecko /coins/markets), puis on les mappe
                    aux paires USDT reellement negociables sur Binance
                    (exchangeInfo). Celles absentes de Binance gardent CoinGecko
                    en secours. Le filtre fondamental (liquidite/capitalisation)
                    ecarte ensuite les actifs trop fragiles.

"Toutes les cryptos" en pratique = l'univers liquide et negociable des top-N,
rafraichi automatiquement. Analyser des milliers de micro-jetons illiquides
serait couteux et sans valeur (ils echouent au filtre de qualite).
"""
from __future__ import annotations
import time

import requests

HEADERS = {"User-Agent": "crypto-analysis-bot/1.0"}
BINANCE_INFO = "https://api.binance.com/api/v3/exchangeInfo"
CG_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"


def binance_usdt_symbols() -> set[str]:
    """Ensemble des paires <BASE>USDT en statut TRADING sur Binance."""
    try:
        r = requests.get(BINANCE_INFO, headers=HEADERS, timeout=30)
        r.raise_for_status()
        syms = set()
        for s in r.json().get("symbols", []):
            if s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING":
                syms.add(s["symbol"])
        return syms
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] exchangeInfo Binance indisponible ({e}); mapping USDT desactive.")
        return set()


def top_markets(n: int) -> list[dict]:
    """Top n cryptos par capitalisation (CoinGecko). Exclut les stablecoins."""
    out, page = [], 1
    per = 250
    while len(out) < n:
        params = {"vs_currency": "usd", "order": "market_cap_desc",
                  "per_page": min(per, 250), "page": page, "sparkline": "false"}
        r = requests.get(CG_MARKETS, params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        page += 1
        if len(batch) < per:
            break
        time.sleep(1.0)   # respect des limites de debit
    return out[:n]


# Stablecoins a exclure (aucun interet pour une strategie directionnelle)
STABLES = {"tether", "usd-coin", "dai", "first-digital-usd", "true-usd",
           "paypal-usd", "usdd", "frax", "ethena-usde", "binance-usd"}


def build_universe(cfg: dict) -> dict:
    """Renvoie {nom: {binance: str|None, coingecko_id: str}}."""
    u = cfg.get("universe", {}) or {}
    mode = u.get("mode", "list")
    if mode == "list":
        return dict(cfg["cryptos"])

    n = int(u.get("top_n", 30))
    exclude_stables = u.get("exclude_stablecoins", True)
    markets = top_markets(n + 15)   # marge pour compenser les stablecoins ecartes
    usdt = binance_usdt_symbols()

    universe, seen = {}, set()
    for m in markets:
        cg_id = m.get("id")
        if exclude_stables and cg_id in STABLES:
            continue
        sym = (m.get("symbol") or "").upper()
        if not sym or sym in seen:
            continue
        cand = f"{sym}USDT"
        binance = cand if (not usdt or cand in usdt) else None
        # si Binance connu mais paire absente ET pas d'id CoinGecko -> on saute
        if binance is None and not cg_id:
            continue
        universe[sym] = {"binance": binance, "coingecko_id": cg_id}
        seen.add(sym)
        if len(universe) >= n:
            break
    print(f"Univers construit : {len(universe)} cryptos (mode top_{n}).")
    return universe
