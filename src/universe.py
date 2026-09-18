"""
Construction de l'UNIVERS de cryptos a analyser.

Sur GitHub Actions, Binance est geo-bloque (451) : par defaut on N'appelle PAS
exchangeInfo et on met binance=None (data_sources ira direct sur CoinGecko).

Optimisation cle : l'appel /coins/markets renvoie DEJA capitalisation, volume,
rang, offres et ATH. On stocke ces champs par crypto (`market`) pour que
l'analyse fondamentale n'ait AUCUN appel supplementaire a faire (ce qui evitait
les 401/429 du job quotidien).

Retour : {nom: {binance, coingecko_id, market}}.
"""
from __future__ import annotations
import requests

from src.cg import cg_get

HEADERS = {"User-Agent": "crypto-analysis-bot/1.0"}
BINANCE_INFO = "https://api.binance.com/api/v3/exchangeInfo"

STABLES = {"tether", "usd-coin", "dai", "first-digital-usd", "true-usd",
           "paypal-usd", "usdd", "frax", "ethena-usde", "binance-usd",
           "usds", "global-dollar", "usd1-wlfi", "paypal-usd"}


def binance_usdt_symbols() -> set[str]:
    try:
        r = requests.get(BINANCE_INFO, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return {s["symbol"] for s in r.json().get("symbols", [])
                if s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING"}
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] exchangeInfo Binance indisponible ({e}); mapping USDT desactive.")
        return set()


def top_markets(n: int) -> list[dict]:
    """Top n cryptos par capitalisation (un seul appel /coins/markets, jusqu'a 250)."""
    out, page = [], 1
    while len(out) < n:
        batch = cg_get("/coins/markets", {
            "vs_currency": "usd", "order": "market_cap_desc",
            "per_page": min(250, n + 20), "page": page, "sparkline": "false"})
        if not batch:
            break
        out.extend(batch)
        page += 1
        if len(batch) < 250:
            break
    return out[:n + 20]


def build_universe(cfg: dict) -> dict:
    u = cfg.get("universe", {}) or {}
    mode = u.get("mode", "list")
    use_binance = bool(cfg.get("use_binance", False))

    if mode == "list":
        # liste explicite : pas de donnees marche pre-chargees (fondamentale via API si besoin)
        return {k: dict(v, market=None) for k, v in cfg["cryptos"].items()}

    n = int(u.get("top_n", 20))
    exclude_stables = u.get("exclude_stablecoins", True)
    markets = top_markets(n)
    usdt = binance_usdt_symbols() if use_binance else set()

    universe, seen = {}, set()
    for m in markets:
        cg_id = m.get("id")
        if exclude_stables and cg_id in STABLES:
            continue
        sym = (m.get("symbol") or "").upper()
        if not sym or sym in seen or not cg_id:
            continue
        binance = None
        if use_binance:
            cand = f"{sym}USDT"
            binance = cand if (not usdt or cand in usdt) else None
        # donnees fondamentales pre-chargees (evite un appel /coins/{id} par crypto)
        market = {
            "market_cap": m.get("market_cap"), "rank": m.get("market_cap_rank"),
            "volume": m.get("total_volume"),
            "circ": m.get("circulating_supply"), "total": m.get("total_supply"),
            "maxs": m.get("max_supply"), "ath_change_pct": m.get("ath_change_percentage"),
        }
        market["vol_mcap"] = ((market["volume"] / market["market_cap"])
                              if (market["market_cap"] and market["volume"]) else None)
        universe[sym] = {"binance": binance, "coingecko_id": cg_id, "market": market}
        seen.add(sym)
        if len(universe) >= n:
            break
    print(f"Univers construit : {len(universe)} cryptos (mode top_{n}, Binance={'oui' if use_binance else 'non'}).")
    return universe
