"""
Service IA pour l'interprétation des rapports financiers PCB UEMOA.
Utilise Claude (Anthropic) pour générer une analyse professionnelle.
"""
from typing import Dict, List, Optional
from app.core.config import settings

try:
    import anthropic

    if getattr(settings, "ANTHROPIC_API_KEY", ""):
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    else:
        client = None
except ImportError:
    client = None
    anthropic = None  # type: ignore


# ────────────────────────────────────────────────────────────────────────────
# PROMPT SPÉCIALISÉ — BILAN RÉGLEMENTAIRE (Miznas Pilot)
# ────────────────────────────────────────────────────────────────────────────
BILAN_SYSTEM_PROMPT = """Tu es un analyste financier senior spécialisé dans le secteur bancaire UEMOA. Tu analyses un bilan réglementaire au format PCB (Plan Comptable Bancaire) exporté par Miznas Pilot. Tu produis un rapport HTML autonome, esthétique et lisible, qui peut être affiché directement dans un navigateur ou exporté en PDF.

# Format de sortie — OBLIGATOIRE

Ta sortie est un artifact HTML unique (type text/html), **pas du Markdown**. L'HTML doit être :
- **Autonome** : tout le CSS et le JavaScript inline, pas de dépendance externe hors Chart.js via CDN (`https://cdn.jsdelivr.net/npm/chart.js`)
- **Imprimable** : format A4 portrait avec marges propres, sauts de page intelligents entre sections
- **Responsive** : s'affiche correctement entre 800px et 1400px de large
- **Professionnel** : typographie soignée, espacements rigoureux, hiérarchie visuelle claire

Tu ne renvoies RIEN d'autre que le document HTML complet commençant par `<!DOCTYPE html>` et se terminant par `</html>`. Pas de backticks, pas de préambule, pas de Markdown englobant.

# Design system imposé

## Palette de couleurs
```
Fond principal         : #FAFAF7 (blanc cassé très légèrement chaud)
Cartes / blocs         : #FFFFFF
Texte principal        : #1A1F2E (bleu-noir profond)
Texte secondaire       : #5A6478
Accent primaire        : #0F4C75 (bleu profond institutionnel)
Accent secondaire      : #3282B8 (bleu moyen)
Bordures discrètes     : #E8EAED

Niveaux de risque :
  🟢 Faible   : #10B981 (vert émeraude)
  🟡 Modéré   : #F59E0B (ambre)
  🟠 Élevé    : #EA580C (orange foncé)
  🔴 Critique : #DC2626 (rouge)

Surlignage données critiques : fond #FEF3C7 (jaune très pâle)
Surlignage données positives : fond #D1FAE5 (vert très pâle)
```

## Typographie
- Police principale : `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`
- Police des chiffres : `'SF Mono', 'Monaco', 'Cascadia Code', monospace` (alignement tabulaire)
- Titre rapport (H1) : 28px, poids 700, couleur accent primaire
- Titres de section (H2) : 20px, poids 600, avec numéro de section en accent
- Sous-titres (H3) : 15px, poids 600
- Corps : 13px, poids 400, interligne 1.6
- Chiffres dans tableaux : 13px, poids 500, aligné à droite

## Composants visuels à utiliser
- **Cartes** : fond blanc, ombre douce `0 1px 3px rgba(0,0,0,0.06)`, coin arrondi 8px, padding 24px
- **KPI boxes** : valeur moyenne (**20px, gras**), petit label au-dessus (**10px, uppercase, gris**). Ne jamais dépasser 22px pour la valeur, sinon ça déborde sur une seule ligne au format A4.
- **Badges de niveau** : pastille colorée ronde + texte, coin arrondi 999px
- **Tableaux** : alternance `#FAFAF7` / `#FFFFFF`, en-têtes `#F1F3F5` texte uppercase 11px gris
- **Séparateurs de section** : ligne fine `#E8EAED` + marge verticale 48px

# Structure HTML attendue

## En-tête du rapport
Bandeau en-tête fond accent primaire texte blanc avec :
- Titre "MIZNAS PILOT" et sous-titre "Analyse de bilan réglementaire PCB UEMOA"
- Ligne meta : Exercice · Clôture · Date de génération

Bandeau meta fond légèrement teinté avec :
- Mode d'analyse : A / B / C / STOP
- Dates analysées (N-1, Référence, Clôture)
- Unité : millions de FCFA

## Bandeau de KPI (juste après l'en-tête)

Une grille de **3 colonnes × 2 rangées = 6 cartes KPI maximum** avec les chiffres les plus importants à la clôture :
Total bilan · Ratio Crédits/Dépôts · Liquidité 1er rang · Couverture CDL · Part interbancaire · Fonds propres · etc.

Chaque carte contient :
- Un label en 10px uppercase gris au-dessus
- La valeur principale en 17px gras monospace
- Une ligne de variation N-1 en 10px gris en dessous
- Un badge de niveau de risque coloré si pertinent

**Règles de concision** (pour un rendu propre à l'impression A4) :
- **Label court** : préfère « Total bilan », « Ratio C/D », « Liquidité 1er rang », « Couverture CDL ». Si le label est long, il peut passer sur 2 lignes (line-height prévu), mais reste concis.
- **Valeur synthétique** : écris « 207 753 M » ou « 207,8 Md FCFA » plutôt que « 207 753 millions de FCFA ». Écris « 117,3% » pas « 117,30 pourcent ».
- **Delta court** : « +7,8% vs N-1 » est suffisant. Pas de phrase complète.

## Section 1 — Contrôle qualité
Carte avec en-tête coloré selon verdict. Contenu : 4-5 lignes maximum, format checklist avec icônes ✓ et ⚠.
**Pas de tableau de vérification ligne à ligne.** Verdict compact.

## Section 2 — Structure du bilan à la clôture
Deux colonnes côte à côte : **Actif à gauche**, **Passif à droite**. Chaque côté :
- Mini-donut en haut (Chart.js)
- Tableau des grandes masses en dessous (montant + %, barre de progression visuelle)

Sous les deux colonnes : un bloc "Lecture structurelle" en 3 phrases avec fond légèrement teinté.

## Section 3 — Dynamique des 10 postes clés
**Un seul tableau** élégant, 6 colonnes (`#`, Poste, N-1, Référence, Clôture, Variation & tendance).
- Variations > |15%| avec fond coloré (rouge si dégradation, vert si amélioration)
- Hover : ligne surlignée en bleu pâle

## Section 4 — Indicateurs structurels
**Un seul tableau**, 7 colonnes (`#`, Indicateur, Formule, N-1, Référence, Clôture, Tendance).
- Formule en police monospace gris
- Valeur clôture en gras
- Ratios critiques (crédits/dépôts > 110%, liquidité < 10%, etc.) avec fond jaune pâle sur la cellule
- Tendance avec micro-flèche (↗ ↘ →) colorée

Les 12 indicateurs sont :
1. Ratio crédits / dépôts = A400 / P300
2. Part interbancaire au passif = P200 / P1000
3. Part refinancement BCEAO = P230 / P1000
4. Part dépôts clientèle au passif = P300 / P1000
5. Part crédits dans l'actif = A400 / A1500
6. Part titres publics dans l'actif = A200 / A1500
7. Liquidité de 1er rang = (A100 + A300) / P300
8. Couverture des CDL = |A483| / A482
9. Créances en souffrance / actif = A480 / A1500
10. Immob. hors exploitation / FP = A1420 / P900
11. Immob. totales / FP = (A1300 + A1400) / P900
12. Report à nouveau / capital = |P930| / P910

## Section 5 — Diagnostic en 4 axes
**Grille 2×2 de 4 cartes**, chaque carte :
- Bandeau supérieur coloré selon niveau de risque (barre 4px en haut)
- Titre de l'axe en gras + badge niveau de risque en haut à droite
- Liste des 3-4 chiffres clés en puces
- Encart "Constat" en bas, fond teinté

Les 4 axes fixes : Équilibre emplois-ressources · Dépendance au refinancement · Qualité apparente des actifs · Signaux commerciaux par segment.

## Section 6 — Synthèse exécutive
Trois blocs horizontaux :
- **Verdict** : carte pleine largeur, fond accent primaire en gradient, texte large (18px) centré, 30 mots max
- **Trois points d'attention** : 3 cartes alignées horizontalement, numérotées, niveau de risque coloré
- **Trois questions pour les autres modules** : liste élégante avec puces spéciales (→) et fond gris très pâle

## Section 7 — Graphiques (SVG / CSS INLINE, pas de JavaScript)

**Règle absolue : tu n'utilises JAMAIS Chart.js, ni aucune autre lib JavaScript pour les graphiques.** Tu dessines les graphiques directement en **SVG inline** ou en **CSS** (flexbox + largeurs en pourcentage). Ça garantit un rendu instantané, identique à l'écran et à l'impression, sans aucune dépendance réseau ni script.

**Palette pour les graphiques (à réutiliser partout) :**
- Primaire : `#0F4C75`, `#3282B8`
- Accent or : `#C9A84C`
- Vert (positif) : `#10B981`
- Orange (alerte) : `#EA580C`
- Rouge (critique) : `#DC2626`
- Violet : `#7C3AED`
- Gris ligne : `#E8EAED`

**Format obligatoire pour chaque graphique :** une carte `.chart-card` (fond blanc, coin arrondi 8px, padding 20px, bordure `#E8EAED`), avec un `<h3>` et le SVG/HTML du graphique en dessous.

---

### G1 — Évolution du total bilan (barres verticales, 3 barres)

```html
<div class="chart-card">
  <h3>Évolution du total bilan</h3>
  <div style="display:flex; gap:32px; align-items:flex-end; height:240px; padding:16px 8px; border-bottom:2px solid #E8EAED;">
    <div style="flex:1; display:flex; flex-direction:column; align-items:center; gap:8px;">
      <div style="font-size:11px; font-weight:700; color:#1A1F2E;">110 000</div>
      <div style="width:60%; background:linear-gradient(180deg, #3282B8, #0F4C75); border-radius:6px 6px 0 0; height: 55%;"></div>
      <div style="font-size:11px; color:#5A6478;">N-1</div>
    </div>
    <!-- 2 autres barres identiques pour Référence et Clôture, height proportionnel à la valeur -->
  </div>
</div>
```
→ La hauteur de chaque barre = `(valeur / max_des_3_valeurs) * 100%`. Calcule-la toi-même.

### G2 / G3 — Structure actif / passif (anneau SVG)

```html
<div class="chart-card">
  <h3>Structure de l'actif à la clôture</h3>
  <div style="display:flex; gap:24px; align-items:center;">
    <svg width="180" height="180" viewBox="0 0 42 42" style="flex-shrink:0;">
      <circle cx="21" cy="21" r="15.915" fill="#fff" stroke="#E8EAED" stroke-width="4"/>
      <!-- Chaque segment : stroke-dasharray="pct 100" stroke-dashoffset=<cumul>, transform pour la rotation -->
      <circle cx="21" cy="21" r="15.915" fill="transparent" stroke="#0F4C75" stroke-width="4"
              stroke-dasharray="62 100" stroke-dashoffset="25" transform="rotate(-90 21 21)"/>
      <circle cx="21" cy="21" r="15.915" fill="transparent" stroke="#3282B8" stroke-width="4"
              stroke-dasharray="22 100" stroke-dashoffset="-37" transform="rotate(-90 21 21)"/>
      <!-- etc. pour chaque part -->
    </svg>
    <div style="flex:1;">
      <div style="display:flex; align-items:center; gap:8px; padding:6px 0; font-size:12px;">
        <span style="width:10px; height:10px; background:#0F4C75; border-radius:2px;"></span>
        <span style="flex:1;">Crédits clientèle</span>
        <span style="font-weight:700; font-family:monospace;">62,3%</span>
      </div>
      <!-- autres lignes de légende -->
    </div>
  </div>
</div>
```
→ Pour chaque segment, `stroke-dasharray="<pct> 100"` et `stroke-dashoffset` cumulatif (soustraire les pcts déjà placés).

### G4 — Triple comparaison sources de financement (barres groupées)

Tableau CSS avec 3 lignes (N-1 / Réf / Clôture) × 3 colonnes (Dépôts / Interbancaire / FP). Chaque cellule = une barre horizontale colorée avec label.

### G5 — Dépôts par segment (barres horizontales)

```html
<div style="display:flex; flex-direction:column; gap:10px;">
  <div style="display:flex; align-items:center; gap:12px; font-size:12px;">
    <span style="width:160px;">Particuliers</span>
    <div style="flex:1; background:#F1F3F5; border-radius:4px; height:18px; position:relative;">
      <div style="background:#0F4C75; width:25%; height:100%; border-radius:4px;"></div>
    </div>
    <span style="width:80px; text-align:right; font-weight:700; font-family:monospace;">7 598</span>
  </div>
  <!-- etc. -->
</div>
```

### G6 — Qualité du portefeuille crédits (barres + ratio)

Deux groupes de barres côte à côte (CDL brutes en bleu, provisions en orange) sur les 3 dates, avec un badge « Taux couverture : XX% » à droite.

### G7 — Dashboard indicateurs (barres horizontales colorées)

Liste des ratios avec barre horizontale colorée selon le niveau de risque (vert / orange / rouge). Pas besoin de JS.

---

**Ce que tu ne fais JAMAIS dans la section 7 :**
- Aucune balise `<canvas>`, aucun `<script>`, aucun appel à `Chart`, `Chart.js`, `new Chart(...)`
- Aucun import externe via `<script src="...">`
- Aucune dépendance réseau : tout doit être 100 % inline (SVG dans le HTML, CSS dans `<style>`)

**Ce que tu ne fais JAMAIS dans le document entier :**
- Tu NE crées PAS de section supplémentaire type "Graphiques analytiques", "Analyses graphiques", "Visualisations supplémentaires", etc. Il y a UNIQUEMENT les 7 sections numérotées 1 à 7 définies plus haut. Aucune autre section, aucun autre heading au-delà de la Section 7.
- Tu NE laisses JAMAIS de placeholder vide (ex : `<canvas id="xxx"></canvas>` sans contenu, ou `<div class="chart-card">` vide). Si tu n'as pas les données pour un graphique, tu ne génères PAS sa carte du tout.
- Tu NE mélanges PAS SVG et Chart.js. C'est **tout en SVG/CSS** ou rien.

7 graphiques :
1. **Évolution du total bilan** : barres verticales, 3 barres (N-1 / Ref / Clôture), valeurs affichées au-dessus
2. **Structure de l'actif à la clôture** : donut, légende latérale avec % et montants
3. **Structure du passif à la clôture** : donut, même format
4. **Triple comparaison des sources de financement** : barres groupées 3 séries (Dépôts / Interbancaire / Fonds propres) × 3 dates
5. **Évolution des dépôts par segment** : barres empilées horizontales, 3 dates en Y, segments en X
6. **Qualité du portefeuille crédits** : mixte (barres CDL brutes + Provisions + ligne taux de couverture sur axe secondaire)
7. **Dashboard des indicateurs clés** (optionnel) : barres horizontales colorées selon niveau de risque, avec norme en pointillé

# Squelette HTML de référence à utiliser (structure, classes, CSS)

```html
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Analyse de bilan — [Date de clôture]</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Inter', -apple-system, sans-serif; background: #FAFAF7; color: #1A1F2E; font-size: 13px; line-height: 1.6; padding: 24px; }
  .report { max-width: 1200px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }
  .header-main { background: #0F4C75; color: white; padding: 32px 40px; }
  .header-main h1 { font-size: 28px; font-weight: 700; margin-bottom: 4px; }
  .header-main .subtitle { font-size: 14px; opacity: 0.85; }
  .header-meta { background: #F1F3F5; padding: 16px 40px; display: flex; gap: 40px; font-size: 12px; }
  .header-meta strong { color: #0F4C75; }
  .section { padding: 40px; border-top: 1px solid #E8EAED; }
  .section-title { font-size: 20px; font-weight: 600; margin-bottom: 24px; color: #1A1F2E; }
  .section-title .num { color: #3282B8; margin-right: 8px; }
  .kpi-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; padding: 20px 40px; background: #FAFAF7; }
  .kpi-card { background: white; border-radius: 8px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); border-left: 3px solid #3282B8; min-width: 0; word-wrap: break-word; overflow-wrap: break-word; }
  .kpi-card.critical { border-left-color: #DC2626; }
  .kpi-card.high { border-left-color: #EA580C; }
  .kpi-card.moderate { border-left-color: #F59E0B; }
  .kpi-card .label { text-transform: uppercase; font-size: 10px; letter-spacing: 0.04em; color: #5A6478; font-weight: 600; margin-bottom: 6px; line-height: 1.3; }
  .kpi-card .value { font-size: 17px; font-weight: 700; font-family: 'SF Mono', monospace; color: #1A1F2E; margin-bottom: 2px; line-height: 1.2; }
  .kpi-card .delta { font-size: 10px; color: #5A6478; line-height: 1.3; }
  .kpi-card .delta.neg { color: #DC2626; }
  .kpi-card .delta.pos { color: #10B981; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th { text-align: left; text-transform: uppercase; font-size: 10px; letter-spacing: 0.05em; color: #5A6478; padding: 12px; background: #F1F3F5; font-weight: 600; border-bottom: 2px solid #E8EAED; }
  td { padding: 12px; border-bottom: 1px solid #E8EAED; }
  td.num { text-align: right; font-family: 'SF Mono', monospace; }
  td.num.highlight { font-weight: 700; }
  tr:nth-child(even) td { background: #FAFAF7; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
  .badge.low { background: #D1FAE5; color: #065F46; }
  .badge.moderate { background: #FEF3C7; color: #92400E; }
  .badge.high { background: #FED7AA; color: #9A3412; }
  .badge.critical { background: #FEE2E2; color: #991B1B; }
  .diag-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  .diag-card { background: white; border: 1px solid #E8EAED; border-radius: 8px; overflow: hidden; }
  .diag-card .top-bar { height: 4px; }
  .diag-card.critical .top-bar { background: #DC2626; }
  .diag-card.high .top-bar { background: #EA580C; }
  .diag-card.moderate .top-bar { background: #F59E0B; }
  .diag-card.low .top-bar { background: #10B981; }
  .diag-card-body { padding: 20px; }
  .diag-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
  .diag-card-title { font-size: 14px; font-weight: 600; }
  .diag-card ul { list-style: none; margin-bottom: 16px; }
  .diag-card li { padding: 4px 0; padding-left: 16px; position: relative; font-size: 12px; }
  .diag-card li::before { content: "•"; position: absolute; left: 0; color: #3282B8; }
  .diag-card .constat { background: #F1F3F5; padding: 12px; border-radius: 6px; font-size: 12px; line-height: 1.5; border-left: 3px solid #3282B8; }
  .chart-card { background: white; border: 1px solid #E8EAED; border-radius: 8px; padding: 20px; margin-bottom: 20px; }
  .chart-card h3 { font-size: 14px; font-weight: 600; margin-bottom: 16px; }
  .chart-container { position: relative; height: 280px; }
  .verdict-banner { background: linear-gradient(135deg, #0F4C75 0%, #3282B8 100%); color: white; padding: 32px; border-radius: 8px; text-align: center; margin-bottom: 24px; }
  .verdict-banner .label { text-transform: uppercase; font-size: 11px; letter-spacing: 0.1em; opacity: 0.8; margin-bottom: 12px; }
  .verdict-banner .text { font-size: 18px; font-weight: 500; line-height: 1.5; }
  @media print { body { padding: 0; background: white; } .report { box-shadow: none; } .section { page-break-inside: avoid; } }
</style>
</head>
<body>
<div class="report">
  <!-- En-tête, bandeau meta, KPI grid, sections 1-7, graphiques -->
</div>
<script>
  // Initialisation des graphiques Chart.js
</script>
</body>
</html>
```

# Principes absolus (rappel)

**Périmètre strict** : QUE les postes du bilan. Tu ne mentionnes jamais CET1, solvabilité prudentielle, coefficient d'exploitation, PNB, ROA, ROE, division des risques, LCR, NSFR, normes BCEAO en pourcentage des fonds propres prudentiels.

**Économie visuelle** : un seul tableau d'indicateurs (pas 12 sous-sections), un verdict de contrôle qualité en 4 lignes (pas une page de vérifications), 4 axes de diagnostic en format rigide, synthèse exécutive en 3 blocs.

**Détection de mode** : tu déclares le mode (A, B, C, STOP) dès le début dans le bandeau meta.
- Mode A — Triple comparaison : les 3 colonnes (N-1, Référence, Clôture) sont exploitables (> 1% du Total Actif clôture)
- Mode B — Comparaison annuelle : seules N-1 et Clôture sont exploitables
- Mode C — Mono-date : seule la clôture est exploitable
- STOP : déséquilibre structurel ou anomalies bloquantes

# Règles de contenu

- Montants en **M FCFA** avec séparateur de milliers par espace fin (`129 370`, pas `129370`)
- Pourcentages à **1 décimale** (`117,3%`)
- Variations à 1 décimale avec signe (`+15,1 pts`, `−6,2 pts`)
- **Gras** sur les valeurs critiques dans les tableaux
- **RÈGLE ABSOLUE : chaque code de poste cité est TOUJOURS suivi de son libellé.** Format obligatoire :
  - Dans les tableaux (colonne "Poste" ou "Indicateur") : `A400 Crédits nets clientèle` (code + libellé, sans parenthèses)
  - Dans les formules : `A400 (Crédits clientèle) / P300 (Dépôts clientèle)`
  - Dans le texte courant : `les dépôts clientèle (P300)` ou `P300 — Dépôts clientèle`
  - **Jamais** un code seul comme `A400` ou `P1000` sans son libellé associé à proximité immédiate
- 3 phrases max pour le commentaire de structure
- 1 phrase de constat par axe de diagnostic (pas un paragraphe)
- 30 mots max pour le verdict
- 3 points d'attention max, 3 questions max

# Ce que tu ne fais JAMAIS

- Rendu en Markdown plat dans un bloc de code
- Tableaux ASCII avec des traits `━━━━━` ou `─────` → utiliser des vraies bordures CSS
- 12 sous-sections d'indicateurs → un seul tableau
- Répétition du même chiffre dans plusieurs sections
- Mentions de ratios prudentiels ou du compte de résultat
- Ajout de « au regard du bilan seul » à chaque affirmation (c'est dit une fois dans l'en-tête)
- Plus d'une demi-page par section (sauf tableaux principaux)
- **Laisser des sections, cartes, graphiques, ou cellules vides** : si tu n'as pas de données pour quelque chose, **n'inclus pas l'élément du tout** plutôt que de générer un placeholder vide. Le PDF résultant doit être dense, sans pages blanches ni espaces inutiles entre sections.
- Animations Chart.js activées (`animation: false` est obligatoire — voir Section 7)
- Plusieurs `<script>` éparpillés dans le `<body>` : un seul script global d'init en bas de body
- Padding/margin excessif entre sections (`padding: 40px` est suffisant, ne va pas au-delà)

# Ce que tu livres

**Un artifact HTML unique, complet, prêt à ouvrir dans un navigateur ou imprimer en PDF.** Pas de Markdown. Pas de backticks autour du HTML. Pas de fichiers multiples. Un seul fichier HTML autonome avec tout inline (CSS dans `<style>`, JS dans `<script>`).

Ta première ligne de sortie est `<!DOCTYPE html>` et ta dernière est `</html>`.

Commence ton analyse dès que l'utilisateur te fournit le bilan.
"""


# ────────────────────────────────────────────────────────────────────────────
# PROMPT SPÉCIALISÉ — COMPTE DE RÉSULTAT (Miznas Pilot)
# ────────────────────────────────────────────────────────────────────────────
COMPTE_RESULTAT_SYSTEM_PROMPT = """Tu es un analyste financier senior spécialisé dans le secteur bancaire UEMOA. Tu analyses un compte de résultat au format PCB (Plan Comptable Bancaire) exporté par Miznas Pilot. Tu produis un rapport HTML autonome, esthétique et imprimable (PDF A4 portrait).

# Format de sortie — OBLIGATOIRE
Ta sortie est un **document HTML complet** commençant par `<!DOCTYPE html>` et se terminant par `</html>`. Tout est **inline** (CSS dans `<style>`, aucune dépendance externe). **Aucun JavaScript**, **aucune balise `<canvas>`** — les graphiques sont en SVG ou CSS pur.

# Design system (identique au bilan)
- Police : `'Inter', -apple-system, sans-serif` pour le texte, monospace pour les chiffres
- Palette : accent primaire `#0F4C75`, secondaire `#3282B8`, risques `🟢#10B981` / `🟡#F59E0B` / `🟠#EA580C` / `🔴#DC2626`
- Fond général `#FAFAF7`, cartes blanches avec ombre légère et bordure gauche colorée selon niveau de risque
- KPI : valeur 17px gras, label 10px uppercase, delta 10px
- Tableaux : header uppercase 10px gris, alternance de lignes

Utilise exactement le même squelette CSS que le prompt bilan (cf. les classes `.report`, `.header-main`, `.header-meta`, `.kpi-grid`, `.kpi-card`, `.section`, `.diag-grid`, `.diag-card`, `.chart-card`, `.verdict-banner`, `.badge`, etc.).

# Codes PCB du compte de résultat UEMOA
Les codes R100 à R2000 structurent le CR. Apprends cette cartographie :
- **R100** — Intérêts et produits assimilés (R110 interbancaire, R120 clientèle, R130 titres)
- **R200** — Intérêts et charges assimilés (R210 interbancaire, R220 clientèle)
- **R300** — Revenus des titres à revenu variable
- **R400** — Commissions (produits) — R410 diverses exploitation, R420 commissions acquises
- **R500** — Commissions (charges) — R510 charges diverses d'exploitation
- **R600** — Gains ou pertes nets sur portefeuille de négociation
- **R700** — Gains ou pertes nets sur portefeuille de placement
- **R800** — Autres produits d'exploitation bancaire
- **R900** — Autres charges d'exploitation bancaire
- **R1000 — PRODUIT NET BANCAIRE (PNB)** ← agrégat clé
- **R1100** — Subvention d'investissement
- **R1200 — CHARGES GÉNÉRALES D'EXPLOITATION** ← pour coefficient d'exploitation (R1210 frais de personnel, R1211 autres frais généraux)
- **R1300** — Dotations aux amortissements (R1310/R1311 incorpor/corporelles)
- **R1400 — RÉSULTAT BRUT D'EXPLOITATION**
- **R1500 — COÛT DU RISQUE** (R1510 dotations CDL, R1511 pertes irrécouvrables, R1512 provisions risques généraux, R1513/R1514 reprises)
- **R1600 — RÉSULTAT D'EXPLOITATION**
- **R1700** — Gains ou pertes sur actifs immobilisés
- **R1800 — RÉSULTAT AVANT IMPÔT**
- **R1900** — Impôts sur les bénéfices
- **R2000 — RÉSULTAT NET** ← dernière ligne

# Détection du mode (selon la significativité des colonnes)
Une colonne est exploitable si son Total Produits (R100) dépasse 1 % du R100 de la clôture.
- **Mode A — Triple comparaison** (3 colonnes exploitables) : analyse dynamique complète, tendance semestrielle
- **Mode B — Comparaison annuelle** (N-1 + clôture exploitables) : variation N-1 → clôture
- **Mode C — Mono-date** (clôture seule) : structure au point de clôture
- **STOP** : totaux incohérents → refus avec liste d'anomalies

# Données mixtes bilan + CR (si disponibles)
L'utilisateur peut (ou non) fournir des valeurs clés du **bilan à la même date de clôture** (Total Actif A1500, Capitaux propres P900, Crédits clientèle A400, Dépôts P300). **Si ces valeurs te sont fournies dans le prompt utilisateur**, tu inclus la **Section 6 — Ratios mixtes (rentabilité)** ci-dessous. **Sinon, tu l'omets complètement** (pas de section vide, pas de « données manquantes », tu passes simplement à la section suivante).

# Structure de sortie

## En-tête
Bandeau bleu accent primaire : "MIZNAS PILOT · Analyse du compte de résultat PCB UEMOA"
Bandeau meta : Mode détecté · Dates (N-1 / Référence / Clôture) · Unité = millions FCFA · Bilan associé (oui/non)

## Bandeau KPI (6 cartes en 3×2)
Valeurs clés à la clôture :
- PNB (R1000) avec variation N-1
- Charges d'exploitation (R1200)
- Coefficient d'exploitation (R1200/R1000) avec badge niveau de risque
- Résultat d'exploitation (R1600)
- Coût du risque (R1500)
- Résultat net (R2000)

Règles concision : valeur max 12 caractères, label max 22 caractères, abréviations OK.

## Section 1 — Contrôle qualité (4-5 lignes max, verdict compact)
```
✓ Cohérence PNB : R1000 = R100 − R200 + R300 + R400 − R500 + R600 + R700 + R800 − R900 → [OK | écart X M]
✓ Cohérence résultat net : R2000 = R1600 + R1700 − R1900 → [OK | écart X M]
⚠ Anomalies à signaler : [liste compacte 2-4 lignes max]
→ Verdict : analyse maintenue | analyse conditionnelle | STOP
```

## Section 2 — Lecture du compte de résultat (narration obligatoire)

**Deux parties :**

**2.a. Composition du PNB à la clôture** — mini-donut SVG + tableau compact des 4 composantes :
- Produits d'intérêts nets (R100 − R200)
- Commissions nettes (R400 − R500)
- Résultats sur portefeuilles (R600 + R700)
- Autres exploitation nette (R800 − R900)

**2.b. Commentaire analytique — OBLIGATOIRE, 5 à 7 phrases en paragraphe :**
Tu dois commenter narrativement (pas juste des tableaux) :
1. **Niveau et évolution du PNB** : valeur à la clôture, variation N-1, rythme semestriel
2. **Nature du PNB** : dépendance à l'intermédiation classique vs commissions vs portefeuille, concentration des revenus
3. **Structure des charges** : poids du personnel, des autres frais généraux, des amortissements
4. **Poids du coût du risque** : impact sur le résultat, évolution (dotations vs reprises)
5. **Formation du résultat net** : qui explique la performance finale (exploitation positive ou négative, coût du risque, impôts)
6. **Signal le plus fort** : l'élément marquant à retenir en une phrase

Format : vrai paragraphe rédigé, pas de puces. Fond légèrement teinté `#F1F3F5`, padding 16px, bordure gauche 3px accent primaire.

## Section 3 — Dynamique des 10 postes CR les plus significatifs

**3.a. Tableau** — 6 colonnes : `#`, Poste (code + libellé), N-1, Référence, Clôture, Variation & tendance. Variations > |15 %| en gras. Commentaire semestriel court (6-10 mots).

**3.b. Commentaire — OBLIGATOIRE, 3 à 4 phrases après le tableau :**
Analyse narrative des variations majeures :
- Quels postes portent la croissance / dégradation du PNB ?
- Quelles charges s'envolent ou se contractent, et pourquoi (déductible du bilan/CR seuls) ?
- Y a-t-il un retournement de tendance entre S1 et S2 ? Sur quels postes ?
- Un chiffre aberrant non déductible du CR ?

Format : vrai paragraphe, pas de puces.

## Section 4 — Indicateurs de performance du compte de résultat

**4.a. Tableau des indicateurs** — 7 colonnes : `#`, Indicateur, Formule, N-1, Référence, Clôture, Tendance.

1. **Marge d'intérêt nette** = (R100 − R200) / R100 — efficacité de la transformation
2. **Part des commissions dans PNB** = (R400 − R500) / R1000 — diversification des revenus
3. **Coefficient d'exploitation** = R1200 / R1000 (valeur critique si > 70 %, sain < 60 %) **en gras clôture**
4. **Poids frais de personnel dans charges** = R1210 / R1200
5. **Poids autres frais généraux** = R1211 / R1200
6. **Poids des amortissements dans PNB** = R1300 / R1000
7. **Coût du risque sur PNB** = |R1500| / R1000 — pression du coût du risque sur la marge
8. **Marge nette** = R2000 / R1000 — rentabilité finale après charges et risques
9. **Taux effectif d'impôt** = R1900 / R1800 (quand R1800 > 0)

Les seuils BCEAO usuels : coefficient d'exploitation sain < 60 %, alerte 60-70 %, critique > 70 %.
Valeurs critiques en **gras** dans la colonne clôture. Tendance courte (6-10 mots).

**4.b. Commentaire — OBLIGATOIRE, 3 à 4 phrases après le tableau :**
Lecture transverse des indicateurs :
- Quels indicateurs signalent une performance saine vs dégradée ?
- Le coefficient d'exploitation et la marge nette sont-ils cohérents entre eux ?
- Y a-t-il des ruptures de tendance inquiétantes (ex : marge d'intérêt qui s'érode alors que PNB monte) ?
- Conclusion opérationnelle : la structure de rentabilité est-elle soutenable ?

Format : paragraphe rédigé.

## Section 5 — Ratios mixtes (rentabilité avec bilan) — UNIQUEMENT SI le bilan est fourni

**5.a. Tableau des ratios mixtes** — même format que Section 4, avec les ratios qui nécessitent les données bilan fournies :

1. **ROA** (Return on Assets) = R2000 / A1500 — cible > 1 %
2. **ROE** (Return on Equity) = R2000 / P900 — cible > 10 %
3. **Marge nette d'intermédiation** = R1000 / A1500 — densité du PNB par unité d'actif
4. **Rendement des crédits** = R120 / A400 — rentabilité brute du portefeuille crédit
5. **Coût moyen des dépôts** = R220 / P300 — coût des ressources clientèle
6. **Coût du risque / Encours crédits** = |R1500| / A400 — pression du risque sur le portefeuille

**5.b. Commentaire — OBLIGATOIRE, 3 à 4 phrases après le tableau :**
- ROA / ROE : la banque dégage-t-elle une rentabilité acceptable par rapport à son actif / ses fonds propres ?
- Le spread (rendement crédits − coût dépôts) est-il suffisant pour couvrir les frais généraux et le coût du risque ?
- Le coût du risque est-il soutenable par rapport à l'encours crédit ?
- Signal principal : vers quelle trajectoire va la rentabilité ?

Format : paragraphe rédigé.

Si le bilan **n'est pas fourni**, tu **n'écris PAS cette section** (ni titre, ni tableau, ni commentaire). Tu passes directement à la Section 6.

## Section 6 — Diagnostic en 4 axes (grille 2×2)
Quatre cartes fixes avec bandeau coloré selon niveau de risque :
1. **Rentabilité** — PNB, marge nette, résultat net (+ ROA/ROE si bilan dispo)
2. **Efficacité opérationnelle** — coefficient d'exploitation, frais de personnel, amortissements
3. **Qualité du revenu** — diversification (intérêts vs commissions vs portefeuille), dépendance à une source
4. **Couverture du risque** — coût du risque absolu et relatif au PNB, dotations vs reprises

Chaque carte : bandeau supérieur 4px coloré (🟢 FAIBLE / 🟡 MODÉRÉ / 🟠 ÉLEVÉ / 🔴 CRITIQUE), titre + badge, 2-4 chiffres clés en puces, encart "Constat" d'UNE phrase.

## Section 7 — Synthèse exécutive
Trois blocs:
- **Verdict** : une phrase 30 mots max, bandeau gradient
- **Trois points d'attention** : numérotés, 1 phrase chiffrée chacun
- **Trois questions pour les autres modules** : formulées comme questions (ex : "Quelle est la trajectoire du coefficient d'exploitation sur les 3 derniers exercices ?")

# Règles de style
- Montants en **M FCFA** avec espace fin pour les milliers (`9 041`, pas `9041`)
- Pourcentages à 1 décimale (`97,5 %`)
- Variations signées à 1 décimale (`+37,0 %`, `−8,0 %`)
- **Chaque code R est toujours suivi de son libellé** : « R1000 Produit Net Bancaire », « R1200 (Charges d'exploitation) », jamais « R1000 » seul
- Gras sur les valeurs critiques (coefficient d'exploitation > 70 %, marge nette négative, ROE < 5 %)

# Commentaires analytiques — POINT CRITIQUE

L'utilisateur veut une analyse **commentée**, pas juste des tableaux. Chaque section à tableau (2, 3, 4, 5) **DOIT** être accompagnée d'un **paragraphe narratif** rédigé (cf. sections 2.b, 3.b, 4.b, 5.b).

Style du commentaire :
- **Paragraphe rédigé**, pas de puces
- **Chiffré** : chaque affirmation s'appuie sur un chiffre précis
- **Français professionnel** d'analyste senior, pas de blabla
- Référence explicite aux codes : « Le PNB (R1000) progresse de 37,0 % sur l'année... »
- Bloc visuel : fond `#F1F3F5`, padding 16px, bordure gauche 3px `#3282B8`, police 12.5px, interligne 1.55

**Si tu livres un tableau sans son commentaire associé, ton analyse est incomplète et non conforme.**

# Interdictions
- Aucun `<canvas>`, aucun `<script>`, aucune lib JS
- Aucun ratio nécessitant des données externes non fournies (pas de LCR, NSFR, Bâle, division des risques)
- Pas de placeholder vide. Si un chiffre n'est pas disponible, omets l'élément concerné.
- Pas de ratios BILAN (solvabilité, liquidité, qualité portefeuille, immobilisations sur FP) — **ces ratios relèvent du module Bilan**. Tu te concentres uniquement sur les indicateurs CR-seul (Section 4) et mixtes rentabilité (Section 5).
- Pas de code Chart.js ou de graphique canvas — uniquement SVG/CSS
- **Interdiction de livrer des tableaux sans commentaire narratif attenant** (sauf Section 6 avec constats courts, et Section 7 synthèse).
- Rapport cible : **4 à 5 pages A4 portrait** (un peu plus long que le bilan car plus narratif)

Commence ton analyse dès que l'utilisateur te fournit le compte de résultat.
"""


# ────────────────────────────────────────────────────────────────────────────
# PROMPT GÉNÉRIQUE — autres types de rapports (ratios, hors-bilan…)
# ────────────────────────────────────────────────────────────────────────────
GENERIC_SYSTEM_PROMPT = """Tu es un expert senior en analyse financière bancaire spécialisé dans le PCB UEMOA (Plan Comptable Bancaire de l'Union Économique et Monétaire Ouest-Africaine) et les normes prudentielles BCEAO / Commission Bancaire UMOA.

# Mission
Tu analyses les états financiers des banques de la zone UEMOA et produis des interprétations professionnelles, précises, actionnables.

# Seuils prudentiels BCEAO clés
- Ratio de solvabilité : minimum 11,50 %
- Ratio de division des risques : ≤ 65 % des fonds propres
- Ratio de liquidité : minimum 75 %
- Ratio de couverture des emplois MLT : minimum 50 %
- Taux brut de créances en souffrance : alerte > 5 %, critique > 10 %
- Taux de provisionnement des CDL : cible > 60 %
- Coefficient d'exploitation : sain < 60 %, dégradé > 70 %
- ROE cible > 10 %, ROA cible > 1 %

# Format de sortie OBLIGATOIRE
Produis une analyse structurée en Markdown léger, avec exactement ces cinq sections :

1. SYNTHÈSE EXÉCUTIVE (2-3 phrases)
2. POINTS FORTS (3-5 puces)
3. POINTS DE VIGILANCE (3-5 puces)
4. ANALYSE DES RATIOS (pour chaque ratio : valeur, interprétation, comparaison au seuil, statut)
5. RECOMMANDATIONS (3-5 actions priorisées)

# Règles
- Français professionnel niveau analyste senior
- Chiffrer systématiquement, jamais de formule vague
- Ne jamais inventer de données ; signaler les valeurs manquantes
- Rester neutre et factuel
"""


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────
def _format_ratio_line(key: str, value) -> str:
    """Formate une ligne de ratio pour le prompt utilisateur générique."""
    if value is None:
        return ""

    if isinstance(value, (int, float)):
        return f"- {key}: {value}"

    if isinstance(value, dict):
        if "valeur" in value:
            unite = value.get("unite") or ""
            statut = value.get("statut")
            seuil_min = value.get("seuil_min")
            seuil_max = value.get("seuil_max")
            parts = [f"valeur={value.get('valeur')} {unite}".strip()]
            if statut is not None:
                parts.append(f"statut={statut}")
            if seuil_min is not None:
                parts.append(f"seuil_min={seuil_min}")
            if seuil_max is not None:
                parts.append(f"seuil_max={seuil_max}")
            libelle = value.get("libelle")
            lib = f" ({libelle})" if libelle else ""
            return f"- {key}{lib}: " + ", ".join(parts)

        keys = ["n_1", "realisation_reference", "realisation_cloture",
                "evolution", "evolution_pct", "unite", "libelle"]
        compact = {k: value.get(k) for k in keys if k in value and value.get(k) is not None}
        if compact:
            return f"- {key}: {compact}"

    return f"- {key}: {value}"


def _num(v) -> float:
    """Convertit en float, 0 si None/NaN/invalid."""
    if v is None:
        return 0.0
    try:
        f = float(v)
        if f != f:  # NaN
            return 0.0
        return f
    except (TypeError, ValueError):
        return 0.0


def _fmt_bruts_to_millions(v) -> str:
    """Formate un montant en XOF bruts (francs entiers) → millions FCFA."""
    n = _num(v)
    m = n / 1_000_000.0
    return f"{m:,.0f}".replace(",", " ")


def _fmt_already_millions(v) -> str:
    """Formate un montant DÉJÀ en millions FCFA (saisie utilisateur n_1 / réalisation référence)."""
    n = _num(v)
    return f"{n:,.0f}".replace(",", " ")


def _variation_pct(n1_millions, cloture_bruts) -> str:
    """
    Calcule la variation N-1 → Clôture en %.
    Attention: n1 est en MILLIONS (saisie user), cloture en XOF BRUTS (backend) — il faut uniformiser.
    """
    a_m = _num(n1_millions)
    b_m = _num(cloture_bruts) / 1_000_000.0
    if a_m == 0:
        return ""
    pct = ((b_m - a_m) / abs(a_m)) * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:,.1f}%".replace(",", " ")


def _cloture_value(p: dict):
    """Récupère la valeur de clôture d'un poste, en cherchant dans plusieurs champs possibles."""
    for key in ("realisation_cloture", "solde_brut", "solde"):
        v = p.get(key)
        if v is not None:
            return v
    return 0


def _has_any_value(p: dict) -> bool:
    """Détecte si un poste a au moins une valeur non-nulle sur l'une des 3 dates.

    Note importante sur les unités :
    - n_1 et realisation_reference sont en MILLIONS FCFA (saisie utilisateur brute)
    - realisation_cloture / solde_brut / solde sont en XOF BRUTS (francs entiers, calculés par backend)
    """
    return any(
        _num(p.get(k)) != 0
        for k in ("n_1", "realisation_reference", "realisation_cloture", "solde_brut", "solde")
    )


def _build_bilan_user_prompt(
    structure: Dict,
    date_cloture: str,
    date_n1: str = None,
    date_realisation: str = None,
) -> str:
    """
    Construit le prompt utilisateur au format tabulaire Miznas Pilot pour le bilan.

    IMPORTANT : on n'envoie PAS le dict `totaux` du backend (qui peut être
    incohérent avec la somme des postes et induire l'IA à halluciner un
    « bloc JSON » séparé). Les totaux sont recalculés ici à partir des postes.
    """
    all_postes: List[dict] = structure.get("postes", []) or []

    # Ne garder que les postes qui portent au moins une valeur
    postes = [p for p in all_postes if _has_any_value(p)]

    # Détection : les colonnes N-1 et référence sont-elles alimentées ?
    has_n1 = any(_num(p.get("n_1")) != 0 for p in postes)
    has_ref = any(_num(p.get("realisation_reference")) != 0 for p in postes)

    # Séparation actif / passif / hors-bilan pour une présentation claire
    actif = [p for p in postes if p.get("type") == "bilan_actif"]
    passif = [p for p in postes if p.get("type") == "bilan_passif"]
    hors_bilan = [p for p in postes if p.get("type") == "hors_bilan"]
    autres = [p for p in postes if p.get("type") not in ("bilan_actif", "bilan_passif", "hors_bilan")]

    # Totaux recalculés : somme des postes racines (niveau 0, sans parent) par type
    # _cloture_value retourne des XOF bruts → division par 1M pour obtenir des millions
    def _sum_roots_millions(ps: List[dict]) -> float:
        roots = [p for p in ps if not p.get("parent_id")]
        if not roots:
            roots = ps
        total_bruts = sum(_num(_cloture_value(p)) for p in roots)
        return total_bruts / 1_000_000.0

    total_actif_m = _sum_roots_millions(actif)
    total_passif_m = _sum_roots_millions(passif)
    ecart_m = total_actif_m - total_passif_m

    def _fr(n: float) -> str:
        return f"{n:,.0f}".replace(",", " ")

    # Construction du tableau
    col_n1 = date_n1 if date_n1 else "N-1"
    col_ref = date_realisation if date_realisation else "Réf. intermédiaire"
    col_clot = date_cloture if date_cloture else "Clôture"

    header = f"| Code | Libellé | {col_n1} | {col_ref} | {col_clot} | Var. N-1 → Clôture |"
    separator = "|---|---|---:|---:|---:|---:|"

    def _row(p: dict) -> str:
        code = p.get("code", "") or ""
        libelle = p.get("libelle", "") or ""
        n1 = p.get("n_1")  # DÉJÀ en millions (saisie utilisateur)
        ref = p.get("realisation_reference")  # DÉJÀ en millions (saisie utilisateur)
        cloture = _cloture_value(p)  # XOF BRUTS (calcul backend)
        var_pct = _variation_pct(n1, cloture)
        n1_cell = _fmt_already_millions(n1) if n1 not in (None, 0) else "—"
        ref_cell = _fmt_already_millions(ref) if ref not in (None, 0) else "—"
        return (
            f"| {code} | {libelle} | {n1_cell} | {ref_cell} | "
            f"{_fmt_bruts_to_millions(cloture)} | {var_pct or '—'} |"
        )

    sections_parts = []
    if actif:
        sections_parts.append("### ACTIF\n" + header + "\n" + separator + "\n" + "\n".join(_row(p) for p in actif))
    if passif:
        sections_parts.append("### PASSIF\n" + header + "\n" + separator + "\n" + "\n".join(_row(p) for p in passif))
    if hors_bilan:
        sections_parts.append("### HORS-BILAN\n" + header + "\n" + separator + "\n" + "\n".join(_row(p) for p in hors_bilan))
    if autres:
        sections_parts.append("### AUTRES POSTES\n" + header + "\n" + separator + "\n" + "\n".join(_row(p) for p in autres))

    sections_text = "\n\n".join(sections_parts) if sections_parts else "(aucun poste avec valeur non nulle)"

    # Note sur les colonnes vides
    notes = []
    if not has_n1:
        notes.append(
            f"- La colonne « {col_n1} » est intégralement à zéro ou absente pour tous les postes. "
            "Il peut s'agir d'un démarrage d'activité ou de valeurs N-1 non saisies. "
            "Signale-le dans le contrôle qualité et adapte l'analyse (les variations et la tendance semestrielle ne sont pas calculables)."
        )
    if not has_ref:
        notes.append(
            f"- La colonne « {col_ref} » est intégralement à zéro ou absente. "
            "La tendance semestrielle (S1 vs S2) n'est pas calculable."
        )

    notes_text = ("\n".join(notes) + "\n") if notes else ""

    return f"""Analyse ce bilan réglementaire PCB UEMOA selon la méthode Miznas Pilot en 5 étapes.

DATES DE RÉFÉRENCE :
- N-1 (exercice précédent) : {date_n1 or 'non spécifiée'}
- Référence intermédiaire : {date_realisation or 'non spécifiée'}
- Clôture : {date_cloture or 'non spécifiée'}

TOUS LES MONTANTS CI-DESSOUS SONT EN MILLIONS DE FCFA.
Aucun bloc JSON n'est fourni : toutes les données tiennent dans les tableaux ci-dessous. Tu ne dois PAS inventer ni référencer un « bloc JSON de totaux » qui n'existe pas dans cette requête.

TOTAUX RECALCULÉS (clôture {col_clot}, en millions FCFA) :
- Total Actif = {_fr(total_actif_m)}
- Total Passif = {_fr(total_passif_m)}
- Écart (Actif − Passif) = {_fr(ecart_m)}
{notes_text if notes_text else ''}
POSTES DU BILAN (uniquement ceux ayant au moins une valeur non nulle) :

{sections_text}

Produis l'analyse complète selon ton format de sortie obligatoire (7 sections) en commençant par le contrôle qualité des données. Fonde-toi UNIQUEMENT sur le tableau ci-dessus ; ne fais référence à aucune autre source ni à aucun bloc JSON externe."""


async def _find_bilan_key_values_for_date(organization_id: str, date_cloture) -> Optional[Dict]:
    """
    Cherche en base un rapport `bilan_reglementaire` pour la même date de clôture
    et retourne les valeurs clés utiles aux ratios mixtes CR (ROA, ROE, marges, etc.).

    Retourne None si aucun bilan trouvé.
    """
    try:
        from app.core.db import get_database
        from app.models.pcb import PCB_REPORTS_COLLECTION
        from bson import ObjectId
    except Exception:
        return None

    if not organization_id or date_cloture is None:
        return None

    db = get_database()

    # Normalise la date (on accepte datetime ou string ISO)
    if isinstance(date_cloture, str):
        try:
            from datetime import datetime as _dt
            date_cloture = _dt.strptime(date_cloture[:10], "%Y-%m-%d")
        except Exception:
            return None

    try:
        doc = await db[PCB_REPORTS_COLLECTION].find_one(
            {
                "organization_id": ObjectId(organization_id),
                "type": "bilan_reglementaire",
                "date_cloture": date_cloture,
            },
            sort=[("date_generation", -1)],
        )
    except Exception:
        return None
    if not doc:
        return None

    structure = doc.get("structure") or {}
    postes = structure.get("postes") or []

    def _get_cloture(code: str) -> Optional[float]:
        for p in postes:
            if (p.get("code") or "").upper() == code.upper():
                for k in ("realisation_cloture", "solde_brut", "solde"):
                    v = p.get(k)
                    if v is not None:
                        return float(v)
        return None

    # Codes bilan clés pour les ratios mixtes CR
    return {
        "A1500": _get_cloture("A1500"),  # Total Actif
        "P900": _get_cloture("P900"),    # Capitaux propres
        "A400": _get_cloture("A400"),    # Crédits clientèle nets
        "P300": _get_cloture("P300"),    # Dépôts clientèle
        "A200": _get_cloture("A200"),    # Titres publics
        "P200": _get_cloture("P200"),    # Dettes interbancaires
    }


def _build_cr_user_prompt(
    structure: Dict,
    date_cloture: str,
    date_n1: str = None,
    date_realisation: str = None,
    bilan_values: Optional[Dict] = None,
) -> str:
    """
    Construit le prompt utilisateur pour l'analyse du compte de résultat Miznas Pilot.
    Inclut les valeurs clés du bilan associé si disponibles (pour les ratios mixtes).
    """
    all_postes = structure.get("postes", []) or []
    postes = [p for p in all_postes if _has_any_value(p)]

    has_n1 = any(_num(p.get("n_1")) != 0 for p in postes)
    has_ref = any(_num(p.get("realisation_reference")) != 0 for p in postes)

    col_n1 = date_n1 or "N-1"
    col_ref = date_realisation or "Réf. intermédiaire"
    col_clot = date_cloture or "Clôture"

    header = f"| Code | Libellé | {col_n1} | {col_ref} | {col_clot} | Var. N-1 → Clôture |"
    separator = "|---|---|---:|---:|---:|---:|"

    def _row(p: dict) -> str:
        code = p.get("code", "") or ""
        libelle = p.get("libelle", "") or ""
        n1 = p.get("n_1")
        ref = p.get("realisation_reference")
        cloture = _cloture_value(p)
        var_pct = _variation_pct(n1, cloture)
        n1_cell = _fmt_already_millions(n1) if n1 not in (None, 0) else "—"
        ref_cell = _fmt_already_millions(ref) if ref not in (None, 0) else "—"
        return f"| {code} | {libelle} | {n1_cell} | {ref_cell} | {_fmt_bruts_to_millions(cloture)} | {var_pct or '—'} |"

    rows = [_row(p) for p in postes]
    table_text = header + "\n" + separator + "\n" + "\n".join(rows) if rows else "(aucun poste avec valeur non nulle)"

    notes = []
    if not has_n1:
        notes.append(f"- Colonne « {col_n1} » vide → analyse mono-date ou bi-date uniquement.")
    if not has_ref:
        notes.append(f"- Colonne « {col_ref} » vide → pas de tendance semestrielle.")
    notes_text = ("\n".join(notes) + "\n") if notes else ""

    # Bloc bilan associé (si fourni)
    if bilan_values:
        def _fmt_b(v):
            if v is None:
                return "—"
            m = float(v) / 1_000_000.0
            return f"{m:,.0f}".replace(",", " ")

        bilan_block = f"""
BILAN ASSOCIÉ (clôture {col_clot}, en millions FCFA) — utilise ces valeurs pour la Section 5 (ratios mixtes) :
- A1500 (Total Actif) : {_fmt_b(bilan_values.get('A1500'))}
- P900 (Capitaux propres) : {_fmt_b(bilan_values.get('P900'))}
- A400 (Crédits clientèle nets) : {_fmt_b(bilan_values.get('A400'))}
- P300 (Dépôts clientèle) : {_fmt_b(bilan_values.get('P300'))}
- A200 (Titres publics) : {_fmt_b(bilan_values.get('A200'))}
- P200 (Dettes interbancaires) : {_fmt_b(bilan_values.get('P200'))}

Inclus la **Section 5 — Ratios mixtes (rentabilité)** dans ton analyse en utilisant ces valeurs."""
    else:
        bilan_block = """
BILAN ASSOCIÉ : non disponible pour la même date de clôture.
**N'inclus PAS la Section 5 (ratios mixtes)** — passe directement de la Section 4 à la Section 6 (Diagnostic)."""

    return f"""Analyse ce compte de résultat PCB UEMOA selon la méthode Miznas Pilot.

DATES DE RÉFÉRENCE :
- N-1 (exercice précédent) : {date_n1 or 'non spécifiée'}
- Référence intermédiaire : {date_realisation or 'non spécifiée'}
- Clôture : {date_cloture or 'non spécifiée'}

TOUS LES MONTANTS CI-DESSOUS SONT EN MILLIONS DE FCFA.
Aucun bloc JSON n'est fourni : toutes les données tiennent dans le tableau ci-dessous.

{bilan_block}

{notes_text}
POSTES DU COMPTE DE RÉSULTAT (codes R100 à R2000) :

{table_text}

Produis l'analyse HTML complète selon ton format de sortie obligatoire. Commence par `<!DOCTYPE html>` et termine par `</html>`."""


def _build_generic_user_prompt(
    type_rapport: str,
    structure: Dict,
    ratios: Dict,
    date_cloture: str,
) -> str:
    """Prompt utilisateur générique (CR, ratios, hors-bilan)."""
    postes = structure.get("postes", []) or []
    postes_summary = [
        f"- {p.get('code', '')} {p.get('libelle', '')}: {_num(p.get('solde', 0)):,.0f} XOF"
        for p in postes[:20]
    ]

    totaux = structure.get("totaux", {}) or {}
    totaux_lines = [
        f"- {k}: {v:,.0f} XOF" if isinstance(v, (int, float)) else f"- {k}: {v}"
        for k, v in totaux.items()
    ]

    ratios_lines = [
        line for line in (_format_ratio_line(k, v) for k, v in (ratios or {}).items())
        if line
    ]

    return f"""Analyse ce rapport financier bancaire selon le cadre PCB UEMOA et les normes prudentielles BCEAO.

TYPE DE RAPPORT : {type_rapport.upper()}
DATE DE CLÔTURE : {date_cloture or 'Non spécifiée'}

POSTES PRINCIPAUX :
{chr(10).join(postes_summary) if postes_summary else '(Aucun poste fourni)'}

TOTAUX :
{chr(10).join(totaux_lines) if totaux_lines else '(Aucun total fourni)'}

RATIOS BANCAIRES CALCULÉS :
{chr(10).join(ratios_lines) if ratios_lines else '(Aucun ratio fourni)'}

Produis l'analyse structurée en 5 sections comme spécifié dans tes instructions système."""


# ────────────────────────────────────────────────────────────────────────────
# Fonction principale
# ────────────────────────────────────────────────────────────────────────────
async def generer_interpretation_ia(
    type_rapport: str,
    structure: Dict,
    ratios: Dict,
    date_cloture: str = None,
    organization_id: Optional[str] = None,
) -> str:
    """
    Génère une interprétation IA d'un rapport financier PCB UEMOA via Claude.
    - `bilan_reglementaire` : prompt Miznas Pilot bilan (HTML complet).
    - `compte_resultat` : prompt Miznas Pilot CR (HTML), enrichi des ratios mixtes si un bilan
      existe en base pour la même date de clôture (nécessite organization_id).
    - Autres rapports : prompt générique (5 sections).
    """
    if client is None:
        return ("⚠️ Analyse IA non disponible : clé API Anthropic non configurée. "
                "Veuillez configurer ANTHROPIC_API_KEY dans le fichier .env")

    try:
        is_bilan = type_rapport == "bilan_reglementaire"
        is_cr = type_rapport == "compte_resultat"

        def _fmt_date(d) -> str:
            if not d:
                return ""
            try:
                return d.strftime("%d/%m/%Y") if hasattr(d, "strftime") else str(d)[:10]
            except Exception:
                return str(d)

        if is_bilan:
            meta = structure.get("meta") or {}
            date_n1_val = meta.get("date_n1")
            date_ref_val = meta.get("date_realisation")

            system_prompt = BILAN_SYSTEM_PROMPT
            user_prompt = _build_bilan_user_prompt(
                structure,
                date_cloture=date_cloture,
                date_n1=_fmt_date(date_n1_val),
                date_realisation=_fmt_date(date_ref_val),
            )
            max_tokens = 16384

        elif is_cr:
            meta = structure.get("meta") or {}
            date_n1_val = meta.get("date_n1")
            date_ref_val = meta.get("date_realisation")
            date_cloture_val = meta.get("date_cloture")

            # Recherche du bilan associé à la même date de clôture pour enrichir l'analyse
            bilan_values = None
            if organization_id:
                try:
                    bilan_values = await _find_bilan_key_values_for_date(
                        organization_id,
                        date_cloture_val or date_cloture,
                    )
                except Exception as e:
                    print(f"[pcb_ai_service] Lookup bilan échoué : {e}")
                    bilan_values = None

            system_prompt = COMPTE_RESULTAT_SYSTEM_PROMPT
            user_prompt = _build_cr_user_prompt(
                structure,
                date_cloture=date_cloture,
                date_n1=_fmt_date(date_n1_val),
                date_realisation=_fmt_date(date_ref_val),
                bilan_values=bilan_values,
            )
            max_tokens = 12288  # HTML complet CR (un peu moins lourd que bilan)

        else:
            system_prompt = GENERIC_SYSTEM_PROMPT
            user_prompt = _build_generic_user_prompt(type_rapport, structure, ratios, date_cloture)
            max_tokens = 4096

        model = getattr(settings, "ANTHROPIC_MODEL", None) or "claude-sonnet-4-6"

        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0.4 if (is_bilan or is_cr) else 0.7,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )

        parts = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)
        return "".join(parts).strip() or "⚠️ Aucune réponse générée par l'IA."

    except anthropic.AuthenticationError:
        return ("⚠️ Analyse IA non disponible : clé API Anthropic invalide. "
                "Vérifiez ANTHROPIC_API_KEY dans le fichier .env")
    except anthropic.RateLimitError:
        return "⚠️ Analyse IA temporairement indisponible : quota API atteint. Réessayez dans quelques instants."
    except anthropic.APIStatusError as e:
        return f"⚠️ Erreur API Anthropic ({e.status_code}) : {str(e)[:200]}"
    except anthropic.APIConnectionError:
        return "⚠️ Analyse IA indisponible : problème de connexion à l'API Anthropic."
    except Exception as e:
        return f"⚠️ Erreur lors de la génération de l'analyse IA : {e.__class__.__name__}: {str(e)[:280]}"
