"""
Lecture/ecriture de l'etat persistant des parametres optimises.

state/params_state.json contient, par crypto :
  - params  : les 5 jeux de parametres retenus au dernier reentrainement
  - enabled : quels indicateurs sont actifs (les defaillants sont a False)
  - valid   : metriques de validation hors-echantillon par indicateur
  - composite_valid : edge de la strategie composite en validation
  - model   : pouvoir predictif mesure (AUC) du modele
  - updated : date du dernier reentrainement

Le job QUOTIDIEN lit cet etat (il n'optimise pas). Le job HEBDOMADAIRE le reecrit.
Si l'etat est absent (premier lancement), on repart des parametres par defaut.
"""
from __future__ import annotations
import json
import pathlib

from src import technical as T

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "state" / "params_state.json"


def load() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def get_for(state: dict, name: str) -> dict:
    """Parametres a utiliser pour une crypto : ceux de l'etat, sinon defauts."""
    entry = state.get(name)
    if not entry:
        return dict(params=T.DEFAULT_PARAMS, enabled={k: True for k in T.DEFAULT_PARAMS},
                    model={}, composite_valid={}, updated=None, from_default=True)
    entry = dict(entry); entry["from_default"] = False
    return entry


def save(state: dict):
    STATE_PATH.parent.mkdir(exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
