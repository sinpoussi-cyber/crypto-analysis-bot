"""
Niveaux de trade MECANIQUES (prix d'achat, objectif, stop, duree de detention).

IMPORTANT : ce ne sont PAS des predictions. Les niveaux sont derives de la
VOLATILITE (ecart-type des rendements) et non d'une anticipation de direction :

  - Prix d'achat (entree) = prix actuel (ordre au marche, reference).
  - Objectif de vente a la HAUSSE (take-profit) = prix x exp(+tp_sigma * sigma_H).
  - Seuil de vente a la BAISSE (stop-loss)      = prix x exp(-sl_sigma * sigma_H).
    ou sigma_H = ecart-type journalier x racine(horizon) : l'amplitude typique
    du mouvement sur la duree de detention.
  - Duree de detention (jours) = inversement proportionnelle a la volatilite
    annualisee (un actif calme se tient plus longtemps), bornee [hold_min, hold_max].

Ce sont des REPERES DE DISCIPLINE (gestion du risque), a ajuster selon la
tolerance de chacun. Ils sont pleinement "actionnables" surtout quand la decision
est INVESTIR ou le signal ACHAT ; sinon ils servent de niveaux de surveillance.
"""
from __future__ import annotations
import math


def compute(price: float, ind: dict, forecast: dict, decision: dict, signal: dict, cfg: dict) -> dict:
    lv = cfg.get("levels", {}) or {}
    tp_sigma = float(lv.get("tp_sigma", 1.5))   # objectif a +1.5 sigma
    sl_sigma = float(lv.get("sl_sigma", 1.0))   # stop a -1.0 sigma
    hold_k = float(lv.get("hold_k", 21))
    hold_min = int(lv.get("hold_min", 7))
    hold_max = int(lv.get("hold_max", 45))

    ann_vol = ind.get("ann_vol") or 0.6
    daily_sigma = forecast.get("daily_sigma")
    if not daily_sigma or daily_sigma <= 0:
        daily_sigma = ann_vol / math.sqrt(365)

    # duree de detention : plus l'actif est volatil, plus la fenetre est courte
    horizon = int(round(hold_k / ann_vol)) if ann_vol > 0 else hold_max
    horizon = max(hold_min, min(hold_max, horizon))

    sigma_H = daily_sigma * math.sqrt(horizon)
    entry = float(price)
    take_profit = entry * math.exp(tp_sigma * sigma_H)
    stop_loss = entry * math.exp(-sl_sigma * sigma_H)
    tp_pct = take_profit / entry - 1.0
    sl_pct = stop_loss / entry - 1.0
    rr = abs(tp_pct / sl_pct) if sl_pct != 0 else None

    actionable = bool(decision.get("action") == "INVESTIR" or signal.get("action") == "ACHAT")

    return dict(
        entry=entry, take_profit=take_profit, stop_loss=stop_loss,
        tp_pct=tp_pct, sl_pct=sl_pct, horizon_days=horizon,
        rr=(round(rr, 2) if rr else None), actionable=actionable,
        tp_sigma=tp_sigma, sl_sigma=sl_sigma,
    )
