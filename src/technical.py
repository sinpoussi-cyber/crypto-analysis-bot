"""
Analyse technique — 5 indicateurs PARAMETRABLES.

Chaque indicateur expose :
  - une fonction de calcul (Series -> Series)
  - une fonction de signal directionnel -> Series de {+1, 0, -1}
    (+1 = haussier, -1 = baissier, 0 = neutre)

Les parametres (fenetres, seuils) ne sont PAS figes : ils sont fournis par
l'optimiseur walk-forward (src/optimize.py) et stockes dans state/params_state.json.
C'est ce qui permet le reentrainement hebdomadaire.

Indicateurs : Moyennes mobiles, RSI, MACD, Stochastique, Bandes de Bollinger.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


# ---------- calculs bruts ----------
def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def rsi(close: pd.Series, n: int) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100/(1+rs)


def macd(close: pd.Series, fast: int, slow: int, signal: int):
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig, line - sig


def stochastic(df: pd.DataFrame, k: int, d: int, smooth: int):
    low = df["low"].rolling(k).min()
    high = df["high"].rolling(k).max()
    raw = 100 * (df["close"] - low) / (high - low).replace(0, np.nan)
    k_line = raw.rolling(smooth).mean()
    d_line = k_line.rolling(d).mean()
    return k_line, d_line


def bollinger(close: pd.Series, n: int, k: float):
    mid = sma(close, n)
    sd = close.rolling(n).std()
    up, low = mid + k*sd, mid - k*sd
    pctb = (close - low) / (up - low).replace(0, np.nan)   # position 0..1 dans le canal
    return up, mid, low, pctb


# ---------- signaux directionnels {+1,0,-1} ----------
def sig_ma(close, fast, slow):
    f, s = sma(close, fast), sma(close, slow)
    out = pd.Series(0, index=close.index)
    out[f > s] = 1
    out[f < s] = -1
    return out


def sig_rsi(close, n, low, high):
    r = rsi(close, n)
    out = pd.Series(0, index=close.index)
    out[r < low] = 1       # survente -> biais haussier (rebond)
    out[r > high] = -1     # surachat -> biais baissier
    return out


def sig_macd(close, fast, slow, signal):
    _, _, hist = macd(close, fast, slow, signal)
    out = pd.Series(0, index=close.index)
    out[hist > 0] = 1
    out[hist < 0] = -1
    return out


def sig_stoch(df, k, d, smooth, low, high):
    kl, dl = stochastic(df, k, d, smooth)
    out = pd.Series(0, index=df.index)
    out[(kl < low) & (kl > dl)] = 1     # survente + croisement haussier
    out[(kl > high) & (kl < dl)] = -1   # surachat + croisement baissier
    return out


def sig_boll(close, n, k):
    up, mid, low, pctb = bollinger(close, n, k)
    out = pd.Series(0, index=close.index)
    out[close <= low] = 1     # sous la bande basse -> survente
    out[close >= up] = -1     # sur la bande haute -> surachat
    return out


# ---------- assemblage ----------
DEFAULT_PARAMS = {
    "ma":    {"fast": 20, "slow": 50},
    "rsi":   {"n": 14, "low": 30, "high": 70},
    "macd":  {"fast": 12, "slow": 26, "signal": 9},
    "stoch": {"k": 14, "d": 3, "smooth": 3, "low": 20, "high": 80},
    "boll":  {"n": 20, "k": 2.0},
}


def all_signals(df: pd.DataFrame, params: dict, enabled: dict | None = None) -> pd.DataFrame:
    """Renvoie un DataFrame des 5 signaux {+1,0,-1}. `enabled` desactive un
    indicateur declare defaillant (met sa colonne a 0)."""
    close = df["close"]
    p = params
    sigs = pd.DataFrame(index=df.index)
    sigs["ma"] = sig_ma(close, p["ma"]["fast"], p["ma"]["slow"])
    sigs["rsi"] = sig_rsi(close, p["rsi"]["n"], p["rsi"]["low"], p["rsi"]["high"])
    sigs["macd"] = sig_macd(close, p["macd"]["fast"], p["macd"]["slow"], p["macd"]["signal"])
    sigs["stoch"] = sig_stoch(df, p["stoch"]["k"], p["stoch"]["d"], p["stoch"]["smooth"],
                              p["stoch"]["low"], p["stoch"]["high"])
    sigs["boll"] = sig_boll(close, p["boll"]["n"], p["boll"]["k"])
    if enabled:
        for k, on in enabled.items():
            if not on and k in sigs.columns:
                sigs[k] = 0    # indicateur defaillant -> neutralise
    return sigs.fillna(0)


def composite(df: pd.DataFrame, params: dict, enabled: dict | None = None) -> pd.Series:
    """Score composite dans [-1,1] = moyenne des indicateurs actifs."""
    sigs = all_signals(df, params, enabled)
    active = [c for c in sigs.columns if not (enabled and not enabled.get(c, True))]
    if not active:
        return pd.Series(0.0, index=df.index)
    return sigs[active].mean(axis=1)
