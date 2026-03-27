"""
Service IA pour analyser une demande de crédit PME/PMI.
"""
from typing import Optional
from app.schemas.credit_pme import CreditPMERequest, PMECalculatedMetrics
from app.core.config import settings
from openai import OpenAI

# Initialiser le client OpenAI
client = None
if hasattr(settings, 'OPENAI_API_KEY') and settings.OPENAI_API_KEY:
    client = OpenAI(api_key=settings.OPENAI_API_KEY)


async def call_openai_analysis(system_prompt: str, user_prompt: str) -> str:
    """Appelle l'API OpenAI pour une analyse"""
    if not client:
        raise ValueError("OpenAI API key not configured")
    
    model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content
    except Exception as e:
        raise Exception(f"Erreur lors de l'appel à OpenAI: {str(e)}")


def clean_markdown(text: str) -> str:
    """
    Nettoie le texte en supprimant les marqueurs Markdown.
    """
    import re
    # Supprimer les titres markdown (# ## ### etc.)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Supprimer les listes avec astérisques ou tirets
    text = re.sub(r'^\s*[\*\-\+]\s+', '', text, flags=re.MULTILINE)
    # Supprimer les gras/italique markdown
    text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)  # **texte** -> texte
    text = re.sub(r'\*([^\*]+)\*', r'\1', text)  # *texte* -> texte
    text = re.sub(r'__([^_]+)__', r'\1', text)  # __texte__ -> texte
    text = re.sub(r'_([^_]+)_', r'\1', text)  # _texte_ -> texte
    # Supprimer les liens markdown [texte](url) -> texte
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Nettoyer les espaces multiples
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def build_pme_analysis_prompt(
    request: CreditPMERequest,
    metrics: PMECalculatedMetrics
) -> str:
    """
    Construit le prompt pour l'analyse IA d'une demande de crédit PME.
    """
    # Construire le tableau des données financières
    financial_table = ""
    for data in sorted(request.donnees_financieres, key=lambda x: x.year):
        financial_table += f"\nAnnée {data.year}:\n"
        financial_table += f"- CA: {data.chiffre_affaires} {request.currency}\n"
        financial_table += f"- EBE (Excédent Brut d'Exploitation): {data.ebitda} {request.currency}\n"
        financial_table += f"- Résultat net: {data.resultat_net} {request.currency}\n"
        financial_table += f"- Fonds propres: {data.fonds_propres} {request.currency}\n"
        financial_table += f"- Dettes financières: {data.dettes_financieres_totales} {request.currency}\n"
        financial_table += f"- Charges financières: {data.charges_financieres} {request.currency}\n"
        financial_table += f"- Trésorerie: {data.tresorerie} {request.currency}\n"
        if data.stocks is not None:
            financial_table += f"- Stocks: {data.stocks} {request.currency}\n"
        if data.creances_clients is not None:
            financial_table += f"- Créances clients: {data.creances_clients} {request.currency}\n"
        if data.dettes_fournisseurs is not None:
            financial_table += f"- Dettes fournisseurs: {data.dettes_fournisseurs} {request.currency}\n"
    
    prompt = f"""Tu es un analyste senior du risque de crédit (banque). Tu dois produire une NOTE INTERNE d'analyse de dossier destinée à un analyste crédit / comité de crédit.
Tu réponds en français, sans utiliser de markdown (pas de #, *, **, etc.).

RÈGLES DE STYLE (OBLIGATOIRES):
- Adresse-toi au lecteur interne (analyste / comité), pas à l'entreprise.
- Ne rédige pas de lettre à l'entreprise (pas de "nous vous informons", pas de "vous").
- Parle de l'entreprise à la 3e personne: "l'entreprise", "le demandeur", "la PME".

Analyse cette demande de crédit PME et donne une décision (APPROUVE, REFUSE, ou CONDITIONNEL) avec une justification détaillée et actionnable.

RÈGLE DE LANGUE (OBLIGATOIRE):
- N'utilise aucun terme de ratio en anglais (interdits: "Debt/Equity", "Current Ratio", "Quick Ratio", "Interest Coverage", "Loan-to-Value").
- Utilise uniquement les intitulés français ci-dessous.

PROFIL ENTREPRISE:
- Raison sociale: {request.raison_sociale}
- Secteur d'activité: {request.secteur_activite}
- Taille: {request.taille}
- Nombre d'employés: {request.nombre_employes or 'Non renseigné'}
- Année de création: {request.annee_creation} (ancienneté: {2025 - request.annee_creation} ans)
- Forme juridique: {request.forme_juridique}
- Positionnement: {request.positionnement or 'Non renseigné'}

DONNÉES FINANCIÈRES:
{financial_table}

RATIOS CALCULÉS:
- Croissance CA: {metrics.croissance_ca or 'N/A'}%
- Marge EBE: {metrics.ebitda_margin or 'N/A'}%
- Marge nette: {metrics.net_margin or 'N/A'}%
- Ratio d'endettement (Dettes financières / Fonds propres): {metrics.debt_to_equity or 'N/A'}%
- Dette/EBE: {metrics.debt_to_ebitda or 'N/A'}
- Couverture des intérêts (EBE / Charges financières): {metrics.interest_coverage or 'N/A'}
- Capacité de remboursement (DSCR = CAF / Service annuel de la dette): {metrics.debt_service_coverage or 'N/A'}
- Poids nouvelle échéance dans CAF: {metrics.new_installment_weight or 'N/A'}%
- Ratio de liquidité générale (Actif courant / Passif courant): {metrics.current_ratio or 'N/A'}
- Ratio de liquidité immédiate ((Actif courant - Stocks) / Passif courant): {metrics.quick_ratio or 'N/A'}
- Ratio Crédit/Valeur des garanties (si applicable): {metrics.ltv or 'N/A'}%
- CAF annuelle: {metrics.caf_annuelle} {request.currency}
- Nouvelle mensualité: {metrics.nouvelle_mensualite} {request.currency}/mois
- Service annuel dette totale: {metrics.service_annuel_dette} {request.currency}

CRÉDIT DEMANDÉ:
- Montant: {request.montant} {request.currency}
- Objet: {request.objet}
- Durée: {request.duree_mois} mois
- Type remboursement: {request.type_remboursement}
- Garanties: {request.garanties or 'Non renseigné'}
- Valeur garanties: {request.valeur_garanties or 'N/A'} {request.currency}
- Source remboursement: {request.source_remboursement}

CONTEXTE RISQUE:
- Concentration clients: {request.concentration_clients or 'Non renseigné'}
- Dépendance fournisseur: {request.dependance_fournisseur or 'Non renseigné'}
- Historique incidents: {request.historique_incidents or 'Aucun incident signalé'}

DÉFINITIONS DES SIGLES ET FORMULES DE CALCUL:

CA (Chiffre d'Affaires):
- Définition: Revenus totaux de l'entreprise provenant de son activité
- Formule: CA = Somme de toutes les ventes de biens et services

EBE (Excédent Brut d'Exploitation, équivalent de l'EBITDA):
- Définition: Résultat d'exploitation avant intérêts, impôts et amortissements. Indicateur clé de la performance opérationnelle.
- Formule (simplifiée): EBE = CA - Charges d'exploitation (hors amortissements)
- Alternative: EBE = Résultat d'exploitation + Amortissements
- Utilité: Mesure la rentabilité opérationnelle sans tenir compte de la structure financière

CAF (Capacité d'Autofinancement):
- Définition: Flux de trésorerie généré par l'exploitation, utilisé pour rembourser les dettes et investir.
- Formule principale: CAF = Résultat net + Amortissements
- Formule alternative: CAF ≈ EBE - Impôts (approximation: CAF ≈ EBE × 0.75)
- Utilité: Indique la capacité réelle de l'entreprise à générer de la trésorerie

BFR (Besoin en Fonds de Roulement):
- Définition: Besoin de financement lié au cycle d'exploitation
- Formule: BFR = Stocks + Créances clients - Dettes fournisseurs
- Utilité: Mesure le besoin de financement pour faire tourner l'activité

Ratio d'endettement (Dettes financières / Fonds propres):
- Définition: Mesure le levier financier de l'entreprise
- Formule: (Dettes financières / Fonds propres) × 100
- Seuil acceptable: < 100% (idéalement < 50%)
- Utilité: Indique la proportion de dettes par rapport aux fonds propres

Dette/EBE:
- Définition: Indique combien d'années d'EBE sont nécessaires pour rembourser la dette totale
- Formule: Dette/EBE = Dettes financières / EBE
- Seuil acceptable: < 3 à 5 selon le secteur
- Utilité: Mesure la capacité de remboursement de la dette

Couverture des intérêts:
- Définition: Mesure la capacité de l'entreprise à payer les intérêts de ses dettes
- Formule: EBE / Charges financières
- Seuil acceptable: > 3 (idéalement > 5)
- Utilité: Indique si l'EBE couvre largement les intérêts

Capacité de remboursement (DSCR):
- Définition: Mesure la capacité à rembourser le service annuel de la dette (intérêts + principal)
- Formule: CAF / Service annuel de la dette
- Service annuel de la dette = Charges financières + Remboursement principal annuel
- Seuil acceptable: > 1.2 (idéalement > 1.5)
- Utilité: Indicateur clé pour évaluer la viabilité d'un nouveau crédit

Ratio de liquidité générale:
- Définition: Mesure la capacité à honorer les dettes à court terme
- Formule: Actif courant / Passif courant
- Actif courant = Trésorerie + Stocks + Créances clients
- Passif courant = Dettes fournisseurs + Dettes court terme
- Seuil acceptable: > 1.5 (idéalement entre 1.5 et 2.5)
- Utilité: Indique la solvabilité à court terme

Ratio de liquidité immédiate:
- Définition: Mesure la liquidité immédiate sans tenir compte des stocks
- Formule: (Actif courant - Stocks) / Passif courant
- Seuil acceptable: > 1 (idéalement > 1.2)
- Utilité: Plus strict que le current ratio, exclut les stocks qui peuvent être difficiles à liquider

Ratio Crédit/Valeur des garanties:
- Définition: Ratio Crédit/Valeur pour les crédits avec garantie réelle
- Formule: (Montant du crédit / Valeur des garanties) × 100
- Seuil acceptable: < 80% (idéalement < 70%)
- Utilité: Mesure le niveau de couverture par les garanties

INSTRUCTIONS POUR LA RÉPONSE (TRÈS IMPORTANT):
Tu dois donner une analyse TRÈS DÉTAILLÉE et COMPLÈTE. Chaque section doit être développée avec des explications précises.

1. DÉFINITIONS DES SIGLES
   Commence toujours par définir clairement tous les sigles utilisés avec leurs formules:
   - CA, EBE, CAF, BFR
   - Ratio d'endettement, Dette/EBE
   - Couverture des intérêts, DSCR
   - Ratio de liquidité générale, Ratio de liquidité immédiate
   - Ratio Crédit/Valeur des garanties

2. ANALYSE DE LA SOLIDITÉ FINANCIÈRE (Section détaillée)
   Analyse en profondeur:
   - La rentabilité (marges EBE et nette, évolution)
   - La croissance (croissance du CA, stabilité)
   - La structure financière (fonds propres, endettement)
   - La liquidité (ratios de liquidité, trésorerie)
   - L'ancienneté et la stabilité de l'entreprise

3. ANALYSE DE LA CAPACITÉ DE REMBOURSEMENT (Section détaillée)
   Analyse en profondeur:
   - La capacité de remboursement (DSCR): est-elle suffisante? (> 1.2 idéalement)
   - Le poids de la nouvelle échéance dans la CAF
   - La couverture des intérêts: l'entreprise peut-elle payer les intérêts?
   - La source de remboursement: est-elle fiable?
   - L'impact du nouveau crédit sur les ratios

4. IDENTIFICATION DES RISQUES (Section détaillée)
   Liste TOUS les risques identifiés:
   - Risques sectoriels
   - Risques de concentration (clients, fournisseurs)
   - Risques financiers (endettement élevé, liquidité faible, rentabilité insuffisante)
   - Risques opérationnels
   - Risques de remboursement
   - Autres risques spécifiques au dossier

5. DÉCISION (Section claire)
   Donne une décision claire: APPROUVE, REFUSE, ou CONDITIONNEL
   Justifie ta décision avec des arguments précis basés sur l'analyse

6. CONDITIONS (Si CONDITIONNEL)
   Si la décision est CONDITIONNEL, liste TOUTES les conditions:
   - Garanties supplémentaires requises
   - Covenants (ratios à maintenir)
   - Réduction du montant si nécessaire
   - Augmentation de la durée si applicable
   - Autres conditions spécifiques

7. RECOMMANDATIONS (Section détaillée)
   Donne des recommandations concrètes et actionnables:
   - Recommandations pour réduire le risque
   - Recommandations pour améliorer le dossier
   - Conseils pour le suivi du crédit
   - Pistes d'atténuation des risques

Format de réponse:
- Texte structuré avec des paragraphes clairs et détaillés
- PAS de markdown (pas de #, ##, *, **, etc.)
- Utilise des sauts de ligne pour séparer les sections
- Sois TRÈS DÉTAILLÉ et EXPLICATIF dans chaque section
- Minimum 600 mots pour une analyse complète
- Sois professionnel, précis et pédagogique"""
    
    return prompt


async def analyze_pme_credit_request(
    request: CreditPMERequest,
    metrics: PMECalculatedMetrics
) -> tuple[str, str, Optional[str]]:
    """
    Analyse une demande de crédit PME avec l'IA.
    
    Returns:
        (ai_analysis, ai_decision, ai_recommendations)
    """
    system_prompt = """Tu es un analyste senior en risque de crédit bancaire (PME/PMI).
Tu produis une note interne d'analyse destinée à un analyste crédit / comité.
Tu n'écris jamais de message adressé à l'entreprise.
Ta réponse doit être structurée, professionnelle et en français.
IMPORTANT: N'utilise JAMAIS de markdown (pas de #, ##, *, **, etc.). Utilise uniquement du texte simple avec des sauts de ligne."""
    
    user_prompt = build_pme_analysis_prompt(request, metrics)
    
    try:
        analysis = await call_openai_analysis(system_prompt, user_prompt)
        if not analysis:
            raise ValueError("OpenAI a retourné une analyse vide")
        
        # Nettoyer le markdown de la réponse
        analysis = clean_markdown(analysis)
        if not analysis:
            raise ValueError("Analyse vide après nettoyage")
        
        # Extraire la décision du texte
        decision = "CONDITIONNEL"
        if "APPROUVE" in analysis.upper() or "APPROUVÉ" in analysis.upper() or "ACCEPT" in analysis.upper():
            decision = "APPROUVE"
        elif "REFUSE" in analysis.upper() or "REFUSÉ" in analysis.upper() or "REJECT" in analysis.upper():
            decision = "REFUSE"
        
        # Extraire les recommandations si présentes
        recommendations = None
        lines = analysis.split('\n')
        rec_start = False
        rec_lines = []
        for line in lines:
            line_upper = line.upper()
            if "RECOMMANDATION" in line_upper or ("CONDITION" in line_upper and "CONDITIONNEL" not in line_upper):
                rec_start = True
            if rec_start and line.strip():
                rec_lines.append(line)
        
        if rec_lines:
            recommendations = '\n'.join(rec_lines)
            # Retirer les recommandations de l'analyse principale
            analysis = '\n'.join([line for line in lines if line not in rec_lines])
        
        return analysis, decision, recommendations
    except Exception as e:
        # En cas d'erreur IA, retourner une analyse par défaut
        default_analysis = f"""DÉFINITIONS DES SIGLES

CA (Chiffre d'Affaires): Revenus totaux de l'entreprise provenant de son activité.

EBE (Excédent Brut d'Exploitation, équivalent de l'EBITDA): Résultat d'exploitation avant intérêts, impôts et amortissements. Indicateur clé de la performance opérationnelle.

CAF (Capacité d'Autofinancement): Flux de trésorerie généré par l'exploitation, utilisé pour rembourser les dettes et investir. Formule approximative: CAF ≈ EBE × 0.75.

BFR (Besoin en Fonds de Roulement): Besoin de financement lié au cycle d'exploitation. BFR = Stocks + Créances clients - Dettes fournisseurs.

Debt/Equity (Gearing): Ratio d'endettement = (Dettes financières / Fonds propres) × 100. Mesure le levier financier de l'entreprise.

Dette/EBE: Ratio dette sur EBE = Dettes financières / EBE. Indique combien d'années d'EBE sont nécessaires pour rembourser la dette totale.

Interest Coverage: Couverture des intérêts = EBE / Charges financières. Mesure la capacité de l'entreprise à payer les intérêts de ses dettes.

Debt Service Coverage: Capacité de remboursement = CAF / Service annuel de la dette. Doit être supérieur à 1.2 pour être considéré comme viable.

Current Ratio: Ratio de liquidité = Actif courant / Passif courant. Mesure la capacité à honorer les dettes à court terme. Idéalement > 1.5.

Quick Ratio: Ratio de liquidité immédiate = (Actif courant - Stocks) / Passif courant. Plus strict que le current ratio car exclut les stocks. Idéalement > 1.

LTV (Loan-to-Value): Ratio Crédit/Valeur = (Montant du crédit / Valeur des garanties) × 100. Pour les crédits avec garantie réelle. Idéalement < 80%.

ANALYSE AUTOMATIQUE BASÉE SUR LES MÉTRIQUES

Ratios calculés:
- Croissance CA: {metrics.croissance_ca or 'N/A'}%
- Marge EBE: {metrics.ebitda_margin or 'N/A'}%
- Marge nette: {metrics.net_margin or 'N/A'}%
- Debt/Equity: {metrics.debt_to_equity or 'N/A'}%
- Dette/EBE: {metrics.debt_to_ebitda or 'N/A'}
- Interest Coverage: {metrics.interest_coverage or 'N/A'}
- Debt Service Coverage: {metrics.debt_service_coverage or 'N/A'}
- Poids nouvelle échéance: {metrics.new_installment_weight or 'N/A'}%
- Current Ratio: {metrics.current_ratio or 'N/A'}
- Quick Ratio: {metrics.quick_ratio or 'N/A'}
"""
        
        if metrics.debt_service_coverage and metrics.debt_service_coverage < 1:
            decision = "REFUSE"
            default_analysis += "\nDÉCISION: REFUSE\n\nLe Debt Service Coverage est inférieur à 1, ce qui signifie que l'entreprise n'a pas la capacité de rembourser ses dettes avec sa CAF."
        elif metrics.debt_service_coverage and metrics.debt_service_coverage < 1.2:
            decision = "CONDITIONNEL"
            default_analysis += "\nDÉCISION: CONDITIONNEL\n\nLe Debt Service Coverage est faible (< 1.2). Des garanties supplémentaires et des covenants sont requis."
        elif metrics.interest_coverage and metrics.interest_coverage < 1:
            decision = "REFUSE"
            default_analysis += "\nDÉCISION: REFUSE\n\nL'Interest Coverage est inférieur à 1, l'entreprise ne peut pas payer les intérêts de ses dettes."
        elif metrics.debt_to_equity and metrics.debt_to_equity > 200:
            decision = "CONDITIONNEL"
            default_analysis += "\nDÉCISION: CONDITIONNEL\n\nLe ratio Debt/Equity est très élevé (>200%), indiquant un endettement important. Des garanties supplémentaires sont requises."
        else:
            decision = "APPROUVE"
            default_analysis += "\nDÉCISION: APPROUVE\n\nLes ratios financiers sont acceptables et l'entreprise présente une capacité de remboursement suffisante."
        
        return default_analysis, decision, None

