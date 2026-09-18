"""
Projection probabiliste a 30 jours — PAS une prevision de prix.

Modele : marche aleatoire geometrique (rendements log ~ i.i.d.).
- Point central = prix actuel (une marche aleatoire n'a pas de direction previsible).
- Bornes = prix_actuel * exp(+/- z * sigma * sqrt(t)), sigma = ecart-type des
  rendements log sur la fenetre recente.

La LARGEUR de l'intervalle est le message : elle quantifie l'incertitude, elle
ne dit pas si le cours montera ou descendra. Aucune direction n'est affirmee.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

Z80, Z95 = 1.2816, 1.9600


def project(close: pd.Series, horizon_days: int = 30, vol_window: int = 180) -> dict:
    close = close.astype(float)
    S0 = float(close.iloc[-1])
    lr = np.log(close / close.shift(1)).dropna().tail(vol_window)
    sigma = float(lr.std())

    def band(z):
        return S0 * np.exp(z * sigma * np.sqrt(horizon_days))

    lo95, lo80, hi80, hi95 = band(-Z95), band(-Z80), band(Z80), band(Z95)
    return dict(
        horizon=horizon_days,
        central=S0,               # prix actuel, sans biais directionnel
        daily_sigma=round(sigma, 5),
        lo95=lo95, lo80=lo80, hi80=hi80, hi95=hi95,
        lo95_pct=lo95 / S0 - 1, lo80_pct=lo80 / S0 - 1,
        hi80_pct=hi80 / S0 - 1, hi95_pct=hi95 / S0 - 1,
    )
