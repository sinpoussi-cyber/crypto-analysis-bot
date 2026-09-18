"""
Couche de DECISION : "on investit seulement quand tout converge".

Combine 4 conditions, chacune devant etre verte pour un signal INVESTIR :

  1. TECHNIQUE   : score composite (indicateurs actifs, parametres optimises) >= seuil
                   ET la strategie composite a montre un edge en validation.
  2. FONDAMENTAL : filtre qualite/liquidite franchi (capitalisation, liquidite, rang...).
  3. PREDICTION  : le modele a un pouvoir predictif MESURE (AUC >= 0.55) ET sa
                   proba de hausse >= 0.55. Si le modele n'a pas d'edge mesure,
                   cette condition est NEUTRE (ni bloc, ni feu vert) et signalee :
                   on n'investit jamais sur une prediction non validee.
  4. RISQUE      : volatilite dans une plage acceptable (garde-fou de sizing).

Sortie : action dans {INVESTIR, CONSERVER, EVITER} + le detail de chaque feu.
"""
from __future__ import annotations


def decide(name, comp_score, tech_edge, fund, model, ann_vol, thresholds) -> dict:
    entry = thresholds["buy_threshold"]
    gates = {}

    # 1. Technique
    tech_ok = bool(comp_score >= entry and tech_edge)
    gates["technique"] = dict(ok=tech_ok, score=round(float(comp_score), 3),
                              edge_valide=bool(tech_edge))

    # 2. Fondamental
    fund_ok = bool(fund.get("passes", True))
    gates["fondamental"] = dict(ok=fund_ok, score=fund.get("score"))

    # 3. Prediction (neutre si pas d'edge mesure)
    if model.get("skill"):
        pred_ok = bool((model.get("proba_up") or 0) >= 0.55)
        pred_state = "vert" if pred_ok else "rouge"
    else:
        pred_ok = True          # neutre : ne bloque pas, mais ne valide pas seul
        pred_state = "neutre (modele sans edge mesure -> ignore)"
    gates["prediction"] = dict(ok=pred_ok, etat=pred_state,
                               auc=model.get("auc"), proba_up=model.get("proba_up"))

    # 4. Risque
    risk_ok = bool(ann_vol is not None and ann_vol <= 1.5)   # <150%/an : au-dela, tres extreme
    gates["risque"] = dict(ok=risk_ok, vol_annualisee=(round(ann_vol, 2) if ann_vol else None))

    invest = tech_ok and fund_ok and pred_ok and risk_ok
    # distinguer EVITER (fondamental/risque en echec) de CONSERVER (juste pas de signal technique)
    if invest:
        action = "INVESTIR"
    elif not fund_ok or not risk_ok:
        action = "EVITER"
    else:
        action = "CONSERVER"

    return dict(action=action, gates=gates,
                convergence=f"{sum(g['ok'] for g in gates.values())}/4 feux verts")
