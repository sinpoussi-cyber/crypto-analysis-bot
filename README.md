# Système d'analyse crypto quantitatif — technique · fondamental · prédiction · walk-forward

Pipeline **GitHub Actions** à deux tâches :

- **Quotidienne** (`src/main.py`) : applique les paramètres optimisés, calcule les
  5 indicateurs, la fondamentale, la prédiction et une **décision à 4 feux**, puis
  envoie une note (Telegram/email) et l'archive dans `reports/`.
- **Hebdomadaire** (`src/retrain.py`, chaque dimanche) : **réentraîne les paramètres
  en walk-forward**, remplace les **indicateurs défaillants**, re-mesure le modèle,
  et met à jour `state/params_state.json`.

## Univers analysé — « toutes les cryptos »

Configurable dans `config.yaml` (section `universe`) :

- `mode: list` — la liste explicite `cryptos` (tes 6 de départ).
- `mode: top_n` — les **N premières cryptos par capitalisation**, récupérées
  automatiquement (CoinGecko) et mappées aux **paires USDT négociables sur Binance**
  (exchangeInfo), stablecoins exclus. `top_n: 30` par défaut, augmentable.

En pratique, « toutes les cryptos » = l'univers **liquide et négociable** des top-N,
rafraîchi à chaque exécution. Analyser des milliers de micro-jetons illiquides
serait coûteux en CI et sans valeur : ils échoueraient de toute façon au filtre
fondamental. Augmente `top_n` selon le temps de calcul que tu acceptes (l'optimisation
walk-forward hebdomadaire tourne une fois par crypto).

## Le flux quotidien

Récupération des cours (**Binance**, avec **CoinGecko** en secours pour GRAM qui
n'est pas sur Binance) → **analyse technique réelle** (RSI, MACD, moyennes mobiles
20/50/200, Bollinger, ATR, volatilité, drawdown, momentum) → **signal mécanique et
transparent ACHAT / CONSERVATION / VENTE** (chaque règle visible) → **projection 30
jours en intervalle** → **rédaction de la note par l'IA (cascade DeepSeek → Kimi →
Claude)** → **envoi Telegram/email et archivage dans `reports/`**. Le workflow
GitHub Actions tourne à **06:00 UTC (soit 06:00 à Abidjan, UTC+0)** et se déclenche
aussi à la main.

### Choix du fournisseur IA (cascade)

La note est rédigée par le premier fournisseur disponible, dans cet ordre :
**DeepSeek → Kimi (Moonshot) → Claude (Anthropic)**, puis une note déterministe
sans IA si tous échouent (clé absente, quota, erreur réseau). DeepSeek et Kimi
utilisent l'API compatible OpenAI, Claude le SDK Anthropic. L'ordre est
modifiable via le secret `AI_PROVIDER_ORDER` (ex. `kimi,claude,deepseek`). Quel
que soit le fournisseur, le même prompt système s'applique : l'IA **rédige** les
chiffres calculés par le code, elle n'invente ni prix ni prédiction.

La note porte **deux couches complémentaires** :
1. le **signal technique transparent** (ACHAT / CONSERVATION / VENTE) — ce que
   disent les indicateurs aujourd'hui, règles explicites ;
2. la **décision d'investissement à 4 feux** (ci-dessous) — plus exigeante : un
   signal ACHAT ne devient INVESTIR que si fondamental, edge validé et risque
   convergent aussi.

## La logique de décision — « on investit seulement quand tout converge »

Chaque jour, pour chaque crypto, 4 feux doivent être verts pour un signal **INVESTIR** :

| Feu | Contenu | Vert si |
|---|---|---|
| **Technique** | Score composite des 5 indicateurs (paramètres optimisés) | composite ≥ seuil **ET** la stratégie a un edge validé hors-échantillon |
| **Fondamental** | Capitalisation, liquidité (volume/cap), rang, offre, activité dev (CoinGecko) | score qualité ≥ 55/100 |
| **Prédiction** | Modèle logistique walk-forward, **AUC mesurée** | AUC ≥ 0,55 **ET** proba hausse ≥ 0,55 — sinon *neutre et ignoré* |
| **Risque** | Volatilité annualisée | ≤ 150 %/an |

Sinon : **CONSERVER** (pas de signal technique) ou **ÉVITER** (fondamental ou risque en échec).

## Les 5 indicateurs (paramètres ré-optimisés chaque semaine)

Moyennes mobiles · RSI · MACD · **Stochastique** · Bandes de Bollinger.
Chacun produit un signal {+1, 0, −1} ; le composite est leur moyenne (indicateurs
actifs seulement).

## Le réentraînement walk-forward (le cœur du système)

Chaque dimanche, pour chaque crypto et chaque indicateur :

1. **Entraînement** sur une fenêtre glissante (`train_window`, 365 j par défaut) :
   recherche du jeu de paramètres maximisant le Sharpe (backtest net de frais).
2. **Validation hors-échantillon** sur une fenêtre postérieure jamais vue
   (`valid_window`, 90 j) — c'est le seul juge.
3. **Remplacement des défaillants** : un indicateur dont le Sharpe de validation
   est ≤ 0 ou qui ne bat pas le buy-and-hold est **désactivé** (`enabled=False`)
   jusqu'au prochain cycle ; il se réactive s'il redevient profitable.
4. **Edge composite** : on mesure aussi si la stratégie d'ensemble bat le
   buy-and-hold en validation.

Tout est écrit dans `state/params_state.json`, relu par la tâche quotidienne.

## ⚠️ Ce que ce système est — et n'est pas

Il **mesure sa propre performance** au lieu de deviner. C'est la garantie honnête :

- Le signal technique n'est retenu que s'il **bat le hasard hors-échantillon**.
- La prédiction n'est utilisée **que si son AUC dépasse 0,55** ; sinon elle est
  ignorée — jamais présentée comme fiable sans edge mesuré.
- La projection 30 j est un **intervalle de plausibilité** (marche aléatoire), pas
  un prix. Sa largeur mesure l'incertitude.

Résultat attendu et honnête : sur des cryptos, l'edge prédictif quotidien est
souvent faible ou nul — le système le dira et **s'abstiendra** plutôt que d'inventer
un signal. Un backtest positif ne garantit aucune performance future. **Information
à but éducatif, pas un conseil en investissement.** N'engagez que ce que vous pouvez
perdre.

## Structure

```
config.yaml                    cryptos, fenêtres walk-forward, seuils, canaux
requirements.txt               pandas, numpy, scikit-learn, anthropic...
src/
  data_sources.py              cours Binance / CoinGecko
  technical.py                 5 indicateurs paramétrables + signaux + composite
  indicators.py                snapshot lisible (pour la note)
  fundamental.py               filtre qualité/liquidité (CoinGecko)
  backtest.py                  moteur long/flat + métriques (Sharpe, DD, hit...)
  optimize.py                  optimisation walk-forward + remplacement défaillants
  model.py                     prédiction logistique + AUC hors-échantillon
  forecast.py                  projection 30j en intervalle
  decision.py                  combinaison des 4 feux
  state.py                     lecture/écriture params_state.json
  main.py                      tâche quotidienne
  retrain.py                   tâche hebdomadaire
.github/workflows/
  daily.yml                    quotidien 06:00 UTC
  weekly_retrain.yml           dimanche 05:00 UTC
state/params_state.json        paramètres + indicateurs actifs + AUC (auto-généré)
reports/                       notes et rapports de réentraînement archivés
```

## Installation

1. Pousser le dossier sur un dépôt GitHub.
2. Récupérer : **clé API DeepSeek** (platform.deepseek.com — prioritaire),
   éventuellement **Kimi/Moonshot** (platform.moonshot.ai) et **Claude**
   (console.anthropic.com) comme replis, et un **bot Telegram**
   (@BotFather → token ; `getUpdates` → chat_id).
3. **Settings → Secrets and variables → Actions** : ajouter au minimum
   `DEEPSEEK_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Optionnels :
   `KIMI_API_KEY`, `ANTHROPIC_API_KEY`, `AI_PROVIDER_ORDER`, les `*_MODEL`, et
   les `SMTP_*` pour l'email. Un seul fournisseur IA suffit à faire tourner le
   système ; les autres ne servent que de repli.
4. **Actions → Reentrainement hebdomadaire → Run workflow** une première fois pour
   générer `state/params_state.json`, puis **Note crypto quotidienne → Run workflow**.
   Ensuite tout tourne seul (dimanche = réentraînement, chaque jour = note).

## Test en local

```bash
pip install -r requirements.txt
python -m src.retrain     # génère state/params_state.json
python -m src.main        # produit et (si secrets présents) envoie la note
```

## Prolongements naturels (pistes quant)

- **Historiser** signaux, décisions et performance réalisée (base Supabase) pour
  suivre l'edge dans le temps.
- **Purged/embargoed CV** (López de Prado) pour un backtest encore plus robuste au
  data-snooping.
- **Corrélations** entre actifs pour juger la diversification du panier.
- **Coûts réels** (spread + slippage) affinés par actif.
