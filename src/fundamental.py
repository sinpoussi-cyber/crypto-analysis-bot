"""
Analyse fondamentale (crypto) — filtre de QUALITE et de LIQUIDITE.

Metriques de marche/reseau, pas de "benefices". Source privilegiee : les donnees
DEJA recuperees par universe.build_universe (champ `market`) -> AUCUN appel API
supplementaire (c'est ce qui evitait les 401/429 du job quotidien). Repli : appel
/coins/{id} via le client partage si aucune donnee pre-chargee n'est fournie.

Renvoie un score 0..100 et un booleen `passes`.
"""
from __future__ import annotations

from src.cg import cg_get


def _score_from_market(f: dict) -> dict:
    pts, reasons = 0, []
    mc = f.get("market_cap") or 0
    if mc >= 1e10:   pts += 30; reasons.append("grande capitalisation (>10 Md$)")
    elif mc >= 1e9:  pts += 22; reasons.append("capitalisation solide (>1 Md$)")
    elif mc >= 1e8:  pts += 12; reasons.append("capitalisation moyenne (>100 M$)")
    else:            reasons.append("petite capitalisation (<100 M$) : fragile")

    vm = f.get("vol_mcap")
    if vm is not None:
        if 0.02 <= vm <= 1.0: pts += 30; reasons.append(f"liquidite saine (vol/cap={vm:.2f})")
        elif vm > 1.0:        pts += 10; reasons.append(f"volume tres eleve vs cap (vol/cap={vm:.2f})")
        else:                 pts += 5;  reasons.append(f"liquidite faible (vol/cap={vm:.2f})")

    rk = f.get("rank")
    if rk and rk <= 20:    pts += 20; reasons.append(f"top {rk} du marche")
    elif rk and rk <= 100: pts += 12; reasons.append(f"rang {rk}")
    elif rk:               pts += 4;  reasons.append(f"rang {rk} (hors top 100)")

    if f.get("maxs"): pts += 10; reasons.append("offre plafonnee (rarete)")
    else:             pts += 3;  reasons.append("offre non plafonnee")

    pts = min(pts, 100)
    return dict(score=pts, passes=bool(pts >= 55), reasons=reasons)


def analyze(cg_id: str | None, market: dict | None = None) -> dict:
    """Si `market` (pre-charge par l'univers) est fourni, aucun appel API.
    Sinon, repli : un appel /coins/{id}."""
    if market:
        s = _score_from_market(market)
        return dict(available=True, score=s["score"], passes=s["passes"],
                    reasons=s["reasons"], raw=market)
    if not cg_id:
        return dict(available=False, score=None, passes=True,
                    reasons=["pas de donnees fondamentales"], raw={})
    try:
        j = cg_get(f"/coins/{cg_id}", {"localization": "false", "tickers": "false",
                                       "market_data": "true", "community_data": "false",
                                       "developer_data": "false", "sparkline": "false"})
        md = j.get("market_data", {}) or {}
        def g(d, *ks):
            for k in ks:
                d = (d or {}).get(k) if isinstance(d, dict) else None
            return d
        mcap = g(md, "market_cap", "usd"); vol = g(md, "total_volume", "usd")
        market = dict(market_cap=mcap, rank=j.get("market_cap_rank"), volume=vol,
                      vol_mcap=(vol / mcap if (mcap and vol) else None),
                      maxs=g(md, "max_supply"))
        s = _score_from_market(market)
        return dict(available=True, score=s["score"], passes=s["passes"], reasons=s["reasons"], raw=market)
    except Exception as e:  # noqa: BLE001
        return dict(available=False, score=None, passes=True,
                    reasons=[f"fondamentale indisponible ({e})"], raw={})
