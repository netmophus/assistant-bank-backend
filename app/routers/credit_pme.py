"""
Endpoints pour le crédit PME/PMI.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List

from app.schemas.credit_pme import (
    CreditPMERequest,
    CreditPMEAnalysis,
)
from app.schemas.credit_pme_config import (
    CreditPMEFieldConfig,
    CreditPMEConfigPublic,
)
from app.models.credit_pme import (
    create_credit_pme_request,
    get_user_credit_pme_requests,
    get_org_credit_pme_requests,
)
from app.models.credit_pme_config import (
    get_credit_pme_config,
    create_or_update_credit_pme_config,
)
from app.services.credit_pme_calculations import calculate_pme_metrics
from app.services.credit_pme_ai_service import analyze_pme_credit_request
from app.routers.credit_particulier import chat_about_credit_endpoint
from app.routers.voice import process_voice_command
from app.core.deps import get_current_user, get_org_admin
from app.models.credit_config import get_credit_config_by_org

router = APIRouter(
    prefix="/credit/pme",
    tags=["credit-pme"],
)


@router.get("/config", response_model=CreditPMEConfigPublic)
async def get_pme_config_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """Récupère la configuration des champs PME pour l'organisation (accessible à tous les utilisateurs)"""
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    config = await get_credit_pme_config(org_id)
    if not config:
        # Créer une config par défaut
        default_config = CreditPMEFieldConfig()
        config = await create_or_update_credit_pme_config(org_id, default_config)
    
    return config


@router.put("/config", response_model=CreditPMEConfigPublic)
async def update_pme_config_endpoint(
    field_config: CreditPMEFieldConfig,
    current_user: dict = Depends(get_org_admin),
):
    """Met à jour la configuration des champs PME"""
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    config = await create_or_update_credit_pme_config(org_id, field_config)
    return config


@router.post("/analyze", response_model=CreditPMEAnalysis)
async def analyze_pme_credit_endpoint(
    request: CreditPMERequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Analyse une demande de crédit PME/PMI avec l'IA.
    """
    import logging
    logging.info(f"🏢 Début analyse PME pour: {request.secteur_activite}")
    
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    # Récupérer la config de crédit pour obtenir le taux d'intérêt
    credit_config = await get_credit_config_by_org(org_id)
    interest_rate = credit_config.get("taux_interet_base", 5.0) / 100 if credit_config else 0.05
    logging.info(f"💰 Taux d'intérêt utilisé: {interest_rate * 100}%")
    
    try:
        # Calculer les métriques
        logging.info("📊 Calcul des métriques PME...")
        metrics = calculate_pme_metrics(request, annual_interest_rate=interest_rate)
        logging.info(f"✅ Métriques calculées: {type(metrics).__name__}")
        
        # Analyser avec l'IA
        logging.info("🤖 Analyse avec l'IA...")
        ai_analysis, ai_decision, ai_recommendations = await analyze_pme_credit_request(request, metrics)
        logging.info(f"✅ Analyse IA terminée: {ai_decision}")
        
        # Sauvegarder la demande
        user_id = str(current_user.get("id") or current_user.get("_id"))
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ID utilisateur introuvable.",
            )
        
        logging.info("💾 Sauvegarde de la demande PME...")
        saved_request = await create_credit_pme_request(
            user_id=user_id,
            organization_id=org_id,
            request_data=request,
            calculated_metrics=metrics,
            ai_analysis=ai_analysis,
            ai_decision=ai_decision,
            ai_recommendations=ai_recommendations,
        )
        logging.info(f"✅ Demande PME sauvegardée: {saved_request.get('id')}")
        
        return saved_request
        
    except Exception as e:
        logging.error(f"❌ Erreur lors de l'analyse PME: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'analyse: {str(e)}",
        )


@router.get("/debug")
async def debug_pme_requests(
    current_user: dict = Depends(get_current_user),
):
    """Endpoint de debug pour vérifier les demandes PME"""
    import logging
    from app.core.db import get_database
    from bson import ObjectId
    
    user_id = str(current_user.get("id") or current_user.get("_id"))
    logging.info(f"🔍 Debug PME pour user_id: {user_id}")
    
    db = get_database()
    
    # Vérifier toutes les collections
    collections = await db.list_collection_names()
    logging.info(f"📂 Collections: {collections}")
    
    # Vérifier les demandes PME
    if "credit_pme_requests" in collections:
        cursor = db["credit_pme_requests"].find({})
        pme_requests = []
        async for doc in cursor:
            pme_requests.append({
                "id": str(doc["_id"]),
                "user_id": str(doc["user_id"]),
                "secteur": doc.get("request_data", {}).get("secteur_activite", "N/A"),
                "created_at": doc.get("created_at")
            })
        
        logging.info(f"📊 PME requests trouvées: {len(pme_requests)}")
        
        # Filtrer pour cet utilisateur
        user_requests = [r for r in pme_requests if r["user_id"] == user_id]
        logging.info(f"👤 Requests pour cet utilisateur: {len(user_requests)}")
        
        return {
            "total_pme_requests": len(pme_requests),
            "user_requests": len(user_requests),
            "all_requests": pme_requests[:5],  # Premier 5
            "user_id": user_id
        }
    else:
        return {"error": "Collection credit_pme_requests non trouvée"}


@router.get("/requests", response_model=List[CreditPMEAnalysis])
async def get_my_pme_requests_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """Récupère les demandes de crédit PME de l'utilisateur connecté"""
    import logging
    user_id = str(current_user.get("id") or current_user.get("_id"))
    logging.info(f"🔍 GET /credit/pme/requests pour user_id: {user_id}")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID utilisateur introuvable.",
        )
    
    requests = await get_user_credit_pme_requests(user_id)
    logging.info(f"📊 Retourne {len(requests)} demandes PME")
    
    # Log du premier élément pour debug
    if requests:
        logging.info(f"📋 Premier request: {requests[0].get('request_data', {}).get('secteur_activite', 'N/A')}")
    
    return requests


@router.get("/requests/org", response_model=List[CreditPMEAnalysis])
async def get_org_pme_requests_endpoint(
    current_user: dict = Depends(get_org_admin),
):
    """Récupère toutes les demandes de crédit PME de l'organisation"""
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    requests = await get_org_credit_pme_requests(org_id)
    return requests


# ===================== CHAT IA POUR PME =====================

@router.post("/chat")
async def chat_about_pme_credit_endpoint(
    request: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Chat IA pour discuter d'une demande de crédit PME avec ChatGPT.
    """
    import logging
    from app.services.pme_chatgpt_service import analyze_pme_with_chatgpt, get_quick_response
    
    logging.info(f"🏢 Chat PME reçu: {request.get('user_message', '')[:50]}...")
    logging.info(f"📊 Données reçues - request_data: {bool(request.get('request_data'))}, calculated_metrics: {bool(request.get('calculated_metrics'))}")
    
    # Récupérer le message et les données
    user_message = request.get("user_message", "")
    request_data = request.get("request_data", {})
    calculated_metrics = request.get("calculated_metrics", {})
    ai_analysis = request.get("ai_analysis", "")
    ai_decision = request.get("ai_decision", "")
    ai_recommendations = request.get("ai_recommendations", "")
    messages = request.get("messages", [])
    
    logging.info(f"📋 Secteur: {request_data.get('secteur_activite', 'N/A')}, Décision: {ai_decision}")
    
    if not user_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le message est requis."
        )
    
    # Vérifier si une réponse rapide est disponible (désactivé pour tester ChatGPT)
    quick_response = None  # get_quick_response(user_message)
    if quick_response:
        logging.info(f"⚡ Réponse rapide générée pour: {user_message[:30]}...")
        return {
            "response": quick_response,
            "messages": messages + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": quick_response}
            ]
        }
    
    logging.info("🤖 Appel au service ChatGPT (réponses rapides désactivées)...")
    
    # Utiliser ChatGPT pour l'analyse complète
    try:
        result = await analyze_pme_with_chatgpt(
            user_message=user_message,
            request_data=request_data,
            calculated_metrics=calculated_metrics,
            ai_analysis=ai_analysis,
            ai_decision=ai_decision,
            ai_recommendations=ai_recommendations,
            conversation_history=messages
        )
        
        if "error" in result:
            logging.error(f"❌ Erreur ChatGPT: {result['error']}")
            # Fallback vers réponse générique
            return {
                "response": f"Je suis l'assistant IA pour les crédits PME. Votre question '{user_message}' a été reçue. Je traite actuellement votre demande.",
                "messages": messages + [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": result["response"]}
                ]
            }
        
        # Mettre à jour l'historique des messages
        updated_messages = messages + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": result["response"]}
        ]
        
        logging.info(f"✅ Réponse ChatGPT générée: {len(result['response'])} caractères")
        
        return {
            "response": result["response"],
            "messages": updated_messages,
            "metadata": {
                "model": result.get("model"),
                "usage": result.get("usage"),
                "context": result.get("context_summary")
            }
        }
        
    except Exception as e:
        logging.error(f"❌ Erreur lors du traitement ChatGPT: {str(e)}")
        return {
            "response": "Désolé, une erreur technique est survenue. Veuillez réessayer plus tard.",
            "messages": messages + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": "Désolé, une erreur technique est survenue. Veuillez réessayer plus tard."}
            ]
        }


# ===================== VOICE ASSISTANT POUR PME =====================

@router.post("/voice/process-command")
async def process_pme_voice_command_endpoint(
    request: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Traite une commande vocale pour une demande de crédit PME avec ChatGPT et ElevenLabs.
    """
    import logging
    import os
    import httpx
    from fastapi import HTTPException, status
    from app.services.pme_chatgpt_service import analyze_pme_with_chatgpt, get_quick_response
    from app.models.credit_pme import get_user_credit_pme_requests
    
    logging.info(f"🎙️ Commande vocale PME reçue: {request.get('text', '')[:50]}...")
    
    # Récupérer les données de la requête
    text = request.get("text", "")
    dossier_id = request.get("dossier_id")
    conversation_history = request.get("conversation_history", [])
    
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le texte est requis."
        )
    
    # Récupérer les données du dossier si spécifié
    dossier_data = {}
    if dossier_id:
        try:
            user_id = str(current_user.get("id") or current_user.get("_id"))
            requests = await get_user_credit_pme_requests(user_id)
            dossier = next((r for r in requests if r.get("id") == dossier_id), None)
            
            if dossier:
                dossier_data = {
                    "request_data": dossier.get("request_data", {}),
                    "calculated_metrics": dossier.get("calculated_metrics", {}),
                    "ai_analysis": dossier.get("ai_analysis", ""),
                    "ai_decision": dossier.get("ai_decision", ""),
                    "ai_recommendations": dossier.get("ai_recommendations", ""),
                }
                logging.info(f"📂 Dossier PME trouvé: {dossier_data['request_data'].get('secteur_activite', 'Non spécifié')}")
        except Exception as e:
            logging.error(f"❌ Erreur récupération dossier PME: {e}")
    
    # Utiliser ChatGPT pour générer une réponse intelligente
    try:
        logging.info(f"🤖 Appel ChatGPT vocal pour: '{text}'")
        logging.info(f"📂 Données dossier disponibles: {bool(dossier_data)}")
        
        result = await analyze_pme_with_chatgpt(
            user_message=text,
            request_data=dossier_data.get("request_data", {}),
            calculated_metrics=dossier_data.get("calculated_metrics", {}),
            ai_analysis=dossier_data.get("ai_analysis", ""),
            ai_decision=dossier_data.get("ai_decision", ""),
            ai_recommendations=dossier_data.get("ai_recommendations", ""),
            conversation_history=conversation_history
        )
        
        logging.info(f"📊 Résultat ChatGPT vocal: {type(result)}")
        logging.info(f"📋 Clés du résultat: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")
        
        if "error" in result:
            response_text = f"Désolé, je ne peux pas traiter votre demande vocale actuellement. Votre commande '{text}' a été reçue."
            logging.warning(f"⚠️ Erreur dans résultat ChatGPT: {result.get('error')}")
        else:
            response_text = result["response"]
            logging.info(f"✅ Réponse ChatGPT vocale générée: {len(response_text)} caractères")
            
    except Exception as e:
        logging.error(f"❌ Erreur ChatGPT vocal: {str(e)}")
        response_text = f"Je suis l'assistant vocal pour les crédits PME. Votre commande '{text}' a été reçue."
        logging.info(f"🔄 Utilisation réponse de secours: {len(response_text)} caractères")
    
    # Générer l'audio avec ElevenLabs si configuré
    # TEMPORAIREMENT DÉSACTIVÉ - CRÉDITS ÉPUISÉS
    audio_base64 = None
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")
    api_key = os.getenv("ELEVENLABS_API_KEY")
    
    logging.info(f"🎤 Configuration ElevenLabs - Voice ID: {bool(voice_id)}, API Key: {bool(api_key)}")
    logging.info("🔇 Audio temporairement désactivé - Crédits ElevenLabs épuisés")
    
    # if voice_id and api_key:
    #     logging.info(f"🔊 Génération audio avec ElevenLabs - Voice: {voice_id}")
    #     try:
    #         async with httpx.AsyncClient() as client:
    #             response = await client.post(
    #                 f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
    #                 json={
    #                     "text": response_text,
    #                     "model_id": "eleven_multilingual_v2",
    #                     "voice_settings": {
    #                         "stability": 0.65,
    #                         "similarity_boost": 0.75,
    #                         "style": 0.0,
    #                         "use_speaker_boost": True,
    #                     },
    #                 },
    #                 headers={"xi-api-key": api_key},
    #             )
    #             
    #             if response.status_code == 200:
    #                 import base64
    #                 audio_base64 = base64.b64encode(response.content).decode()
    #                 logging.info("✅ Audio généré avec succès pour PME")
    #             else:
    #                 logging.warning(f"⚠️ Erreur génération audio: {response.status_code} - {response.text}")
    #     except Exception as e:
    #         logging.error(f"❌ Erreur génération audio PME: {e}")
    # else:
    #     logging.info("🔇 ElevenLabs non configuré - Pas de génération audio")
    #     logging.info(f"   Voice ID configuré: {bool(voice_id)}")
    #     logging.info(f"   API Key configurée: {bool(api_key)}")
    #     if not voice_id:
    #         logging.info("   → Ajoutez ELEVENLABS_VOICE_ID dans votre .env")
    #     if not api_key:
    #         logging.info("   → Ajoutez ELEVENLABS_API_KEY dans votre .env")
    
    return {
        "reponse_courte": response_text[:100] + "..." if len(response_text) > 100 else response_text,
        "reponse_detaillee": response_text,
        "audio_data": audio_base64,
        "analyse_complete": dossier_data,
        "conversation_history": conversation_history,
        "dossier_id": dossier_id
    }

