"""
Generation du rapport Word (.docx) a partir du payload quotidien.

Produit un document detaille : titre, resume executif, tableau recapitulatif
(20 cryptos, decisions en couleur), analyse detaillee par crypto, methodologie.
Utilise python-docx (aucune dependance Node). Renvoie le chemin du fichier ecrit.
"""
from __future__ import annotations
import pathlib

# Import defensif : si python-docx est absent, l'import du module NE plante PAS
# (le reste du pipeline — analyse, reentrainement, email texte — continue).
# La generation du .docx echouera proprement, capturee par le try/except de main.
try:
    from docx import Document
    from docx.shared import Pt, RGBColor, Twips
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    _HAS_DOCX = True
    NAVY = RGBColor(0x1F, 0x38, 0x64)
    BLUE = RGBColor(0x2E, 0x54, 0x96)
    GREEN = RGBColor(0x1E, 0x7D, 0x32)
    RED = RGBColor(0xC6, 0x28, 0x28)
    AMBER = RGBColor(0xB2, 0x6A, 0x00)
    GREY = RGBColor(0x55, 0x55, 0x55)
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)
except Exception:  # noqa: BLE001
    _HAS_DOCX = False


def _shade(el, fill_hex):
    """Applique une couleur de fond a une cellule ou un paragraphe (via son _element)."""
    pr = el.get_or_add_tcPr() if el.tag.endswith('}tc') else el.get_or_add_pPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear'); shd.set(qn('w:color'), 'auto'); shd.set(qn('w:fill'), fill_hex)
    pr.append(shd)


def _run(p, text, *, bold=False, color=None, size=10, italic=False):
    r = p.add_run(text)
    r.font.bold = bold; r.font.italic = italic; r.font.size = Pt(size); r.font.name = "Calibri"
    if color is not None:
        r.font.color.rgb = color
    return r


def _dec_color(d):
    return GREEN if d == "INVESTIR" else RED if d == "EVITER" else AMBER


def _fmt_price(p):
    if p >= 1000:
        return f"{p:,.2f}".replace(",", " ")
    if p >= 1:
        return f"{p:.4f}"
    return f"{p:.6f}"


def _pct(x, d=1):
    return f"{x*100:+.{d}f}%" if x is not None else "n/d"


def build(payload: dict, out_dir: str) -> str:
    if not _HAS_DOCX:
        raise RuntimeError("python-docx non installe (ajoute 'python-docx>=1.1' a requirements.txt)")
    date = payload["date"]
    cryptos = payload["cryptos"]
    doc = Document()
    # marges
    sec = doc.sections[0]
    sec.top_margin = sec.bottom_margin = Twips(900)
    sec.left_margin = sec.right_margin = Twips(1000)
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(10)

    # ---- bandeau titre (table 1 cellule, fond navy) ----
    t = doc.add_table(rows=2, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (txt, sz, col) in enumerate([("NOTE CRYPTO QUOTIDIENNE", 22, WHITE),
                                        (f"Analyse technique · fondamentale · prédiction — {date}", 11, RGBColor(0xD9,0xE1,0xF2))]):
        cell = t.rows[i].cells[0]
        _shade(cell._tc, "1F3864")
        p = cell.paragraphs[0]
        _run(p, txt, bold=(i == 0), color=col, size=sz)
    doc.add_paragraph()

    p = doc.add_paragraph()
    _run(p, "Univers analysé : "+str(len(cryptos))+" cryptomonnaies (top capitalisation). "
            "Deux couches : signal technique transparent (ACHAT/CONSERVATION/VENTE) et "
            "décision d'investissement à 4 feux (Technique · Fondamental · Prédiction · Risque).",
         italic=True, color=GREY, size=9)

    # compteurs
    n_inv = sum(1 for c in cryptos if c["decision"]["action"] == "INVESTIR")
    n_evi = sum(1 for c in cryptos if c["decision"]["action"] == "EVITER")
    n_con = sum(1 for c in cryptos if c["decision"]["action"] == "CONSERVER")
    inv_names = ", ".join(c["name"] for c in cryptos if c["decision"]["action"] == "INVESTIR") or "aucune"
    evi_names = ", ".join(c["name"] for c in cryptos if c["decision"]["action"] == "EVITER") or "aucune"

    # ---- 1. Résumé exécutif ----
    doc.add_heading("1. Résumé exécutif", level=1)
    p = doc.add_paragraph(); _run(p, "Répartition des décisions à 4 feux sur les "+str(len(cryptos))+" cryptomonnaies :", size=10)
    for txt, col in [("INVESTIR (4 feux verts) : "+str(n_inv)+" — "+inv_names+".", GREEN),
                     ("CONSERVER (pas de signal net) : "+str(n_con)+".", AMBER),
                     ("ÉVITER (fondamental ou risque en échec) : "+str(n_evi)+" — "+evi_names+".", RED)]:
        pp = doc.add_paragraph(style="List Bullet"); _run(pp, txt, size=10, color=col, bold=True)

    # ---- 2. Tableau récapitulatif ----
    doc.add_heading("2. Tableau récapitulatif", level=1)
    cols = ["Crypto", "Signal tech.", "Décision", "Feux", "Composite", "Fond.", "AUC", "Proj. 30j (95%)"]
    widths = [1150, 1350, 1350, 700, 1000, 700, 700, 2100]
    tab = doc.add_table(rows=1, cols=len(cols))
    tab.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = tab.rows[0].cells
    for j, name in enumerate(cols):
        _shade(hdr[j]._tc, "2E5496")
        pp = hdr[j].paragraphs[0]; pp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _run(pp, name, bold=True, color=WHITE, size=8)
    for i, c in enumerate(cryptos):
        d = c["decision"]; s = c["signal"]; m = c["model"]; f = c["forecast"]
        auc = m.get("auc") if m.get("auc") is not None else "n/d"
        proj = _pct(f["lo95_pct"], 0)+".."+_pct(f["hi95_pct"], 0)
        vals = [c["name"], s["action"], d["action"], d["convergence"].split()[0],
                (f"{c['composite']:+.2f}"), str(c["fundamental"].get("score")), str(auc), proj]
        row = tab.add_row().cells
        zebra = "F2F5FB" if i % 2 else None
        for j, v in enumerate(vals):
            if zebra:
                _shade(row[j]._tc, zebra)
            pp = row[j].paragraphs[0]
            pp.alignment = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
            col = None; bold = False
            if j == 0:
                bold = True
            elif j == 1:
                col = RED if v == "VENTE" else (GREEN if v == "ACHAT" else GREY)
            elif j == 2:
                col = _dec_color(v); bold = True
            _run(pp, v, size=8, color=col, bold=bold)
    # largeurs de colonnes
    for j, w in enumerate(widths):
        for row in tab.rows:
            row.cells[j].width = Twips(w)
    p = doc.add_paragraph()
    _run(p, "Composite = moyenne des indicateurs actifs (−1 à +1). Fond. = score fondamental /100. "
            "AUC = pouvoir prédictif mesuré (0,5 = hasard). Projection = fourchette de plausibilité à "
            "30 jours, pas une prévision.", size=8, color=GREY)

    # ---- 3. Plan de trade (niveaux mecaniques) ----
    doc.add_page_break()
    doc.add_heading("3. Plan de trade — niveaux indicatifs", level=1)
    p = doc.add_paragraph()
    _run(p, "Niveaux dérivés de la VOLATILITÉ (pas d'une prévision) : objectif à "
            "+1,5σ, stop à −1,0σ sur la durée indiquée. Prix d'achat = prix actuel "
            "(référence, ordre au marché). Durée = fenêtre de détention avant revue, "
            "d'autant plus courte que l'actif est volatil. À ajuster selon votre tolérance au risque.",
         italic=True, color=GREY, size=9)
    lcols = ["Crypto", "Décision", "Prix d'achat", "Vente ↑ (objectif)", "Vente ↓ (stop)", "Durée (j)", "Ratio G/P"]
    lwidths = [1150, 1300, 1500, 1700, 1600, 900, 900]
    lt = doc.add_table(rows=1, cols=len(lcols))
    lt.alignment = WD_TABLE_ALIGNMENT.CENTER
    lh = lt.rows[0].cells
    for j, name in enumerate(lcols):
        _shade(lh[j]._tc, "2E5496")
        pp = lh[j].paragraphs[0]; pp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _run(pp, name, bold=True, color=WHITE, size=8)
    for i, c in enumerate(cryptos):
        lv = c.get("levels") or {}
        d = c["decision"]
        vals = [
            c["name"], d["action"],
            "$"+_fmt_price(lv.get("entry", c["indicators"]["price"])),
            "$"+_fmt_price(lv.get("take_profit", 0))+"  ("+_pct(lv.get("tp_pct"), 0)+")",
            "$"+_fmt_price(lv.get("stop_loss", 0))+"  ("+_pct(lv.get("sl_pct"), 0)+")",
            str(lv.get("horizon_days", "-")),
            (str(lv.get("rr")) if lv.get("rr") else "-"),
        ]
        row = lt.add_row().cells
        zebra = "F2F5FB" if i % 2 else None
        for j, v in enumerate(vals):
            if zebra:
                _shade(row[j]._tc, zebra)
            pp = row[j].paragraphs[0]
            pp.alignment = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
            col = None; bold = False
            if j == 0:
                bold = True
            elif j == 1:
                col = _dec_color(v); bold = True
            elif j == 3:
                col = GREEN
            elif j == 4:
                col = RED
            _run(pp, v, size=8, color=col, bold=bold)
    for j, w in enumerate(lwidths):
        for row in lt.rows:
            row.cells[j].width = Twips(w)
    p = doc.add_paragraph()
    _run(p, "Ratio G/P = gain visé ÷ perte au stop (1,5 par défaut). Ces niveaux sont pleinement "
            "actionnables surtout quand la décision est INVESTIR ; pour CONSERVER/ÉVITER, ils servent "
            "de niveaux de surveillance. Ce ne sont pas des ordres ni un conseil.", size=8, color=GREY)

    # ---- 4. Analyse détaillée ----
    doc.add_page_break()
    doc.add_heading("4. Analyse détaillée par crypto", level=1)
    for c in cryptos:
        d = c["decision"]; s = c["signal"]; m = c["model"]; f = c["forecast"]; i = c["indicators"]
        g = d["gates"]
        actifs = ", ".join(k for k, v in c["enabled"].items() if v) or "aucun"
        h = doc.add_heading(level=2); h.text = ""
        _run(h, c["name"]+"  —  ", bold=True, color=NAVY, size=13)
        _run(h, d["action"], bold=True, color=_dec_color(d["action"]), size=13)
        _run(h, "  ("+d["convergence"]+")", color=GREY, size=9)

        def kv(label, val, vcolor=None):
            pp = doc.add_paragraph()
            _run(pp, label+" : ", bold=True, size=9.5)
            _run(pp, val, size=9.5, color=vcolor)

        kv("Prix", "$"+_fmt_price(i["price"])+"   |   Composite "+f"{c['composite']:+.2f}"+"   |   Indicateurs actifs : "+actifs)
        kv("Signal technique", s["action"]+" (score "+f"{s['score']:.3f}"+")", RED if s["action"] == "VENTE" else GREY)
        kv("Profil de risque", "ATR "+(_pct(i.get('atr_pct')) if i.get('atr_pct') else 'n/d')
           + "  ·  volatilité annualisée "+_pct(i.get('ann_vol'))
           + "  ·  drawdown vs plus-haut "+_pct(i.get('drawdown'))
           + "  ·  momentum 7j/30j/90j "+_pct(i.get('ret_7d'))+" / "+_pct(i.get('ret_30d'))+" / "+_pct(i.get('ret_90d')))
        pp = doc.add_paragraph()
        _run(pp, "Décision à 4 feux : ", bold=True, size=9.5)
        _run(pp, "Technique "+("vert" if g['technique']['ok'] else "rouge")+"  ·  ", size=9,
             color=GREEN if g['technique']['ok'] else RED)
        _run(pp, "Fondamental "+("vert" if g['fondamental']['ok'] else "rouge")+" (score "+str(g['fondamental'].get('score'))+")  ·  ", size=9,
             color=GREEN if g['fondamental']['ok'] else RED)
        _run(pp, "Prédiction "+g['prediction']['etat']+" (AUC "+str(m.get('auc'))+")  ·  ", size=9)
        _run(pp, "Risque "+("vert" if g['risque']['ok'] else "rouge")+" (vol "+str(g['risque'].get('vol_annualisee'))+")", size=9,
             color=GREEN if g['risque']['ok'] else RED)
        kv("Projection 30j (fourchette, pas une prévision)",
           _pct(f["lo95_pct"], 0)+" à "+_pct(f["hi95_pct"], 0)+" autour du prix actuel")
        lv = c.get("levels") or {}
        if lv:
            pp = doc.add_paragraph()
            _run(pp, "Plan de trade (volatilité, pas une prévision) : ", bold=True, size=9.5)
            _run(pp, "achat ~$"+_fmt_price(lv.get("entry", i["price"]))+"  ·  ", size=9)
            _run(pp, "vente ↑ $"+_fmt_price(lv.get("take_profit", 0))+" ("+_pct(lv.get("tp_pct"), 0)+")", size=9, color=GREEN)
            _run(pp, "  ·  ", size=9)
            _run(pp, "vente ↓ $"+_fmt_price(lv.get("stop_loss", 0))+" ("+_pct(lv.get("sl_pct"), 0)+")", size=9, color=RED)
            _run(pp, "  ·  détention ~"+str(lv.get("horizon_days", "-"))+" j  ·  ratio G/P "+str(lv.get("rr", "-")), size=9)

    # ---- 5. Méthodologie ----
    doc.add_page_break()
    doc.add_heading("5. Méthodologie & avertissements", level=1)
    meth = [
        ("Deux couches complémentaires",
         "Le SIGNAL TECHNIQUE résume ce que disent les indicateurs. La DÉCISION à 4 feux n'affiche INVESTIR "
         "que si Technique, Fondamental, Prédiction et Risque convergent. Un signal peut être neutre alors que "
         "la décision est INVESTIR, et inversement.", BLUE),
        ("Les 5 indicateurs",
         "Moyennes mobiles, RSI, MACD, Stochastique, Bandes de Bollinger — paramètres ré-optimisés chaque semaine "
         "en walk-forward. Un indicateur qui ne bat pas le buy-and-hold hors-échantillon est désactivé.", BLUE),
        ("Feu Prédiction",
         "Modèle logistique dont l'AUC est mesurée hors-échantillon. Sans edge (AUC ≈ 0,5), il est ignoré : aucune "
         "prédiction n'est présentée comme fiable sans pouvoir prédictif démontré.", BLUE),
        ("Projection 30 jours",
         "Fourchette de plausibilité (marche aléatoire) : sa largeur mesure l'incertitude. Ce n'est pas une "
         "prévision de prix et elle n'indique aucune direction.", BLUE),
        ("Plan de trade (niveaux)",
         "Prix d'achat = prix actuel (référence). Objectif de vente à la hausse = prix × exp(+1,5σ) et stop "
         "à la baisse = prix × exp(−1,0σ), où σ est l'amplitude typique (volatilité) sur la durée de détention. "
         "La durée = 21 ÷ volatilité annualisée, bornée 7–45 jours (un actif calme se tient plus longtemps). "
         "Ces niveaux sont des repères de gestion du risque dérivés de la volatilité, PAS des prévisions ni des "
         "ordres : ajustez-les à votre tolérance au risque.", BLUE),
        ("Données",
         "Cours quotidiens CoinGecko (historique limité à 365 jours sur le plan gratuit).", BLUE),
        ("Avertissement",
         "Document d'information à but éducatif — pas un conseil en investissement. Cryptomonnaies très volatiles : "
         "pertes possibles, y compris totales. Les performances passées ne préjugent pas des performances futures.", RED),
    ]
    for title, body, col in meth:
        pp = doc.add_paragraph(); _run(pp, title, bold=True, size=10, color=col)
        pp2 = doc.add_paragraph(); _run(pp2, body, size=9.5)

    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / ("Note_Crypto_"+date+".docx")
    doc.save(str(path))
    return str(path)
