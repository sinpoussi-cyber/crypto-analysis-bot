"""
Job QUOTIDIEN : lit les parametres optimises (state), calcule les 5 indicateurs,
la fondamentale, la prediction et la DECISION a 4 feux, redige la note (IA) et
l'envoie (Telegram/email) + archive dans reports/.

Il N'OPTIMISE PAS : il applique les parametres du dernier reentrainement
hebdomadaire (src/retrain). Usage : python -m src.main
"""
from __future__ import annotations
import datetime as dt
import os
import pathlib
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import (data_sources, technical as T, indicators, signals, forecast,  # noqa: E402
                 fundamental, model as ML, decision, state as ST, ai_note, notify, universe)

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_payload(cfg: dict) -> dict:
    today = dt.date.today().isoformat()
    days = cfg.get("history_days", 400)
    vol_window = cfg.get("vol_window", 180)
    thr = cfg["signal"]
    st = ST.load()
    cryptos = universe.build_universe(cfg)

    out = []
    for name, meta in cryptos.items():
        try:
            df = data_sources.fetch(name, meta, days)
        except Exception as e:  # noqa: BLE001
            print(f"[ERREUR] {name}: {e}. Ignoree.")
            continue

        tuned = ST.get_for(st, name)
        params, enabled = tuned["params"], tuned["enabled"]

        # 5 indicateurs -> score composite avec parametres optimises
        comp = T.composite(df, params, enabled)
        comp_now = float(comp.iloc[-1])
        ind = indicators.snapshot(df)                 # valeurs lisibles pour la note
        # Signal mecanique TRANSPARENT ACHAT/CONSERVATION/VENTE (regles visibles)
        sig = signals.compute(ind, thr["buy_threshold"], thr["sell_threshold"])
        tech_edge = bool(tuned.get("composite_valid", {}).get("beats_bh", False)
                         or (tuned.get("composite_valid", {}).get("sharpe") or 0) > 0.5)

        # fondamentale
        fund = fundamental.analyze(meta.get("coingecko_id")) if meta.get("coingecko_id") else \
            dict(available=False, score=None, passes=True, reasons=["pas d'id CoinGecko"])

        # prediction : soit re-mesuree ici, soit lue depuis l'etat hebdo
        mstate = tuned.get("model") or {}
        if mstate.get("auc") is not None:
            mdl = dict(available=True, auc=mstate.get("auc"), skill=mstate.get("skill"),
                       proba_up=mstate.get("proba_up"), reason=mstate.get("reason"))
        else:
            mdl = ML.train_and_skill(df, params, horizon=cfg.get("predict_horizon", 5))

        # projection (intervalle, pas une prevision)
        fc = forecast.project(df.set_index("date")["close"], 30, vol_window)

        # DECISION a 4 feux
        dec = decision.decide(name, comp_now, tech_edge, fund, mdl, ind.get("ann_vol"), thr)

        out.append(dict(name=name, last_date=str(df["date"].iloc[-1].date()),
                        indicators=ind, params=params, enabled=enabled,
                        composite=round(comp_now, 3), tech_edge=tech_edge,
                        signal=sig, fundamental=fund, model=mdl, forecast=fc, decision=dec,
                        tuned_on=tuned.get("updated"), from_default=tuned.get("from_default")))
        print(f"  {name:5} sig={sig['action']:12} | decision={dec['action']:9} "
              f"({dec['convergence']}) comp={comp_now:+.2f} fond={fund.get('score')} AUC={mdl.get('auc')}")
    return dict(date=today, cryptos=out)


def summary_table(payload: dict) -> str:
    rows = ["",
            "| Crypto | Signal tech. | Décision | Feux | Composite | Fond. | AUC | Proj.30j 95% |",
            "|---|---|---|---|---|---|---|---|"]
    for c in payload["cryptos"]:
        d, f, m, s = c["decision"], c["forecast"], c["model"], c["signal"]
        auc = m.get("auc") if m.get("auc") is not None else "n/d"
        rows.append(f"| {c['name']} | {s['action']} | {d['action']} | {d['convergence']} "
                    f"| {c['composite']:+.2f} | {c['fundamental'].get('score')} | {auc} "
                    f"| {f['lo95_pct']*100:+.0f}%..{f['hi95_pct']*100:+.0f}% |")
    return "\n".join(rows)


def main():
    cfg = load_config()
    print("Analyse quotidienne (parametres optimises)...")
    payload = build_payload(cfg)
    if not payload["cryptos"]:
        print("[ERREUR] aucune crypto analysee."); sys.exit(1)

    note = ai_note.write_note(payload)
    full = f"*Note crypto quotidienne — {payload['date']}*\n" + summary_table(payload) + "\n\n" + note

    if cfg["notify"].get("commit_report", True):
        (ROOT / "reports").mkdir(exist_ok=True)
        (ROOT / "reports" / f"{payload['date']}.md").write_text(full, encoding="utf-8")
        print(f"Rapport ecrit : reports/{payload['date']}.md")

    if cfg["notify"].get("telegram"):
        notify.send_telegram(full)
    if cfg["notify"].get("email"):
        notify.send_email(full, subject=f"Note crypto — {payload['date']}")
    print("Termine.")


if __name__ == "__main__":
    main()
