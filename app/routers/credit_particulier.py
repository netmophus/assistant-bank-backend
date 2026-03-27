"""
Endpoints pour le crédit particulier.
"""
import logging
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List

from app.schemas.credit_particulier import (
    CreditParticulierFieldConfig,
    CreditParticulierConfigPublic,
    CreditParticulierRequest,
    CreditParticulierAnalysis,
    CreditChatRequest,
    CreditChatResponse,
)
from app.models.credit_particulier import (
    get_credit_particulier_config,
    create_or_update_credit_particulier_config,
    create_credit_particulier_request,
    get_user_credit_requests,
    get_org_credit_requests,
)
from app.services.credit_calculations import calculate_credit_metrics
from app.services.credit_ai_service import analyze_credit_request, call_openai_analysis
from app.core.deps import get_current_user, get_org_admin
from app.models.credit_config import get_credit_config_by_org

router = APIRouter(
    prefix="/credit/particulier",
    tags=["credit-particulier"],
)


@router.get("/config", response_model=CreditParticulierConfigPublic)
async def get_config_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """Récupère la configuration des champs pour l'organisation (accessible à tous les utilisateurs)"""
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    config = await get_credit_particulier_config(org_id)
    if not config:
        # Créer une config par défaut
        default_config = CreditParticulierFieldConfig()
        config = await create_or_update_credit_particulier_config(org_id, default_config)
    
    return config


@router.put("/config", response_model=CreditParticulierConfigPublic)
async def update_config_endpoint(
    field_config: CreditParticulierFieldConfig,
    current_user: dict = Depends(get_org_admin),
):
    """Met à jour la configuration des champs"""
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    config = await create_or_update_credit_particulier_config(org_id, field_config)
    return config


@router.post("/analyze", response_model=CreditParticulierAnalysis)
async def analyze_credit_endpoint(
    request: CreditParticulierRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Analyse une demande de crédit particulier avec l'IA.
    """
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    # Récupérer la config de crédit pour obtenir le taux d'intérêt par défaut
    credit_config = await get_credit_config_by_org(org_id)
    default_interest_rate = credit_config.get("taux_interet_base", 5.0) / 100 if credit_config else 0.05
    
    # Utiliser le taux d'intérêt du formulaire s'il est fourni, sinon le taux par défaut
    logging.info(f"🔍 Taux d'intérêt reçu du formulaire: {request.annualInterestRate}")
    if request.annualInterestRate is not None:
        interest_rate = request.annualInterestRate / 100  # Convertir % en décimal
        logging.info(f"💰 Utilisation du taux d'intérêt du formulaire: {request.annualInterestRate}%")
    else:
        interest_rate = default_interest_rate
        logging.info(f"💰 Utilisation du taux d'intérêt par défaut: {default_interest_rate * 100}%")
    
    try:
        # Calculer les métriques
        metrics = calculate_credit_metrics(request, annual_interest_rate=interest_rate)
        
        # Analyser avec l'IA
        ai_analysis, ai_decision, ai_recommendations = await analyze_credit_request(request, metrics)
        
        # S'assurer que ai_decision n'est pas vide
        if not ai_decision:
            ai_decision = "CONDITIONNEL"  # Valeur par défaut
        
        # Sauvegarder la demande
        user_id = str(current_user.get("id") or current_user.get("_id"))
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ID utilisateur introuvable.",
            )
        
        saved_request = await create_credit_particulier_request(
            user_id=user_id,
            organization_id=org_id,
            request_data=request,
            calculated_metrics=metrics,
            ai_analysis=ai_analysis,
            ai_decision=ai_decision,
            ai_recommendations=ai_recommendations,
        )
        
        return saved_request
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'analyse: {str(e)}",
        )


@router.get("/requests", response_model=List[CreditParticulierAnalysis])
async def get_my_requests_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """Récupère les demandes de crédit de l'utilisateur connecté"""
    user_id = str(current_user.get("id") or current_user.get("_id"))
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID utilisateur introuvable.",
        )
    requests = await get_user_credit_requests(user_id)
    return requests


@router.get("/requests/org", response_model=List[CreditParticulierAnalysis])
async def get_org_requests_endpoint(
    current_user: dict = Depends(get_org_admin),
):
    """Récupère toutes les demandes de crédit de l'organisation"""
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    requests = await get_org_credit_requests(org_id)
    return requests


@router.post("/debug-openai")
async def debug_openai(
    current_user: dict = Depends(get_current_user),
):
    """Endpoint de debug pour tester OpenAI"""
    try:
        from app.services.credit_ai_service import client, settings
        
        logging.info("🔍 Debug OpenAI - Test de connexion")
        
        # Vérifier la clé API
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        logging.info(f"🔑 Clé API présente: {bool(api_key)}")
        if api_key:
            logging.info(f"🔑 Longueur clé: {len(api_key)}")
            logging.info(f"🔑 Début clé: {api_key[:10]}...")
        
        # Vérifier le client
        logging.info(f"🤖 Client initialisé: {client is not None}")
        
        # Test simple
        if client:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": "Dis simplement 'OK' en réponse"}
                ],
                timeout=10.0
            )
            result = response.choices[0].message.content
            return {"status": "ok", "response": result}
        else:
            return {"status": "error", "message": "Client non initialisé"}
            
    except Exception as e:
        logging.error(f"❌ Debug OpenAI erreur: {str(e)}")
        return {"status": "error", "message": str(e)}


@router.post("/chat", response_model=CreditChatResponse)
async def chat_about_credit_endpoint(
    chat_request: CreditChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Discute avec l'IA à propos d'un dossier de crédit analysé.
    """
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    try:
        # Construire le contexte du dossier
        dossier_context = f"""
DOSSIER DE CRÉDIT ANALYSÉ:

INFORMATIONS CLIENT:
- Nom: {chat_request.request_data.get('clientName', 'Non renseigné')}
- Statut professionnel: {chat_request.request_data.get('employmentStatus', 'Non renseigné')}
- Employeur: {chat_request.request_data.get('employerName', 'Non renseigné')}
- Secteur: {chat_request.request_data.get('employerSector', 'Non renseigné')}
- Contrat: {chat_request.request_data.get('contractType', 'Non renseigné')}
- Poste: {chat_request.request_data.get('position', 'Non renseigné')}

REVENUS:
- Salaire net mensuel: {chat_request.request_data.get('netMonthlySalary', 0)} XOF
- Autres revenus: {chat_request.request_data.get('otherMonthlyIncome', 0)} XOF
- Revenu total mensuel: {chat_request.calculated_metrics.get('totalMonthlyIncome', 0)} XOF

CHARGES ACTUELLES:
- Loyer/hypothèque: {chat_request.request_data.get('rentOrMortgage', 0)} XOF
- Autres charges: {chat_request.request_data.get('otherMonthlyCharges', 0)} XOF
- Prêts existants: {len(chat_request.request_data.get('existingLoans', []))} prêt(s)
- Total charges mensuelles: {chat_request.calculated_metrics.get('totalMonthlyCharges', 0)} XOF

CRÉDIT DEMANDÉ:
- Montant: {chat_request.request_data.get('loanAmount', 0)} XOF
- Durée: {chat_request.request_data.get('loanDurationMonths', 0)} mois
- Type: {chat_request.request_data.get('loanType', 'Non renseigné')}
- Mensualité: {chat_request.calculated_metrics.get('newLoanMonthlyPayment', 0)} XOF

MÉTRIQUES FINANCIÈRES:
- Taux d'endettement actuel: {chat_request.calculated_metrics.get('debtToIncomeRatio', 0)}%
- Nouveau taux d'endettement: {chat_request.calculated_metrics.get('newDebtToIncomeRatio', 0)}%
- Reste à vivre: {chat_request.calculated_metrics.get('resteAVivre', 0)} XOF
- Ratio Crédit/Revenu (LTI): {chat_request.calculated_metrics.get('loanToIncome', 0)}%
- Ratio Crédit/Valeur (LTV): {chat_request.calculated_metrics.get('loanToValue', 'N/A')}%
- Taux d'intérêt: {chat_request.calculated_metrics.get('annualInterestRate', 'N/A')}%
- Total des intérêts: {chat_request.calculated_metrics.get('totalInterestPaid', 0)} XOF

ANALYSE IA PRÉCÉDENTE:
- Décision: {chat_request.ai_decision or 'Non disponible'}
- Analyse: {chat_request.ai_analysis or 'Non disponible'}

"""
        
        # Construire l'historique de conversation
        conversation_history = ""
        if chat_request.messages:
            for msg in chat_request.messages:
                role_label = "Utilisateur" if msg.role == "user" else "Assistant"
                conversation_history += f"{role_label}: {msg.content}\n\n"
        
        # System prompt spécifique pour le chat
        system_prompt = """Tu es un expert-conseil en analyse de risque bancaire spécialisé dans les crédits particuliers.
Tu réponds en français, sans utiliser de markdown (pas de #, *, **, etc.).
Tu es pédagogue, précis et objectif dans tes réponses.

TON RÔLE:
1. **SPÉCIALISTE CRÉDIT** : Réponds à toutes les questions sur le crédit, les risques, les ratios
2. **CONSEILLER BANCAIRE** : Donne des conseils sur les produits bancaires, les démarches
3. **EXPERT FINANCIER** : Aide à comprendre les métriques financières (DTI, reste à vivre, etc.)
4. **ASSISTANT PERSONNEL** : Peut répondre à des questions générales si liées au contexte financier

RÈGLES IMPORTANTES:
- Si l'utilisateur dit "merci", "merci beaucoup", "ok", "d'accord", "compris", réponds simplement: "Je vous en prie ! Y a-t-il autre chose ?"
- Pour les questions crédit : Sois précis avec les chiffres du dossier
- Pour les questions bancaires : Donne des conseils généraux utiles
- Pour les questions hors sujet : Ramène poliment au sujet du crédit
- Ne répète jamais toute l'analyse si la question est simple
- Sois concis et direct"""
        
        # User prompt avec contexte + historique + nouvelle question
        user_prompt = f"""{dossier_context}

HISTORIQUE DE LA CONVERSATION:
{conversation_history}

QUESTION DE L'UTILISATEUR:
{chat_request.user_message}

Réponds de manière précise en te basant sur les données du dossier."""
        
        # Appeler l'IA
        assistant_response = await call_openai_analysis(system_prompt, user_prompt)
        
        # Nettoyer la réponse
        assistant_response = assistant_response.strip()
        
        # Mettre à jour l'historique des messages
        updated_messages = chat_request.messages.copy()
        updated_messages.append({"role": "user", "content": chat_request.user_message})
        updated_messages.append({"role": "assistant", "content": assistant_response})
        
        return CreditChatResponse(
            assistant_message=assistant_response,
            messages=updated_messages
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la conversation: {str(e)}",
        )

