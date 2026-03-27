"""
Service ChatGPT pour l'analyse de crédit PME/PMI
Utilise OpenAI API pour fournir des réponses intelligentes sur les dossiers de crédit PME
"""

import os
import logging
from typing import Dict, Any, List
from openai import OpenAI

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")

if not OPENAI_API_KEY:
    logging.warning("⚠️ OPENAI_API_KEY non définie dans les variables d'environnement")
else:
    logging.info(f"✅ OPENAI_API_KEY configurée, modèle: {OPENAI_MODEL}")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Prompt système pour l'expert crédit PME
SYSTEM_PROMPT = """Tu es un expert bancaire spécialisé dans l'analyse de crédit PME/PMI avec plus de 15 ans d'expérience. 
Ton rôle est d'aider les utilisateurs à comprendre leur dossier de demande de crédit PME.

COMPÉTENCES :
- Analyse financière approfondie des PME
- Évaluation des risques sectoriels
- Interprétation des ratios financiers (EBE, CAF, BFR, Dette/EBE, etc.)
- Compréhension des garanties et conditions de remboursement
- Explication des décisions de crédit (APPROUVÉ/REFUSÉ/CONDITIONNEL)

STYLE DE RÉPONSE :
- Professionnel mais accessible
- Précis et factuel basé sur les données du dossier
- Pédagogique : explique les concepts financiers complexes
- Orienté vers l'action : donne des conseils pratiques
- En français uniquement

DONNÉES DISPONIBLES :
- Informations sur l'entreprise (secteur, taille, employés, etc.)
- Données financières sur 2-3 années
- Métriques calculées (ratios, indicateurs)
- Analyse IA complète
- Décision et recommandations

IMPORTANT :
- Base toutes tes réponses sur les données fournies
- Ne jamais inventer de données non présentes dans le dossier
- Si une information manque, indique-le clairement
- Fais référence aux métriques spécifiques du dossier
"""

def format_number(value):
    """Formate un nombre sans utiliser de locale pour éviter les erreurs"""
    if value is None:
        return "0"
    try:
        return f"{int(value):,}".replace(',', ' ')
    except (ValueError, TypeError):
        return str(value)

def format_pme_context(request_data: Dict, calculated_metrics: Dict, ai_analysis: str, ai_decision: str, ai_recommendations: str) -> str:
    """Formate les données du dossier PME pour ChatGPT"""
    
    context = f"""DOSSIER DE CRÉDIT PME/PMI :

INFORMATIONS ENTREPRISE :
- Raison sociale : {request_data.get('raison_sociale', 'Non spécifié')}
- Secteur d'activité : {request_data.get('secteur_activite', 'Non spécifié')}
- Taille : {request_data.get('taille', 'Non spécifié')}
- Nombre d'employés : {request_data.get('nombre_employes', 'Non spécifié')}
- Année de création : {request_data.get('annee_creation', 'Non spécifié')}
- Forme juridique : {request_data.get('forme_juridique', 'Non spécifié')}
- Positionnement : {request_data.get('positionnement', 'Non spécifié')}

DEMANDE DE CRÉDIT :
- Montant demandé : {format_number(request_data.get('montant'))} XOF
- Objet : {request_data.get('objet', 'Non spécifié')}
- Durée : {request_data.get('duree_mois', 0)} mois
- Type de remboursement : {request_data.get('type_remboursement', 'Non spécifié')}
- Garanties : {request_data.get('garanties', 'Non spécifié')}
- Valeur des garanties : {format_number(request_data.get('valeur_garanties'))} XOF
- Source de remboursement : {request_data.get('source_remboursement', 'Non spécifié')}

DONNÉES FINANCIÈRES :
"""
    
    # Ajouter les données financières
    donnees_financieres = request_data.get('donnees_financieres', [])
    for i, annee in enumerate(donnees_financieres, 1):
        context += f"""
Année {annee.get('year', 'N/A')} :
- Chiffre d'affaires : {format_number(annee.get('chiffre_affaires'))} XOF
- EBE (Excédent Brut d'Exploitation) : {format_number(annee.get('ebitda'))} XOF
- Résultat net : {format_number(annee.get('resultat_net'))} XOF
- Fonds propres : {format_number(annee.get('fonds_propres'))} XOF
- Dettes financières : {format_number(annee.get('dettes_financieres_totales'))} XOF
- Charges financières : {format_number(annee.get('charges_financieres'))} XOF
- Trésorerie : {format_number(annee.get('tresorerie'))} XOF
"""
    
    # Ajouter les métriques calculées
    context += f"""

MÉTRIQUES CALCULÉES :
"""
    metric_labels = {
        "croissance_ca": "Croissance du CA (%)",
        "ebitda_margin": "Marge EBE (%)",
        "net_margin": "Marge nette (%)",
        "debt_to_equity": "Ratio d'endettement (Dettes financières / Fonds propres) (%)",
        "debt_to_ebitda": "Dette/EBE",
        "interest_coverage": "Couverture des intérêts (EBE / Charges financières)",
        "debt_service_coverage": "Capacité de remboursement (DSCR = CAF / Service annuel de la dette)",
        "new_installment_weight": "Poids nouvelle échéance dans CAF (%)",
        "current_ratio": "Ratio de liquidité générale (Actif courant / Passif courant)",
        "quick_ratio": "Ratio de liquidité immédiate ((Actif courant - Stocks) / Passif courant)",
        "ltv": "Ratio Crédit/Valeur des garanties (%)",
        "caf_annuelle": "CAF annuelle",
        "nouvelle_mensualite": "Nouvelle mensualité",
        "service_annuel_dette": "Service annuel de la dette",
    }

    for key, value in calculated_metrics.items():
        if value is None:
            continue
        label = metric_labels.get(key, key)
        context += f"- {label} : {value}\n"
    
    # Ajouter l'analyse et la décision
    context += f"""

ANALYSE IA COMPLÈTE :
{ai_analysis}

DÉCISION : {ai_decision}

RECOMMANDATIONS :
{ai_recommendations}
"""
    
    return context

async def analyze_pme_with_chatgpt(
    user_message: str,
    request_data: Dict,
    calculated_metrics: Dict,
    ai_analysis: str,
    ai_decision: str,
    ai_recommendations: str,
    conversation_history: List[Dict] = None
) -> Dict[str, Any]:
    """
    Analyse une demande de crédit PME avec ChatGPT en utilisant les données du dossier.
    """
    
    if not client:
        logging.error("❌ Client OpenAI non initialisé")
        return {
            "response": "Désolé, le service ChatGPT n'est pas disponible actuellement. Veuillez réessayer plus tard.",
            "error": "OpenAI client not initialized"
        }
    
    try:
        # Préparer le contexte
        context = format_pme_context(request_data, calculated_metrics, ai_analysis, ai_decision, ai_recommendations)
        
        # Préparer les messages pour ChatGPT
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Voici le contexte du dossier de crédit PME :\n\n{context}\n\nQuestion de l'utilisateur : {user_message}"}
        ]
        
        # Ajouter l'historique de conversation si disponible
        if conversation_history:
            for msg in conversation_history[-5:]:  # Limiter aux 5 derniers messages
                if msg.get('role') in ['user', 'assistant']:
                    messages.insert(-1, {
                        "role": msg['role'],
                        "content": msg['content']
                    })
        
        logging.info(f"🤖 Appel ChatGPT pour analyse PME : {user_message[:50]}...")
        logging.info(f"📋 Modèle utilisé: {OPENAI_MODEL}")
        logging.info(f"📝 Nombre de messages: {len(messages)}")
        
        # Appel à l'API OpenAI avec timeout
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,  # Utiliser le modèle configuré
                messages=messages,
                max_tokens=1000,
                temperature=0.7,
                top_p=0.9,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                timeout=30.0  # Timeout de 30 secondes
            )
        except Exception as api_error:
            logging.error(f"❌ Erreur API OpenAI: {str(api_error)}")
            raise api_error
        
        assistant_response = response.choices[0].message.content
        
        logging.info(f"✅ Réponse ChatGPT reçue : {len(assistant_response)} caractères")
        logging.info(f"💰 Tokens utilisés: {response.usage.total_tokens if response.usage else 'N/A'}")
        
        return {
            "response": assistant_response,
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            },
            "context_summary": {
                "secteur": request_data.get('secteur_activite'),
                "montant": request_data.get('montant'),
                "decision": ai_decision
            }
        }
        
    except Exception as e:
        logging.error(f"❌ Erreur lors de l'appel ChatGPT : {str(e)}")
        return {
            "response": "Désolé, une erreur technique est survenue lors de l'analyse. Veuillez réessayer plus tard.",
            "error": str(e)
        }

def get_quick_response(user_message: str) -> str:
    """Génère des réponses rapides pour les messages courants"""
    
    message_lower = user_message.lower().strip()
    
    # Réponses de politesse
    if any(word in message_lower for word in ["merci", "merci beaucoup", "bien reçu", "ok", "parfait"]):
        return "Je vous en prie ! N'hésitez pas si vous avez d'autres questions sur votre dossier de crédit PME."
    
    # Salutations
    if any(word in message_lower for word in ["bonjour", "salut", "hello", "bonsoir"]):
        return "Bonjour ! Je suis votre assistant expert en crédit PME. Je peux vous aider à analyser votre dossier de crédit. Quelle est votre question ?"
    
    # Questions sur la décision
    if any(word in message_lower for word in ["décision", "résultat", "accepté", "refusé", "approuvé"]):
        return "Pour connaître la décision exacte concernant votre dossier, veuillez consulter la section 'Décision' dans votre analyse. Je peux vous aider à interpréter cette décision et ses implications."
    
    # Questions sur les garanties
    if any(word in message_lower for word in ["garantie", "hypothèque", "caution"]):
        return "Les garanties sont un élément important dans l'évaluation de votre dossier. Je peux analyser les garanties proposées et leur adéquation avec votre demande de crédit."
    
    return None  # Pas de réponse rapide, utiliser ChatGPT
