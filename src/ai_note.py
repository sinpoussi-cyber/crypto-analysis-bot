"""
Redaction de la note quotidienne par l'IA (API Claude / Anthropic).

Principe de conception (important) :
- L'IA NE CALCULE RIEN et NE PREDIT RIEN. Tous les chiffres (indicateurs,
  signal, intervalle de projection) sont calcules par le code Python en amont.
- L'IA recoit ces chiffres deja calcules et se contente de les REDIGER en
  francais, clairement, pour un lecteur humain.
- Le prompt systeme lui interdit explicitement d'inventer un prix futur ou
  d'affirmer une direction. Elle explique ce que disent les indicateurs
  AUJOURD'HUI, jamais ce qui va arriver demain.

Si la cle API est absente, une note deterministe de secours est generee sans IA.
"""
from __future__ import annotations
import json
import os

SYSTEM = """Tu es un analyste quantitatif qui redige une note quotidienne sur des \
crypto-actifs, en francais, pour un lecteur averti (statisticien).

La note comporte DEUX couches complementaires, que tu presentes clairement :
- SIGNAL TECHNIQUE TRANSPARENT (ACHAT / CONSERVATION / VENTE) : score mecanique
  issu d'indicateurs classiques (MM 20/50/200, RSI, MACD, Bollinger, momentum),
  avec chaque regle visible. C'est "ce que disent les indicateurs aujourd'hui".
- DECISION D'INVESTISSEMENT a 4 feux : TECHNIQUE (5 indicateurs a parametres
  optimises chaque semaine), FONDAMENTAL (qualite/liquidite), PREDICTION (modele
  dont l'AUC est mesuree hors-echantillon) et RISQUE. L'action INVESTIR n'apparait
  que si les 4 feux sont verts ; sinon CONSERVER ou EVITER.
Le signal technique peut etre ACHAT sans que la decision soit INVESTIR : la
decision est plus exigeante (elle demande aussi fondamental, edge et risque).

REGLES ABSOLUES :
1. Tu ne PREDIS JAMAIS un prix futur ni une direction ("va monter/baisser").
2. Tu presentes la decision comme le resultat MECANIQUE des 4 feux, pas comme un
   ordre ni un conseil personnalise. "INVESTIR" = les 4 conditions objectives sont
   reunies aujourd'hui, pas une promesse de gain.
3. Tu n'inventes AUCUN chiffre : uniquement les valeurs fournies.
4. Sur la PREDICTION : si le modele n'a pas d'edge mesure (AUC proche de 0,5), tu
   dis explicitement qu'il est ignore faute de pouvoir predictif fiable. Tu ne le
   presentes jamais comme une prevision credible s'il n'a pas d'edge.
5. L'intervalle de projection mesure l'incertitude (largeur), pas une direction.
6. Rappel de risque bref + "information, pas un conseil en investissement".
7. Pour chaque crypto, tu cites explicitement le PROFIL DE RISQUE fourni : ATR,
   volatilite annualisee, drawdown historique et momentum 7j/30j/90j.

Style : concis, factuel, structure. ~120-180 mots par crypto."""


def _fallback_note(payload: dict) -> str:
    lines = [f"# Note quotidienne — {payload['date']}", "",
             "*(Note de secours generee sans IA : cle API absente.)*", ""]
    for c in payload["cryptos"]:
        d, f, m, fu, s = c["decision"], c["forecast"], c["model"], c["fundamental"], c["signal"]
        g = d["gates"]
        actifs = [k for k, v in c["enabled"].items() if v]
        regles = "; ".join(x["explication"] for x in s["components"])
        i = c["indicators"]
        def _p(x, mul=100, suf="%"):
            return f"{x*mul:+.1f}{suf}" if x is not None else "n/d"
        risk_line = (
            f"- Profil de risque : ATR {_p(i.get('atr_pct'), 100, '%') if i.get('atr_pct') else 'n/d'} "
            f"| volatilite annualisee {_p(i.get('ann_vol'))} "
            f"| drawdown actuel vs plus-haut {_p(i.get('drawdown'))} "
            f"| momentum 7j/30j/90j {_p(i.get('ret_7d'))} / {_p(i.get('ret_30d'))} / {_p(i.get('ret_90d'))}"
        )
        lines += [
            f"## {c['name']} — signal technique : {s['action']} | decision : {d['action']} ({d['convergence']})",
            f"- Prix : {c['indicators']['price']:.4f} USD | composite : {c['composite']:+.2f} "
            f"| indicateurs actifs : {', '.join(actifs) or 'aucun'}",
            f"- Signal technique transparent : {s['action']} (score {s['score']}) — regles : {regles}",
            risk_line,
            f"- Feu TECHNIQUE : {'vert' if g['technique']['ok'] else 'rouge'} "
            f"(edge valide : {g['technique']['edge_valide']})",
            f"- Feu FONDAMENTAL : {'vert' if g['fondamental']['ok'] else 'rouge'} "
            f"(score {fu.get('score')})",
            f"- Feu PREDICTION : {g['prediction']['etat']} (AUC {m.get('auc')}, "
            f"proba hausse {m.get('proba_up')})",
            f"- Feu RISQUE : {'vert' if g['risque']['ok'] else 'rouge'} "
            f"(vol. annualisee {g['risque']['vol_annualisee']})",
            f"- Projection 30j (fourchette, pas une prevision) : "
            f"{f['lo95_pct']*100:+.0f}% a {f['hi95_pct']*100:+.0f}% autour du prix actuel.",
            "",
        ]
    lines.append("_Information a but educatif — pas un conseil en investissement. "
                 "Actifs tres volatils : pertes possibles. Un backtest positif ne garantit "
                 "aucune performance future._")
    return "\n".join(lines)


def write_note(payload: dict) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[WARN] ANTHROPIC_API_KEY absente : note de secours (sans IA).")
        return _fallback_note(payload)

    try:
        import anthropic
    except ImportError:
        print("[WARN] paquet anthropic absent : note de secours.")
        return _fallback_note(payload)

    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    client = anthropic.Anthropic(api_key=api_key)
    user_msg = (
        "Voici les donnees calculees pour aujourd'hui (JSON). Redige la note "
        "quotidienne en respectant strictement tes regles. Pour chaque crypto : "
        "un titre avec le biais technique, un paragraphe interpretant les "
        "indicateurs fournis, puis la fourchette de projection presentee comme "
        "une mesure d'incertitude. Termine par un rappel de risque global.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    try:
        resp = client.messages.create(
            model=model, max_tokens=2000, system=SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        return resp.content[0].text
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] appel API echoue ({e}) : note de secours.")
        return _fallback_note(payload)
