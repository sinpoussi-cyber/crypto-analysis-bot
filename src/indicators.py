"""
Indicateurs d'analyse technique — implementations pandas/numpy pures (aucune
dependance TA-Lib, plus simple a installer sur GitHub Actions).

Tous prennent une Series de cours de cloture (index = dates) et renvoient soit
une Series, soit un dict de valeurs scalaires pour la derniere date.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def sma(close: pd.Series, n: int) -> pd.Series:
    return close.rolling(n).mean()


def ema(close: pd.Series, n: int) -> pd.Series:
    return close.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False).mean()
    hist = line - sig
    return line, sig, hist


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    mid = sma(close, n)
    sd = close.rolling(n).std()
    return mid + k * sd, mid, mid - k * sd


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def snapshot(df: pd.DataFrame) -> dict:
    """Calcule l'ensemble des indicateurs et renvoie un dict de valeurs recentes."""
    close = df.set_index("date")["close"].astype(float)
    S0 = close.iloc[-1]
    ma20, ma50, ma200 = sma(close, 20), sma(close, 50), sma(close, 200)
    r = rsi(close, 14)
    ml, ms, mh = macd(close)
    bu, bm, bl = bollinger(close)
    a = atr(df.set_index("date"))
    lr = np.log(close / close.shift(1)).dropna()
    ann_vol = lr.std() * np.sqrt(365)

    def pct(days):
        if len(close) <= days:
            return np.nan
        return close.iloc[-1] / close.iloc[-1 - days] - 1

    maxprice = close.cummax()
    dd = (close / maxprice - 1).iloc[-1]

    def val(s):
        v = s.iloc[-1]
        return float(v) if pd.notna(v) else None

    return dict(
        price=float(S0),
        ma20=val(ma20), ma50=val(ma50), ma200=val(ma200),
        rsi=val(r), macd=val(ml), macd_signal=val(ms), macd_hist=val(mh),
        boll_up=val(bu), boll_mid=val(bm), boll_low=val(bl),
        atr=val(a), atr_pct=(val(a) / S0 if val(a) else None),
        ann_vol=float(ann_vol),
        ret_7d=(float(pct(7)) if pd.notna(pct(7)) else None),
        ret_30d=(float(pct(30)) if pd.notna(pct(30)) else None),
        ret_90d=(float(pct(90)) if pd.notna(pct(90)) else None),
        drawdown=float(dd),
        above_ma50=(bool(S0 > val(ma50)) if val(ma50) else None),
        above_ma200=(bool(S0 > val(ma200)) if val(ma200) else None),
    )
