"""
Service IA pour analyser une demande de crédit particulier avec Structured Outputs.
"""
from typing import Optional, Dict, Any, List
from app.schemas.credit_particulier import CreditParticulierRequest, CalculatedMetrics
from app.core.config import settings
from openai import OpenAI
import json
import logging

# Initialiser le client OpenAI
client = None
if hasattr(settings, 'OPENAI_API_KEY') and settings.OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        logging.info("✅ Client OpenAI initialisé avec succès")
    except Exception as e:
        logging.error(f"❌ Erreur d'initialisation OpenAI: {str(e)}")
else:
    logging.warning("⚠️ OPENAI_API_KEY non trouvée dans les settings")

# JSON Schema pour Structured Outputs
CREDIT_ANALYSIS_SCHEMA = {
    "name": "credit_analysis",
    "schema": {
        "type": "object",
        "properties": {
            "decision_recommandee": {
                "type": "string",
                "enum": ["APPROUVER", "REJETER", "REVOIR"],
                "description": "Décision recommandée pour le dossier de crédit"
            },
            "score_risque": {
                "type": "number",
                "minimum": 0,
                "maximum": 100,
                "description": "Score de risque (0 = faible risque, 100 = risque très élevé)"
            },
            "risques_principaux": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Liste des risques principaux identifiés"
            },
            "points_forts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Liste des points forts du dossier"
            },
            "conditions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Conditions à remplir pour l'approbation"
            },
            "infos_manquantes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Informations manquantes pour l'analyse complète"
            },
            "reponse_courte": {
                "type": "string",
                "description": "Réponse concise (1-2 phrases) pour la voix"
            },
            "reponse_detaillee": {
                "type": "string",
                "description": "Réponse détaillée pour l'affichage"
            }
        },
        "required": [
            "decision_recommandee",
            "score_risque",
            "risques_principaux",
            "points_forts",
            "conditions",
            "infos_manquantes",
            "reponse_courte",
            "reponse_detaillee"
        ]
    }
}


async def analyze_credit_with_structured_output(
    dossier: Dict[str, Any],
    ratios: Dict[str, Any],
    calculated_metrics: Dict[str, Any],
    question: str,
    historique: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Analyse un dossier de crédit avec OpenAI Structured Outputs.
    
    Args:
        dossier: Dossier de crédit complet
        ratios: Ratios calculés
        calculated_metrics: Métriques complètes avec taux d'intérêt
        question: Question du client
        historique: Historique de conversation (limité aux 6 derniers messages)
        
    Returns:
        Dict avec l'analyse structurée
    """
    if not client:
        raise ValueError("OpenAI API key not configured")
    
    # Limiter l'historique aux 6 derniers messages
    historique_limite = historique[-6:] if len(historique) > 6 else historique
    
    # Utiliser les vraies données brutes du dossier
    donnees_brutes = dossier.get("donnees_brutes", {})
    request_data = donnees_brutes.get("request_data", {})
    calculated_metrics = donnees_brutes.get("calculated_metrics", {})
    ai_analysis = donnees_brutes.get("ai_analysis", "")
    
    # Construire le prompt avec les vraies données
    system_prompt = f"""Tu es un analyste risque de crédit senior avec 15 ans d'expérience.
    
    Tu dois analyser ce dossier de crédit et répondre à la question du client de manière professionnelle et précise.
    
    RÈGLES IMPORTANTES:
    - Ne JAMAIS inventer de données. Utilise UNIQUEMENT les données fournies dans le dossier
    - Base tes analyses sur les vrais ratios calculés et l'analyse IA existante
    - Sois objectif et prudent dans ton évaluation du risque
    - La "reponse_courte" doit être complète et détaillée
    - La "reponse_courte" doit être naturelle et conversationnelle
    - La "reponse_courte" doit inclure des explications et des détails
    - La "reponse_detaillee" peut être plus technique et détaillée
    
    INSTRUCTIONS POUR LES RÉPONSES:
    - Commence par une phrase d'introduction contextuelle
    - Explique les chiffres et ratios avec des exemples concrets
    - Donne des conseils pratiques et utiles
    - Termine par une phrase de conclusion ou une suggestion
    - Utilise un langage professionnel mais accessible
    - Évite les réponses trop brèves comme "Oui" ou "Non"
    
    RÈGLES SPÉCIALES POUR RÉPONSES COURTES:
    - Si l'utilisateur dit "merci", "merci beaucoup", "ok", "d'accord", "compris", réponds simplement: "Je vous en prie ! Y a-t-il autre chose que je puisse faire pour vous concernant votre dossier ?"
    - Si l'utilisateur dit "au revoir", "bye", réponds: "Au revoir et bonne continuation pour votre projet !"
    - Si l'utilisateur dit "bonjour", "salut", réponds: "Bonjour ! Je suis votre assistant crédit. Comment puis-je vous aider aujourd'hui ?"
    
    DONNÉES RÉELLES DU DOSSIER:
    Client: {request_data.get('clientName', 'Client')}
    Profession: {request_data.get('employmentStatus', 'Non spécifié')}
    Employeur: {request_data.get('employerName', 'Non spécifié')}
    Contrat: {request_data.get('contractType', 'Non spécifié')}
    Ancienneté: {calculated_metrics.get('jobSeniorityMonths', 0)} mois
    
    DONNÉES FINANCIÈRES:
    Salaire net: {request_data.get('netMonthlySalary', 0)} XOF
    Autres revenus: {request_data.get('otherMonthlyIncome', 0)} XOF
    Total revenus: {calculated_metrics.get('totalMonthlyIncome', 0)} XOF
    
    CHARGES EXISTANTES:
    Loyer: {request_data.get('rentOrMortgage', 0)} XOF
    Autres charges: {request_data.get('otherMonthlyCharges', 0)} XOF
    Crédits existants: {len(request_data.get('existingLoans', []))}
    Total charges: {calculated_metrics.get('totalMonthlyCharges', 0)} XOF
    
    DEMANDE DE CRÉDIT:
    Montant: {request_data.get('loanAmount', 0)} XOF
    Durée: {request_data.get('loanDurationMonths', 0)} mois
    Type: {request_data.get('loanType', 'Non spécifié')}
    Taux d'intérêt: {calculated_metrics.get('annualInterestRate', 'Non spécifié')}%
    
    RATIOS CALCULÉS:
    Taux d'endettement actuel: {calculated_metrics.get('debtToIncomeRatio', 0)}%
    Taux d'endettement avec crédit: {calculated_metrics.get('newDebtToIncomeRatio', 0)}%
    Reste à vivre: {calculated_metrics.get('resteAVivre', 0)} XOF
    Mensualité du nouveau crédit: {calculated_metrics.get('newLoanMonthlyPayment', 0)} XOF
    Ratio Crédit/Revenu: {calculated_metrics.get('loanToIncome', 0)}%
    
    ANALYSE IA EXISTANTE:
    {ai_analysis[:500] if ai_analysis else "Aucune analyse existante"}
    
    HISTORIQUE CONVERSATION:
    {json.dumps(historique_limite, indent=2)}
    
    QUESTION CLIENT: {question}"""
    
    try:
        logging.info(" Appel à OpenAI avec Structured Outputs...")
        logging.info(f" Question: {question}")
        logging.info(f" Dossier: {request_data.get('clientName', 'Client')}")
        logging.info(f" Salaire: {request_data.get('netMonthlySalary', 0)} XOF")
        logging.info(f" Endettement: {calculated_metrics.get('newDebtToIncomeRatio', 0)}%")
        
        response = client.chat.completions.create(
            model="gpt-4o",  # Modèle qui supporte Structured Outputs
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyse ce dossier et réponds: {question}"}
            ],
            response_format={"type": "json_schema", "json_schema": CREDIT_ANALYSIS_SCHEMA},
            max_tokens=1600,
            temperature=0.3  # Plus de consistance
        )
        
        # Parser la réponse JSON
        analyse = json.loads(response.choices[0].message.content)
        logging.info(f" Analyse IA reçue: {analyse['decision_recommandee']} (score: {analyse['score_risque']}/100)")
        logging.info(f" Réponse courte: {analyse['reponse_courte']}")
        
        return analyse
        
    except Exception as e:
        logging.error(f" Erreur OpenAI: {str(e)}")
        # Fallback en cas d'erreur
        return generate_fallback_analysis(dossier, ratios, question)


def generate_fallback_analysis(dossier: Dict[str, Any], ratios: Dict[str, Any], question: str) -> Dict[str, Any]:
    """
    Génère une analyse de fallback en cas d'erreur OpenAI.
    """
    client_name = dossier.get("client", {}).get("nom", "Client")
    montant = dossier.get("demande", {}).get("montant", 0)
    duree = dossier.get("demande", {}).get("duree", 0)
    
    # Analyse basique basée sur les ratios
    endettement = ratios.get("endettement_avec_credit", 0)
    reste_a_vivre = ratios.get("reste_a_vivre", 0)
    
    if endettement > 40 or reste_a_vivre < 0:
        decision = "REJETER"
        score = 80
        risques = ["Taux d'endettement trop élevé", "Capacité de remboursement insuffisante"]
        points_forts = []
        conditions = []
        reponse_courte = f"Désolé {client_name}, votre demande de {montant} XOF est refusée car le taux d'endettement est trop élevé."
    elif endettement > 33:
        decision = "REVOIR"
        score = 60
        risques = ["Taux d'endettement élevé"]
        points_forts = ["Revenus stables"]
        conditions = ["Garanties supplémentaires requises"]
        reponse_courte = f"{client_name}, votre dossier nécessite une étude complémentaire. Des garanties pourraient être nécessaires."
    else:
        decision = "APPROUVER"
        score = 30
        risques = []
        points_forts = ["Taux d'endettement acceptable", "Capacité de remboursement suffisante"]
        conditions = []
        reponse_courte = f"Bonne nouvelle {client_name}, votre demande de {montant} XOF sur {duree} mois peut être approuvée."
    
    return {
        "decision_recommandee": decision,
        "score_risque": score,
        "risques_principaux": risques,
        "points_forts": points_forts,
        "conditions": conditions,
        "infos_manquantes": [],
        "reponse_courte": reponse_courte,
        "reponse_detaillee": f"Analyse automatisée du dossier de {client_name}: {decision}. Score risque: {score}/100."
    }


# Garder les anciennes fonctions pour compatibilité
async def call_openai_analysis(system_prompt: str, user_prompt: str) -> str:
    """Appelle l'API OpenAI pour une analyse (legacy)"""
    logging.info("🤖 Appel à call_openai_analysis (legacy)")
    
    # Forcer l'initialisation du client si nécessaire
    global client
    if not client:
        logging.info("🔄 Réinitialisation du client OpenAI...")
        if hasattr(settings, 'OPENAI_API_KEY') and settings.OPENAI_API_KEY:
            try:
                client = OpenAI(api_key=settings.OPENAI_API_KEY)
                logging.info("✅ Client OpenAI réinitialisé avec succès")
            except Exception as e:
                logging.error(f"❌ Erreur d'initialisation OpenAI: {str(e)}")
                raise ValueError("OpenAI API key not configured")
        else:
            logging.error("❌ OPENAI_API_KEY non trouvée dans les settings")
            raise ValueError("OpenAI API key not configured")
    
    logging.info(f"📝 Client OpenAI disponible: {client is not None}")
    
    model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
    logging.info(f"🎯 Modèle utilisé: {model}")
    
    try:
        logging.info("📡 Envoi à OpenAI...")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1600,
            timeout=120.0,  # Timeout de 120 secondes
        )
        result = response.choices[0].message.content
        logging.info(f"✅ Réponse OpenAI reçue: {len(result)} caractères")
        return result
    except Exception as e:
        error_msg = str(e)
        logging.error(f"❌ Erreur OpenAI dans call_openai_analysis: {error_msg}")
        
        # Si timeout, donner une réponse de fallback
        if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            logging.warning("⏰ Timeout OpenAI, utilisation du fallback")
            return "Désolé, je rencontre des difficultés techniques. Veuillez réessayer dans quelques instants. L'analyse de votre dossier montre que votre demande est en cours de traitement."
        
        raise Exception(f"Erreur lors de l'appel à OpenAI: {str(e)}")


def build_credit_analysis_prompt(
    request: CreditParticulierRequest,
    metrics: CalculatedMetrics
) -> str:
    """
    Construit le prompt pour l'analyse IA d'une demande de crédit.
    """
    prompt = f"""Tu es un analyste senior du risque de crédit (banque). Tu dois produire une NOTE INTERNE d'analyse de dossier destinée à un analyste crédit / comité de crédit.
Tu réponds en français, sans utiliser de markdown (pas de #, *, **, etc.).

RÈGLES DE STYLE (OBLIGATOIRES):
- Adresse-toi au lecteur interne (analyste / comité), pas au client.
- N'écris pas de lettre au client (interdits: "Je vous remercie", "Monsieur", "Madame", "vous" adressé au client).
- Parle du demandeur à la 3e personne: "le client", "le demandeur", ou "M. {request.clientName}".
- Sois factuel, chiffré, et orienté décision (risques, mitigations, conditions, avis).
- Si une donnée manque, mentionne le manque et l'impact sur l'analyse.

INFORMATIONS DU CLIENT:
- Nom: {request.clientName}
- Statut professionnel: {request.employmentStatus}
- Employeur: {request.employerName or 'Non renseigné'}
- Secteur: {request.employerSector or 'Non renseigné'}
- Type de contrat: {request.contractType or 'Non renseigné'}
- Poste: {request.position or 'Non renseigné'}
- Date d'embauche: {request.employmentStartDate.strftime('%Y-%m-%d') if request.employmentStartDate else 'Non renseigné'}
- En période d'essai: {'Oui' if metrics.enPeriodeEssai else 'Non'}
- Ancienneté: {metrics.jobSeniorityMonths or 0} mois

REVENUS:
- Salaire net mensuel: {request.netMonthlySalary} {request.incomeCurrency}
- Autres revenus: {request.otherMonthlyIncome} {request.incomeCurrency}
- Total revenus mensuels: {metrics.totalMonthlyIncome} {request.incomeCurrency}

CHARGES:
- Loyer/hypothèque: {request.rentOrMortgage} {request.incomeCurrency}
- Autres charges: {request.otherMonthlyCharges} {request.incomeCurrency}
- Prêts existants: {len(request.existingLoans)} prêt(s)
- Total charges mensuelles: {metrics.totalMonthlyCharges} {request.incomeCurrency}
- Taux d'endettement actuel: {metrics.debtToIncomeRatio}%

CRÉDIT DEMANDÉ:
- Type: {request.loanType}
- Montant: {request.loanAmount} {request.incomeCurrency}
- Durée: {request.loanDurationMonths} mois
- Mensualité: {metrics.newLoanMonthlyPayment} {request.incomeCurrency}
- Taux d'intérêt annuel: {metrics.annualInterestRate if metrics.annualInterestRate is not None else 'Non renseigné'}%
- Intérêts totaux estimés: {metrics.totalInterestPaid if metrics.totalInterestPaid is not None else 'Non renseigné'} {request.incomeCurrency}
- Coût total estimé (capital + intérêts): {(request.loanAmount + (metrics.totalInterestPaid or 0)) if metrics.totalInterestPaid is not None else 'Non renseigné'} {request.incomeCurrency}

MÉTRIQUES APRÈS PROJET:
- Nouvelles charges totales: {metrics.newTotalCharges} {request.incomeCurrency}
- Nouveau taux d'endettement: {metrics.newDebtToIncomeRatio}%
- Reste à vivre: {metrics.resteAVivre} {request.incomeCurrency}
- Ratio Crédit/Revenu annuel: {metrics.loanToIncome}%
{f'- Ratio Crédit/Valeur bien: {metrics.loanToValue}%' if metrics.loanToValue else ''}

DÉFINITIONS DES INDICATEURS FINANCIERS:
- Taux d'endettement: (Charges mensuelles / Revenus mensuels) × 100
- Ratio Crédit/Revenu: (Montant du crédit / Revenu annuel) × 100
- Ratio Crédit/Valeur: (Montant du crédit / Valeur du bien) × 100 (pour crédit immobilier)
- Reste à vivre: Revenus mensuels - Charges mensuelles totales

INSTRUCTIONS POUR LA RÉPONSE (TRÈS IMPORTANT):
Tu dois donner une analyse TRÈS DÉTAILLÉE et COMPLÈTE. Chaque section doit être développée avec des explications précises et une utilité décisionnelle.

RÈGLE DE COHÉRENCE (OBLIGATOIRE):
- Si le taux d'intérêt annuel est fourni dans les données (champ "Taux d'intérêt annuel" ci-dessus), ne dis jamais qu'il est "non précisé" ou "manquant".
- Si le taux n'est pas renseigné, indique explicitement qu'il manque et que cela impacte le calcul du coût total.

0. INTRODUCTION (Section OBLIGATOIRE)
   Commence TOUJOURS par une introduction qui présente:
   - L'identité du client (3e personne) et la situation professionnelle
   - Le type de crédit demandé, le montant, la durée, la mensualité
   - Le taux d'intérêt appliqué et le coût total (intérêts)
   - Un résumé chiffré: DTI actuel / DTI après projet / reste à vivre / LTI (et LTV si applicable)
   - Cette introduction doit faire au moins 50 mots

1. DÉFINITIONS ET MÉTHODES DE CALCUL (Section OBLIGATOIRE)
   Commence TOUJOURS par expliquer clairement comment chaque indicateur est calculé:
   - Taux d'endettement: Explique la formule (Charges mensuelles / Revenus mensuels) × 100
   - Reste à vivre: Explique la formule Revenus mensuels - Charges mensuelles totales
   - Ratio Crédit/Revenu: Explique (Montant du crédit / Revenu annuel) × 100
   - Mensualité: Explique comment elle est calculée avec le taux d'intérêt
   - Montant total: Explique mensualité × durée + intérêts

2. ANALYSE DE LA STABILITÉ PROFESSIONNELLE (Section détaillée)
   Analyse en profondeur:
   - L'ancienneté: Est-elle suffisante? Quel est le risque de perte d'emploi?
   - Le type de contrat: CDI est plus stable que CDD, etc.
   - La période d'essai: Si en période d'essai, explique le risque
   - Le secteur d'activité: Est-ce un secteur stable ou à risque?
   - L'employeur: Est-ce une entreprise stable?

3. ANALYSE DE LA CAPACITÉ DE REMBOURSEMENT (Section détaillée)
   Analyse en profondeur:
   - Le reste à vivre: Est-il suffisant? Peut-il faire face aux imprévus?
   - Le taux d'endettement actuel: Est-il acceptable?
   - Le nouveau taux d'endettement: Est-il dans les limites acceptables?
   - Les prêts existants: Analyse chaque prêt et son impact
   - La mensualité du nouveau crédit: Est-elle supportable?

4. IDENTIFICATION DES RISQUES (Section détaillée)
   Liste TOUS les risques identifiés:
   - Risques liés à l'emploi
   - Risques liés aux revenus
   - Risques liés à l'endettement
   - Risques liés à la capacité de remboursement
   - Autres risques spécifiques au dossier

5. DÉCISION (Section claire)
   Donne une décision claire: APPROUVE, REFUSE, ou CONDITIONNEL
   Justifie ta décision avec des arguments précis basés sur l'analyse

6. CONDITIONS (Si CONDITIONNEL)
   Si la décision est CONDITIONNEL, liste TOUTES les conditions:
   - Garanties requises (caution, hypothèque, etc.)
   - Réduction du montant si nécessaire
   - Augmentation de la durée si applicable
   - Autres conditions spécifiques

7. RECOMMANDATIONS (Section détaillée)
   Donne des recommandations concrètes et actionnables:
   - Mesures de mitigation (garanties, quotité, délégation salaire, assurance, etc.)
   - Points de vérification KYC / conformité et pièces à exiger
   - Recommandations de suivi (alertes, revue périodique, clauses)

Format de réponse:
- Texte structuré avec des paragraphes clairs et détaillés
- PAS de markdown (pas de #, ##, *, **, etc.)
- Utilise des sauts de ligne pour séparer les sections
- Sois TRÈS DÉTAILLÉ et EXPLICATIF dans chaque section
- La réponse doit être détaillée, mais évite toute longueur inutile
- Sois professionnel, précis et pédagogique
- UTILISE UNIQUEMENT LES TERMES EN FRANÇAIS"""
    
    return prompt


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


async def analyze_credit_request(
    request: CreditParticulierRequest,
    metrics: CalculatedMetrics
) -> tuple[str, str, Optional[str]]:
    """
    Analyse une demande de crédit avec l'IA.
    
    Returns:
        (ai_analysis, ai_decision, ai_recommendations)
    """
    system_prompt = """Tu es un analyste senior en risque de crédit bancaire.
Tu produis une note interne d'analyse destinée à un analyste crédit / comité.
Tu n'écris jamais de message adressé au client.
Ta réponse doit être structurée, professionnelle et en français.
IMPORTANT: N'utilise JAMAIS de markdown (pas de #, ##, *, **, etc.). Utilise uniquement du texte simple avec des sauts de ligne."""
    
    user_prompt = build_credit_analysis_prompt(request, metrics)
    
    try:
        analysis = await call_openai_analysis(system_prompt, user_prompt)
        
        # Nettoyer le markdown de la réponse
        analysis = clean_markdown(analysis)
        
        # Extraire la décision du texte - chercher d'abord REFUSE puis APPROUVE
        decision = "CONDITIONNEL"
        analysis_upper = analysis.upper()
        
        # Chercher REFUSE en premier (plus spécifique)
        if any(keyword in analysis_upper for keyword in ["REFUSE", "REFUSÉ", "REJECT"]):
            decision = "REFUSE"
        # Puis chercher APPROUVE seulement si REFUSE n'a pas été trouvé
        elif any(keyword in analysis_upper for keyword in ["APPROUVE", "APPROUVÉ", "ACCEPT"]):
            decision = "APPROUVE"
        
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

DTI (Debt-to-Income): Taux d'endettement = (Charges mensuelles / Revenus mensuels) × 100
LTI (Loan-to-Income): Ratio Crédit/Revenu = (Montant du crédit / Revenu annuel) × 100
LTV (Loan-to-Value): Ratio Crédit/Valeur = (Montant du crédit / Valeur du bien) × 100 (pour crédit immobilier)
Reste à vivre: Revenus mensuels - Charges mensuelles totales

ANALYSE AUTOMATIQUE BASÉE SUR LES MÉTRIQUES

Taux d'endettement après projet (DTI): {metrics.newDebtToIncomeRatio}%
Reste à vivre: {metrics.resteAVivre} {request.incomeCurrency}
Ratio Crédit/Revenu (LTI): {metrics.loanToIncome}%
"""
        
        if metrics.newDebtToIncomeRatio > 40:
            decision = "REFUSE"
            default_analysis += "\nDÉCISION: REFUSE\n\nLe taux d'endettement après projet dépasse 40%, ce qui représente un risque trop élevé pour la banque."
        elif metrics.newDebtToIncomeRatio > 33:
            decision = "CONDITIONNEL"
            default_analysis += "\nDÉCISION: CONDITIONNEL\n\nLe taux d'endettement est élevé (supérieur à 33%). Des garanties supplémentaires sont requises pour réduire le risque."
        elif metrics.resteAVivre < 0:
            decision = "REFUSE"
            default_analysis += "\nDÉCISION: REFUSE\n\nLe reste à vivre est négatif, ce qui signifie que les charges dépassent les revenus. Le client n'a pas la capacité de remboursement nécessaire."
        else:
            decision = "APPROUVE"
            default_analysis += "\nDÉCISION: APPROUVE\n\nLe profil du client est acceptable avec un taux d'endettement raisonnable et un reste à vivre positif."
        
        return default_analysis, decision, None

