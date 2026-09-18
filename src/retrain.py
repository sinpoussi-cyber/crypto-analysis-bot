"""
REENTRAINEMENT HEBDOMADAIRE (lance chaque dimanche par GitHub Actions).

Pour chaque crypto :
  - recupere l'historique,
  - relance l'optimisation walk-forward (src/optimize) : nouveaux parametres +
    remplacement des indicateurs defaillants (validation hors-echantillon),
  - re-mesure le pouvoir predictif du modele (src/model, AUC walk-forward),
  - ecrit le tout dans state/params_state.json (relu par le job quotidien),
  - produit un rapport de reentrainement dans reports/retrain_<date>.md.

Usage : python -m src.retrain
"""
from __future__ import annotations
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from src import data_sources, optimize, model, state, notify, universe  # noqa: E402
from src.main import load_config  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    cfg = load_config()
    today = dt.date.today().isoformat()
    days = cfg.get("history_days", 800)
    new_state = state.load()
    cryptos = universe.build_universe(cfg)

    lines = [f"# Reentrainement hebdomadaire — {today}",
             f"Univers : {len(cryptos)} cryptos.", ""]
    for name, meta in cryptos.items():
        try:
            df = data_sources.fetch(name, meta, days)
        except Exception as e:  # noqa: BLE001
            lines.append(f"## {name} — ECHEC recuperation : {e}")
            continue
        res = optimize.optimize_crypto(df, cfg)
        mdl = model.train_and_skill(df, res["params"], horizon=cfg.get("predict_horizon", 5))
        new_state[name] = dict(
            params=res["params"], enabled=res["enabled"], valid=res.get("valid", {}),
            composite_valid=res.get("composite_valid", {}),
            model=dict(auc=mdl.get("auc"), skill=mdl.get("skill"),
                       proba_up=mdl.get("proba_up"), reason=mdl.get("reason")),
            updated=today,
        )
        cv = res.get("composite_valid", {})
        actifs = [k for k, v in res["enabled"].items() if v]
        defail = [k for k, v in res["enabled"].items() if not v]
        lines += [
            f"## {name}",
            f"- Indicateurs actifs : {', '.join(actifs) or 'aucun'}",
            f"- Defaillants remplaces (neutralises) : {', '.join(defail) or 'aucun'}",
            f"- Composite (validation hors-echantillon) : Sharpe={cv.get('sharpe')}, "
            f"rendement={cv.get('total_return')}, buy&hold={cv.get('bh_total_return')}, "
            f"bat le buy&hold : {cv.get('beats_bh')}",
            f"- Modele de prediction : AUC={mdl.get('auc')} -> "
            f"{'EDGE mesure, utilise' if mdl.get('skill') else 'pas d edge fiable, IGNORE'}",
            f"- Parametres retenus : {res['params']}",
            "",
        ]
    state.save(new_state)

    rep = ROOT / "reports" / f"retrain_{today}.md"
    rep.parent.mkdir(exist_ok=True)
    report = "\n".join(lines)
    rep.write_text(report, encoding="utf-8")
    print(f"Etat mis a jour : {state.STATE_PATH}")
    print(f"Rapport : {rep}")

    if cfg["notify"].get("telegram"):
        notify.send_telegram(f"*Reentrainement hebdomadaire effectue — {today}*\n"
                             "Parametres re-optimises et indicateurs defaillants remplaces. "
                             "Detail dans le rapport du depot.")


if __name__ == "__main__":
    main()
