"""
Modele de PREDICTION walk-forward + mesure honnete de son pouvoir predictif.

Cible : signe du rendement a `horizon` jours (hausse = 1, baisse = 0).
Variables : les 5 indicateurs techniques transformes en features continues
(RSI, histogramme MACD, %K stochastique, %B Bollinger, ecart aux MM, momentum).
Modele : regression logistique standardisee (scikit-learn), robuste et rapide.

Point crucial : on evalue le modele HORS-ECHANTILLON par validation walk-forward
(TimeSeriesSplit) et on renvoie son AUC. Si l'AUC est proche de 0,5, le modele
n'a AUCUN pouvoir predictif reel : la couche de decision l'IGNORE alors, au lieu
de faire semblant. C'est la difference entre une prediction mesuree et une devinette.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from src import technical as T

try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import roc_auc_score
    HAS_SK = True
except Exception:  # noqa: BLE001
    HAS_SK = False


def build_features(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    close = df["close"]
    f = pd.DataFrame(index=df.index)
    f["rsi"] = T.rsi(close, params["rsi"]["n"]) / 100.0
    _, _, hist = T.macd(close, params["macd"]["fast"], params["macd"]["slow"], params["macd"]["signal"])
    f["macd_hist"] = hist / close
    kl, dl = T.stochastic(df, params["stoch"]["k"], params["stoch"]["d"], params["stoch"]["smooth"])
    f["stoch_k"] = kl / 100.0
    f["stoch_kd"] = (kl - dl) / 100.0
    _, mid, _, pctb = T.bollinger(close, params["boll"]["n"], params["boll"]["k"])
    f["pctb"] = pctb
    f["ma_gap"] = (T.sma(close, params["ma"]["fast"]) - T.sma(close, params["ma"]["slow"])) / close
    f["mom10"] = close.pct_change(10)
    f["mom20"] = close.pct_change(20)
    return f


def train_and_skill(df: pd.DataFrame, params: dict, horizon: int = 5) -> dict:
    """Entraine le modele et mesure son AUC hors-echantillon. Renvoie aussi la
    probabilite de hausse pour la DERNIERE observation (proba_up)."""
    if not HAS_SK:
        return dict(available=False, reason="scikit-learn absent", auc=None, proba_up=None, skill=False)

    feats = build_features(df, params)
    fwd = df["close"].shift(-horizon) / df["close"] - 1
    y = (fwd > 0).astype(int)
    data = feats.copy()
    data["y"] = y
    data = data.dropna()
    if len(data) < 250:
        return dict(available=False, reason="donnees insuffisantes", auc=None, proba_up=None, skill=False)

    X = data.drop(columns="y").values
    yv = data["y"].values

    # validation walk-forward
    aucs = []
    tss = TimeSeriesSplit(n_splits=5)
    for tr, te in tss.split(X):
        if len(np.unique(yv[tr])) < 2 or len(np.unique(yv[te])) < 2:
            continue
        mdl = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, C=1.0))
        mdl.fit(X[tr], yv[tr])
        p = mdl.predict_proba(X[te])[:, 1]
        aucs.append(roc_auc_score(yv[te], p))
    auc = float(np.mean(aucs)) if aucs else None

    # modele final entraine sur tout l'historique disponible, proba pour aujourd'hui
    final = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, C=1.0))
    final.fit(X, yv)
    last_row = build_features(df, params).iloc[[-1]].dropna()
    proba_up = float(final.predict_proba(last_row.values)[:, 1][0]) if len(last_row) else None

    skill = bool(auc is not None and auc >= 0.55)   # seuil d'edge minimal
    return dict(available=True, auc=(round(auc, 3) if auc else None),
                proba_up=(round(proba_up, 3) if proba_up else None),
                skill=skill, horizon=horizon,
                reason=("edge mesure" if skill else "AUC proche de 0.5 : pas d'edge fiable"))
