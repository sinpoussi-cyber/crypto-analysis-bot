"""
Signal technique MECANIQUE et TRANSPARENT.

Ce n'est PAS une prevision. C'est un score composite, borne dans [-1, +1],
agregeant plusieurs indicateurs classiques selon des regles fixes et visibles.
Chaque composante est documentee pour que la note explique POURQUOI le signal
penche dans un sens — jamais "le cours va monter", mais "les indicateurs sont
majoritairement haussiers aujourd'hui".

Traduction en action :
    score >= buy_threshold  -> "Achat" (biais technique haussier)
    score <= sell_threshold -> "Vente" (biais technique baissier)
    sinon                   -> "Conservation" (pas de biais net)
"""
from __future__ import annotations


def compute(ind: dict, buy_th: float, sell_th: float) -> dict:
    comps: list[tuple[str, float, str]] = []  # (nom, contribution, explication)
    p = ind["price"]

    # 1) Tendance vs MM50
    if ind.get("ma50"):
        if p > ind["ma50"]:
            comps.append(("Tendance MM50", +1, "cours au-dessus de la moyenne 50 jours (tendance porteuse)"))
        else:
            comps.append(("Tendance MM50", -1, "cours sous la moyenne 50 jours (tendance faible)"))

    # 2) Tendance de fond vs MM200
    if ind.get("ma200"):
        if p > ind["ma200"]:
            comps.append(("Tendance MM200", +1, "cours au-dessus de la moyenne 200 jours (tendance de fond haussiere)"))
        else:
            comps.append(("Tendance MM200", -1, "cours sous la moyenne 200 jours (tendance de fond baissiere)"))

    # 3) RSI — surachat / survente
    rsi = ind.get("rsi")
    if rsi is not None:
        if rsi < 30:
            comps.append(("RSI", +1, f"RSI {rsi:.0f} en zone de survente (rebond technique possible)"))
        elif rsi > 70:
            comps.append(("RSI", -1, f"RSI {rsi:.0f} en zone de surachat (essoufflement possible)"))
        else:
            comps.append(("RSI", 0, f"RSI {rsi:.0f} en zone neutre"))

    # 4) MACD — momentum
    mh = ind.get("macd_hist")
    if mh is not None:
        if mh > 0:
            comps.append(("MACD", +1, "histogramme MACD positif (momentum haussier)"))
        else:
            comps.append(("MACD", -1, "histogramme MACD negatif (momentum baissier)"))

    # 5) Position dans les bandes de Bollinger
    if ind.get("boll_low") and ind.get("boll_up"):
        if p <= ind["boll_low"]:
            comps.append(("Bollinger", +1, "cours sur la bande inferieure (potentiellement survendu)"))
        elif p >= ind["boll_up"]:
            comps.append(("Bollinger", -1, "cours sur la bande superieure (potentiellement surachete)"))
        else:
            comps.append(("Bollinger", 0, "cours dans le canal de Bollinger"))

    # 6) Momentum 30 jours
    r30 = ind.get("ret_30d")
    if r30 is not None:
        if r30 > 0.05:
            comps.append(("Momentum 30j", +1, f"performance 30 jours de {r30*100:+.0f}% (dynamique positive)"))
        elif r30 < -0.05:
            comps.append(("Momentum 30j", -1, f"performance 30 jours de {r30*100:+.0f}% (dynamique negative)"))
        else:
            comps.append(("Momentum 30j", 0, f"performance 30 jours de {r30*100:+.0f}% (etale)"))

    weights = [c[1] for c in comps]
    score = sum(weights) / len(weights) if weights else 0.0

    if score >= buy_th:
        action, label = "ACHAT", "Biais technique haussier"
    elif score <= sell_th:
        action, label = "VENTE", "Biais technique baissier"
    else:
        action, label = "CONSERVATION", "Pas de biais technique net"

    return dict(
        score=round(score, 3),
        action=action,
        label=label,
        components=[{"nom": n, "poids": w, "explication": e} for n, w, e in comps],
    )
