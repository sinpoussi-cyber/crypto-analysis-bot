"""
Construction de l'UNIVERS de cryptos a analyser.

Deux composantes combinees (config -> section `universe`) :
  - TOP N par capitalisation (top_n) : les plus grosses / etablies.
  - TOP K les plus VOLATILES (volatile_n) : selectionnees dans un pool plus large
    (volatile_pool) via un indicateur de volatilite (amplitude des variations
    recentes), au-dela du top capitalisation.
L'union (dedoublonnee) forme l'univers final.

Sur GitHub Actions, Binance est geo-bloque (451) : par defaut binance=None et
data_sources va direct sur CoinGecko. L'appel /coins/markets renvoie DEJA
capitalisation, volume, rang, offres et variations -> stockees par crypto
(`market`) pour que la fondamentale ne fasse AUCUN appel supplementaire.

Retour : {nom: {binance, coingecko_id, market}}.
"""
from __future__ import annotations
import requests

from src.cg import cg_get

HEADERS = {"User-Agent": "crypto-analysis-bot/1.0"}
BINANCE_INFO = "https://api.binance.com/api/v3/exchangeInfo"

STABLES = {"tether", "usd-coin", "dai", "first-digital-usd", "true-usd",
           "paypal-usd", "usdd", "frax", "ethena-usde", "binance-usd",
           "usds", "global-dollar", "usd1-wlfi", "usdt0", "susds", "blackrock-usd"}


def binance_usdt_symbols() -> set[str]:
    try:
        r = requests.get(BINANCE_INFO, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return {s["symbol"] for s in r.json().get("symbols", [])
                if s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING"}
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] exchangeInfo Binance indisponible ({e}); mapping USDT desactive.")
        return set()


def fetch_pool(pool_size: int) -> list[dict]:
    """Recupere un pool de marches (capitalisation desc) AVEC les variations
    24h/7j/30j, pour pouvoir classer par volatilite. Pagination par 250."""
    out, page = [], 1
    while len(out) < pool_size:
        batch = cg_get("/coins/markets", {
            "vs_currency": "usd", "order": "market_cap_desc",
            "per_page": 250, "page": page, "sparkline": "false",
            "price_change_percentage": "24h,7d,30d"})
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 250:
            break
        page += 1
    return out[:pool_size]


def _chg(m: dict, key: str):
    v = m.get(f"price_change_percentage_{key}_in_currency")
    if v is None and key == "24h":
        v = m.get("price_change_percentage_24h")
    return v


def _vol_proxy(m: dict) -> float:
    """Indicateur de volatilite (proxy, sans historique) : amplitude ponderee des
    variations recentes. Le court terme pese plus (swings recents)."""
    c24, c7, c30 = _chg(m, "24h"), _chg(m, "7d"), _chg(m, "30d")
    s = 0.0
    if c24 is not None: s += 0.5 * abs(c24)
    if c7 is not None:  s += 0.3 * abs(c7)
    if c30 is not None: s += 0.2 * abs(c30)
    return s


def _market_dict(m: dict) -> dict:
    md = {
        "market_cap": m.get("market_cap"), "rank": m.get("market_cap_rank"),
        "volume": m.get("total_volume"),
        "circ": m.get("circulating_supply"), "total": m.get("total_supply"),
        "maxs": m.get("max_supply"), "ath_change_pct": m.get("ath_change_percentage"),
        "chg_24h": _chg(m, "24h"), "chg_7d": _chg(m, "7d"), "chg_30d": _chg(m, "30d"),
    }
    md["vol_mcap"] = ((md["volume"] / md["market_cap"])
                      if (md["market_cap"] and md["volume"]) else None)
    md["vol_proxy"] = round(_vol_proxy(m), 2)
    return md


def build_universe(cfg: dict) -> dict:
    u = cfg.get("universe", {}) or {}
    mode = u.get("mode", "list")
    use_binance = bool(cfg.get("use_binance", False))

    if mode == "list":
        return {k: dict(v, market=None) for k, v in cfg["cryptos"].items()}

    top_n = int(u.get("top_n", 50))
    volatile_n = int(u.get("volatile_n", 0))
    volatile_pool = int(u.get("volatile_pool", 300))
    exclude_stables = bool(u.get("exclude_stablecoins", True))

    pool_size = max(top_n, volatile_pool if volatile_n > 0 else top_n)
    pool = fetch_pool(pool_size)
    usdt = binance_usdt_symbols() if use_binance else set()

    # nettoyage : stablecoins ecartes, symbole/id valides, sans doublon de symbole
    clean, seen = [], set()
    for m in pool:
        cg_id = m.get("id")
        sym = (m.get("symbol") or "").upper()
        if not sym or not cg_id or sym in seen:
            continue
        if exclude_stables and cg_id in STABLES:
            continue
        seen.add(sym)
        clean.append((sym, cg_id, m))

    cap_set = clean[:top_n]                       # top capitalisation
    cap_ids = {sym for sym, _, _ in cap_set}

    vol_add = []
    if volatile_n > 0:
        ranked = sorted(clean, key=lambda t: _vol_proxy(t[2]), reverse=True)
        for sym, cg_id, m in ranked:
            if sym in cap_ids:
                continue
            vol_add.append((sym, cg_id, m))
            if len(vol_add) >= volatile_n:
                break

    def _entry(sym, cg_id, m, tag):
        binance = None
        if use_binance:
            cand = f"{sym}USDT"
            binance = cand if (not usdt or cand in usdt) else None
        md = _market_dict(m); md["tag"] = tag
        return sym, {"binance": binance, "coingecko_id": cg_id, "market": md}

    universe = {}
    for sym, cg_id, m in cap_set:
        k, v = _entry(sym, cg_id, m, "cap")
        universe[k] = v
    for sym, cg_id, m in vol_add:
        k, v = _entry(sym, cg_id, m, "volatil")
        universe[k] = v

    print(f"Univers construit : {len(universe)} cryptos "
          f"(top {top_n} cap + {len(vol_add)} volatiles, Binance={'oui' if use_binance else 'non'}).")
    return universe
