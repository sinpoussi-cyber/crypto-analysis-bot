"""
Analyse fondamentale (crypto) — filtre de QUALITE et de LIQUIDITE.

Note importante : une crypto n'a pas de "benefices" comme une action. La
fondamentale ici = metriques de marche et de reseau recuperees via l'API publique
CoinGecko : capitalisation, rang, volume/capitalisation (liquidite), distance a
l'ATH, dynamique de l'offre, activite developpeur et communaute quand disponibles.

Ce n'est pas une valorisation : c'est un GARDE-FOU. Il ecarte les actifs trop
petits, trop illiquides ou structurellement fragiles avant toute prise de position.
Renvoie un score 0..100 et un booleen `pass` (filtre franchi).
"""
from __future__ import annotations
import requests

URL = "https://api.coingecko.com/api/v3/coins/{id}"
HEADERS = {"User-Agent": "crypto-analysis-bot/1.0"}


def fetch_fundamentals(cg_id: str) -> dict:
    params = {"localization": "false", "tickers": "false", "market_data": "true",
              "community_data": "true", "developer_data": "true", "sparkline": "false"}
    r = requests.get(URL.format(id=cg_id), params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    j = r.json()
    md = j.get("market_data", {}) or {}
    dev = j.get("developer_data", {}) or {}
    com = j.get("community_data", {}) or {}

    def g(d, *ks):
        for k in ks:
            d = (d or {}).get(k) if isinstance(d, dict) else None
        return d

    mcap = g(md, "market_cap", "usd")
    vol = g(md, "total_volume", "usd")
    ath_change = g(md, "ath_change_percentage", "usd")  # % sous l'ATH (negatif)
    return dict(
        market_cap=mcap, rank=j.get("market_cap_rank"),
        volume=vol, vol_mcap=(vol / mcap if (mcap and vol) else None),
        ath_change_pct=ath_change,
        circ=g(md, "circulating_supply"), total=g(md, "total_supply"), maxs=g(md, "max_supply"),
        dev_stars=dev.get("stars"), dev_commits=dev.get("commit_count_4_weeks"),
        twitter=com.get("twitter_followers"),
    )


def score(f: dict) -> dict:
    pts, reasons = 0, []

    # Capitalisation (taille -> robustesse)
    mc = f.get("market_cap") or 0
    if mc >= 1e10:   pts += 30; reasons.append("grande capitalisation (>10 Md$)")
    elif mc >= 1e9:  pts += 22; reasons.append("capitalisation solide (>1 Md$)")
    elif mc >= 1e8:  pts += 12; reasons.append("capitalisation moyenne (>100 M$)")
    else:            reasons.append("petite capitalisation (<100 M$) : fragile")

    # Liquidite : volume / capitalisation
    vm = f.get("vol_mcap")
    if vm is not None:
        if 0.02 <= vm <= 1.0: pts += 30; reasons.append(f"liquidite saine (vol/cap={vm:.2f})")
        elif vm > 1.0:        pts += 10; reasons.append(f"volume tres eleve vs cap (vol/cap={vm:.2f}) : possible agitation")
        else:                 pts += 5;  reasons.append(f"liquidite faible (vol/cap={vm:.2f})")

    # Rang de marche
    rk = f.get("rank")
    if rk and rk <= 20:   pts += 20; reasons.append(f"top {rk} du marche")
    elif rk and rk <= 100: pts += 12; reasons.append(f"rang {rk}")
    elif rk:               pts += 4;  reasons.append(f"rang {rk} (hors top 100)")

    # Offre : plafond connu = rarete
    if f.get("maxs"):     pts += 10; reasons.append("offre plafonnee (rarete)")
    else:                 pts += 3;  reasons.append("offre non plafonnee")

    # Activite developpeur (bonus si dispo)
    if f.get("dev_commits"):
        if f["dev_commits"] > 0: pts += 10; reasons.append(f"depot actif ({f['dev_commits']} commits/4 sem.)")

    pts = min(pts, 100)
    return dict(score=pts, passes=bool(pts >= 55), reasons=reasons)


def analyze(cg_id: str) -> dict:
    try:
        f = fetch_fundamentals(cg_id)
    except Exception as e:  # noqa: BLE001
        return dict(available=False, score=None, passes=True, reasons=[f"fondamentale indisponible ({e})"],
                    raw={})
    s = score(f)
    return dict(available=True, score=s["score"], passes=s["passes"], reasons=s["reasons"], raw=f)
