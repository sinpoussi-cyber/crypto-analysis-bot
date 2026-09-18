"""
Moteur de backtest LONG/FLAT (adapte au spot : on est investi ou en cash, pas de vente a decouvert).

Regle : position = 1 (investi) quand le score composite >= seuil d'entree,
0 (cash) quand il repasse sous le seuil de sortie. Frais de transaction preleves
a chaque changement de position.

Metriques renvoyees : rendement total, CAGR, Sharpe et Sortino annualises,
max drawdown, taux de trades gagnants, nombre de trades, et comparaison au
buy-and-hold. Ces metriques sont l'unique juge de la qualite d'un jeu de
parametres — c'est ce qui remplace la "devinette".
"""
from __future__ import annotations
import numpy as np
import pandas as pd

TRADING_DAYS = 365   # crypto : marche 7j/7


def positions_from_score(score: pd.Series, entry: float, exit: float) -> pd.Series:
    """Hysteresis : entre a `entry`, sort a `exit` (<= entry). Evite le sur-trading."""
    pos = np.zeros(len(score))
    cur = 0
    vals = score.values
    for i, v in enumerate(vals):
        if cur == 0 and v >= entry:
            cur = 1
        elif cur == 1 and v <= exit:
            cur = 0
        pos[i] = cur
    return pd.Series(pos, index=score.index)


def run(close: pd.Series, score: pd.Series, entry: float, exit: float,
        cost: float = 0.001) -> dict:
    close = close.astype(float)
    ret = close.pct_change().fillna(0.0)
    pos = positions_from_score(score, entry, exit)
    trades = pos.diff().abs().fillna(pos.abs())
    n_trades = int(trades.sum())
    # rendement strategie : on capte le rendement du lendemain de la position d'aujourd'hui
    strat = pos.shift(1).fillna(0) * ret - trades * cost
    equity = (1 + strat).cumprod()
    bh_equity = (1 + ret).cumprod()

    def sharpe(x):
        sd = x.std()
        return float(x.mean() / sd * np.sqrt(TRADING_DAYS)) if sd > 0 else 0.0

    def sortino(x):
        dn = x[x < 0].std()
        return float(x.mean() / dn * np.sqrt(TRADING_DAYS)) if dn > 0 else 0.0

    def maxdd(eq):
        return float((eq / eq.cummax() - 1).min())

    # taux de trades gagnants (par cycle investi)
    wins = tot = 0
    inpos = False; entry_px = 0.0
    for i in range(len(pos)):
        if not inpos and pos.iloc[i] == 1:
            inpos = True; entry_px = close.iloc[i]
        elif inpos and pos.iloc[i] == 0:
            inpos = False; tot += 1
            if close.iloc[i] > entry_px:
                wins += 1
    hit = wins / tot if tot else np.nan

    years = max(len(close) / TRADING_DAYS, 1e-9)
    tot_ret = float(equity.iloc[-1] - 1)
    cagr = float(equity.iloc[-1] ** (1/years) - 1) if equity.iloc[-1] > 0 else -1.0
    return dict(
        total_return=tot_ret, cagr=cagr,
        sharpe=sharpe(strat), sortino=sortino(strat), max_drawdown=maxdd(equity),
        hit_rate=hit, n_trades=n_trades,
        bh_total_return=float(bh_equity.iloc[-1] - 1), bh_sharpe=sharpe(ret),
        exposure=float(pos.mean()),
        final_equity=float(equity.iloc[-1]),
    )
