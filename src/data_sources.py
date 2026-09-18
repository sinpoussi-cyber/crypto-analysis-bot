"""
Recuperation des cours quotidiens.

Source primaire : API publique Binance (klines) — aucune cle requise.
Source de secours : API publique CoinGecko (market_chart) pour les cryptos
absentes de Binance (ex. GRAM) ou si Binance echoue.

Retourne toujours un DataFrame trie : colonnes [date, open, high, low, close, volume].
"""
from __future__ import annotations
import time
from datetime import datetime, timezone, timedelta

import pandas as pd
import requests

BINANCE_URL = "https://api.binance.com/api/v3/klines"
COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/{id}/market_chart"
HEADERS = {"User-Agent": "crypto-analysis-bot/1.0"}


def _from_binance(symbol: str, days: int) -> pd.DataFrame:
    start_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    rows = []
    while True:
        params = {"symbol": symbol, "interval": "1d", "startTime": start_ts, "limit": 1000}
        r = requests.get(BINANCE_URL, params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows.extend(batch)
        start_ts = batch[-1][6] + 1
        if len(batch) < 1000:
            break
        time.sleep(0.2)
    if not rows:
        raise RuntimeError(f"Binance n'a renvoye aucune donnee pour {symbol}")
    df = pd.DataFrame(rows, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "qv", "trades", "tb", "tq", "ig"])
    df["date"] = pd.to_datetime(df["open_time"], unit="ms", utc=True).dt.tz_localize(None)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df[["date", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def _from_coingecko(cg_id: str, days: int) -> pd.DataFrame:
    params = {"vs_currency": "usd", "days": days, "interval": "daily"}
    r = requests.get(COINGECKO_URL.format(id=cg_id), params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    prices = data.get("prices", [])
    vols = dict((int(t), v) for t, v in data.get("total_volumes", []))
    if not prices:
        raise RuntimeError(f"CoinGecko n'a renvoye aucune donnee pour {cg_id}")
    df = pd.DataFrame(prices, columns=["ts", "close"])
    df["date"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.tz_localize(None).dt.normalize()
    df["volume"] = df["ts"].map(lambda t: vols.get(int(t), float("nan")))
    # CoinGecko ne donne que le close en daily -> OHLC approxime par le close
    df["open"] = df["close"]; df["high"] = df["close"]; df["low"] = df["close"]
    df = df.drop_duplicates("date")
    return df[["date", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def fetch(name: str, cfg: dict, days: int) -> pd.DataFrame:
    """Recupere l'historique d'une crypto. cfg = {binance: str|None, coingecko_id: str}."""
    binance = cfg.get("binance")
    cg = cfg.get("coingecko_id")
    if binance:
        try:
            return _from_binance(binance, days)
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] {name}: Binance a echoue ({e}); bascule sur CoinGecko.")
    if cg:
        return _from_coingecko(cg, days)
    raise RuntimeError(f"{name}: aucune source disponible (ni Binance ni CoinGecko).")
