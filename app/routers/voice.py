"""
Router pour les endpoints de discussion vocale avec OpenAI Realtime API et ElevenLabs.
"""
from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Header, Request
from typing import Dict, Any, List
import os
import io
import base64
import httpx
import logging
from datetime import datetime

from app.schemas.voice_chat import (
    VoiceSessionRequest,
    VoiceSessionResponse,
    VoiceSessionStatus,
)
from app.services.voice_service import voice_service
from app.core.deps import get_current_user

router = APIRouter(
    prefix="/voice",
    tags=["voice-chat"],
)


def _extract_text_from_elevenlabs_payload(payload: Dict[str, Any]) -> str:
    """Best-effort extraction of the user query from various ElevenLabs webhook/tool payload shapes."""
    candidates = [
        payload.get("text"),
        payload.get("query"),
        payload.get("input"),
        payload.get("message"),
        payload.get("user_message"),
    ]

    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else None
    if tool_input:
        candidates.extend([
            tool_input.get("text"),
            tool_input.get("query"),
            tool_input.get("input"),
            tool_input.get("message"),
        ])

    data = payload.get("data") if isinstance(payload.get("data"), dict) else None
    if data:
        candidates.extend([
            data.get("text"),
            data.get("query"),
            data.get("input"),
            data.get("message"),
        ])

    for c in candidates:
        if isinstance(c, str) and c.strip():
            return c.strip()
    return ""


# ---------------------------------------------------------------------------
# Chat Vocal — Transcription (Whisper) + Synthèse (ElevenLabs)
# ---------------------------------------------------------------------------

@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Transcrit un fichier audio en texte via OpenAI Whisper API.
    Accepte les formats webm, mp4, wav, ogg, m4a.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY non configuré")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Fichier audio vide")

    logging.info(f"🎤 Transcription audio: {file.filename} ({len(audio_bytes)} bytes)")

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)

        # Whisper nécessite un nom de fichier avec extension valide
        filename = file.filename or "audio.webm"
        audio_file = (filename, io.BytesIO(audio_bytes), file.content_type or "audio/webm")

        transcription = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="fr",
        )

        text = transcription.text.strip()
        logging.info(f"✅ Transcription: '{text}'")
        return {"text": text}

    except Exception as e:
        logging.error(f"❌ Erreur Whisper: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur transcription: {str(e)}")


@router.post("/speak")
async def text_to_speech(
    data: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
):
    """
    Convertit du texte en audio via ElevenLabs TTS.
    Retourne l'audio encodé en base64.
    """
    text = data.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Texte manquant")

    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

    if not api_key:
        raise HTTPException(status_code=500, detail="ELEVENLABS_API_KEY non configuré")

    # Limiter le texte pour ne pas épuiser le quota ElevenLabs
    if len(text) > 3000:
        text = text[:3000] + "..."

    logging.info(f"🔊 TTS ElevenLabs: {len(text)} caractères, voix={voice_id}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                json={
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability": 0.55,
                        "similarity_boost": 0.75,
                        "style": 0.2,
                        "use_speaker_boost": True,
                    },
                },
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                timeout=60.0,
            )

            if response.status_code != 200:
                logging.error(f"❌ ElevenLabs TTS: {response.status_code} — {response.text}")
                detail = f"Erreur ElevenLabs: {response.status_code}"
                if os.getenv("DEBUG"):
                    detail = f"{detail} — {response.text}"
                raise HTTPException(
                    status_code=500,
                    detail=detail,
                )

            audio_b64 = base64.b64encode(response.content).decode()
            logging.info(f"✅ Audio généré: {len(response.content)} bytes")
            return {"audio_data": audio_b64}

    except HTTPException:
        raise
    except httpx.TimeoutException as e:
        logging.error(f"❌ ElevenLabs TTS timeout: {e}")
        raise HTTPException(
            status_code=504,
            detail="Timeout lors de l'appel ElevenLabs (synthèse vocale). Réessayez.",
        )
    except Exception as e:
        logging.error(f"❌ Erreur TTS: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur synthèse vocale: {str(e)}")

@router.get("/elevenlabs/voices")
async def get_elevenlabs_voices(
    current_user: dict = Depends(get_current_user),
):
    """
    Endpoint debug pour récupérer la liste des voix ElevenLabs disponibles.
    Permet de copier/coller un voice_id valide dans ELEVENLABS_VOICE_ID.
    """
    try:
        api_key = os.getenv("ELEVENLABS_API_KEY")
        
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="ELEVENLABS_API_KEY non configuré. Veuillez définir cette variable d'environnement."
            )
        
        logging.info("🔍 Récupération des voix ElevenLabs...")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={
                    "xi-api-key": api_key,
                    "Accept": "application/json"
                },
                timeout=15.0  # Réduit de 30s à 15s pour plus de rapidité
            )
            
            logging.info(f"📡 Réponse ElevenLabs voices: {response.status_code}")
            
            if response.status_code != 200:
                logging.error(f"❌ Erreur ElevenLabs voices: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Erreur ElevenLabs API: {response.status_code}"
                )
            
            voices_data = response.json()
            
            # Filtrer et retourner uniquement les voix nécessaires
            voices_list = []
            for voice in voices_data.get("voices", []):
                voices_list.append({
                    "name": voice.get("name", ""),
                    "voice_id": voice.get("voice_id", ""),
                    "category": voice.get("category", ""),
                    "description": voice.get("description", "")
                })
            
            logging.info(f"✅ {len(voices_list)} voix récupérées")
            
            return {
                "voices": voices_list,
                "total": len(voices_list),
                "message": "Copiez un voice_id dans ELEVENLABS_VOICE_ID"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"❌ Erreur lors de la récupération des voix: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne du serveur"
        )


@router.post("/elevenlabs/kb-tool")
async def elevenlabs_kb_tool(
    request: Request,
    x_elevenlabs_tool_secret: str | None = Header(default=None, alias="x-elevenlabs-tool-secret"),
):
    """Tool/Webhook endpoint for ElevenLabs ConvAI to query internal KB (RAG).

    Security:
    - Set env ELEVENLABS_TOOL_SECRET
    - Configure the agent to send header: x-elevenlabs-tool-secret: <secret>

    Org scoping:
    - Uses payload.organization_id / payload.org_id if present
    - Otherwise uses env ELEVENLABS_TOOL_ORG_ID
    """
    expected_secret = os.getenv("ELEVENLABS_TOOL_SECRET")
    if not expected_secret:
        raise HTTPException(status_code=500, detail="ELEVENLABS_TOOL_SECRET non configuré")
    if not x_elevenlabs_tool_secret or x_elevenlabs_tool_secret != expected_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    text = _extract_text_from_elevenlabs_payload(payload)
    if not text:
        raise HTTPException(status_code=400, detail="Texte manquant")

    organization_id = None
    if isinstance(payload, dict):
        organization_id = payload.get("organization_id") or payload.get("org_id")
        meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None
        if not organization_id and meta:
            organization_id = meta.get("organization_id") or meta.get("org_id")

    if not organization_id:
        organization_id = os.getenv("ELEVENLABS_TOOL_ORG_ID")

    try:
        allow_global = False
        if organization_id:
            from app.models.license import org_has_active_license

            allow_global = await org_has_active_license(str(organization_id))

        from app.services.rag_new_service import answer_question

        answer, _strategy, _sources, _debug = await answer_question(
            question=text,
            organization_id=str(organization_id) if organization_id else None,
            category=None,
            allow_global=allow_global,
        )
    except Exception as e:
        logging.error(f"❌ ElevenLabs KB tool error: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur KB: {str(e)}")

    # Return a flexible response shape to maximize compatibility with ElevenLabs tool parsers.
    return {
        "answer": answer,
        "result": answer,
        "text": answer,
    }

@router.get("/dossiers")
async def lister_dossiers_disponibles(
    current_user: dict = Depends(get_current_user),
):
    """
    Liste tous les dossiers de crédit disponibles pour l'assistant vocal.
    """
    try:
        from app.services.dossier_service import get_dossiers_disponibles
        
        dossiers = await get_dossiers_disponibles()
        
        return {
            "dossiers": dossiers,
            "total": len(dossiers)
        }
        
    except Exception as e:
        logging.error(f"❌ Erreur lors de la récupération des dossiers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne du serveur"
        )


@router.post("/process-command")
async def process_voice_command(
    request: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
):
    """
    Traite une commande vocale avec analyse IA de risque de crédit.
    Récupère le dossier, calcule les ratios, appelle OpenAI, génère l'audio.
    """
    import time
    start_time = time.time()
    
    try:
        text = request.get("text", "")
        dossier_id = request.get("dossier_id")
        conversation_history = request.get("conversation_history", [])
        
        logging.info(f"🎤 Commande vocale: '{text}' (dossier: {dossier_id})")
        
        # 1. Récupérer le dossier
        dossier_start = time.time()
        from app.services.dossier_service import get_dossier_by_id
        dossier = await get_dossier_by_id(dossier_id)
        dossier_time = time.time() - dossier_start
        logging.info(f"📂 Dossier récupéré en {dossier_time:.2f}s")
        
        if not dossier:
            # Plus de dossier démo, on utilise les vrais dossiers
            logging.error(f"❌ Dossier non trouvé: {dossier_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dossier {dossier_id} non trouvé. Veuillez d'abord analyser un dossier avec l'IA."
            )
        
        # 2. Calculer les ratios de risque avec les métriques complètes
        from app.services.credit_calculations import calculate_credit_metrics
        from app.services.credit_calculations import calculate_risk_ratios
        
        # Recréer les métriques complètes depuis les données du dossier
        request_data = dossier.get("request_data", {})
        credit_request = type('CreditRequest', (), {
            'clientName': request_data.get('clientName', 'Client'),
            'employmentStatus': request_data.get('employmentStatus', 'SALAIRE'),
            'employerName': request_data.get('employerName'),
            'employerSector': request_data.get('employerSector'),
            'employmentStartDate': request_data.get('employmentStartDate'),
            'contractType': request_data.get('contractType'),
            'position': request_data.get('position'),
            'probationEndDate': request_data.get('probationEndDate'),
            'netMonthlySalary': request_data.get('netMonthlySalary', 0),
            'otherMonthlyIncome': request_data.get('otherMonthlyIncome', 0),
            'incomeCurrency': request_data.get('incomeCurrency', 'XOF'),
            'rentOrMortgage': request_data.get('rentOrMortgage', 0),
            'otherMonthlyCharges': request_data.get('otherMonthlyCharges', 0),
            'existingLoans': request_data.get('existingLoans', []),
            'loanAmount': request_data.get('loanAmount', 0),
            'loanDurationMonths': request_data.get('loanDurationMonths', 0),
            'loanType': request_data.get('loanType', 'CONSO'),
            'propertyValue': request_data.get('propertyValue'),
            'annualInterestRate': request_data.get('annualInterestRate', 5.0) / 100 if request_data.get('annualInterestRate') else 0.05
        })()
        
        calculated_metrics = calculate_credit_metrics(credit_request)
        ratios = calculate_risk_ratios(dossier)
        
        logging.info(f"📊 Ratios calculés: DTI={ratios['endettement_avec_credit']}%, Reste à vivre={ratios['reste_a_vivre']} XOF")
        
        # 3. Analyse avec OpenAI Structured Outputs
        from app.services.credit_ai_service import analyze_credit_with_structured_output
        analyse = await analyze_credit_with_structured_output(
            dossier=dossier,
            ratios=ratios,
            calculated_metrics=calculated_metrics,
            question=text,
            historique=conversation_history
        )
        
        logging.info(f"🤖 Analyse IA: {analyse['decision_recommandee']} (score: {analyse['score_risque']}/100)")
        
        # Formater le texte pour une meilleure prononciation
        def format_numbers_for_speech(text: str) -> str:
            """Formate les nombres pour une meilleure prononciation en français."""
            import re
            
            # Convertir les grands nombres en mots
            def convert_number(match):
                num = int(match.group())
                
                if num >= 1_000_000:
                    millions = num // 1_000_000
                    reste = num % 1_000_000
                    if reste == 0:
                        return f"{millions} millions"
                    elif reste < 100_000:
                        return f"{millions} millions et {reste // 1000} mille"
                    else:
                        return f"{millions} millions {reste // 1000} mille"
                elif num >= 1000:
                    milliers = num // 1000
                    reste = num % 1000
                    if reste == 0:
                        return f"{milliers} mille"
                    else:
                        return f"{milliers} mille {reste}"
                else:
                    return str(num)
            
            # Remplacer les nombres par des mots
            text = re.sub(r'\b\d{1,9}\b', convert_number, text)
            
            # Remplacer XOF par "francs CFA"
            text = text.replace("XOF", "francs CFA")
            
            return text


        # 4. Générer l'audio avec ElevenLabs (uniquement reponse_courte)
        voice_id = os.getenv("ELEVENLABS_VOICE_ID")
        
        # Si pas de voice_id configuré, utiliser une voix française par défaut
        if not voice_id:
            logging.warning("⚠️ ELEVENLABS_VOICE_ID non configuré, utilisation de la voix française par défaut")
            voice_id = "21m00Tcm4TlvDq8ikWAM"  # Rachel (anglais) - à remplacer
        
        # Forcer une voix française si la configurée est anglaise
        french_voices = {
            "CwhRBWXzGAHq8TQ4Fs17": "21m00Tcm4TlvDq8ikWAM",  # Remplacer par Rachel (multilingue)
            "pNInz6obpgDQ0cT4KyVo": "21m00Tcm4TlvDq8ikWAM",  # Si l'ancienne voix française ne marche pas
        }
        
        if voice_id in french_voices:
            logging.info(f"🇫🇷 Remplacement de la voix par une voix multilingue française")
            voice_id = french_voices[voice_id]
        
        logging.info(f"🎙️ Voice ID utilisé: {voice_id}")
        
        if not voice_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="ELEVENLABS_VOICE_ID non configuré. Utilisez /voice/elevenlabs/voices pour obtenir un voice_id valide."
            )
        
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="ELEVENLABS_API_KEY non configuré"
            )
        
        logging.info("🌐 Génération audio avec ElevenLabs TTS...")
        
        # Formater le texte pour une meilleure prononciation
        formatted_text = format_numbers_for_speech(analyse["reponse_courte"])
        logging.info(f"📝 Texte original: {analyse['reponse_courte']}")
        logging.info(f"📝 Texte formaté: {formatted_text}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                json={
                    "text": formatted_text,
                    "model_id": "eleven_multilingual_v2",  # Meilleur pour le français
                    "voice_settings": {
                        "stability": 0.65,  # Plus naturel
                        "similarity_boost": 0.75,  # Plus expressif
                        "style": 0.3,  # Un peu de style
                        "use_speaker_boost": True  # Meilleure qualité
                    }
                },
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg"
                },
                timeout=15.0  # Réduit de 30s à 15s pour plus de rapidité
            )
            
            logging.info(f"📡 Réponse ElevenLabs TTS: {response.status_code}")
            
            if response.status_code != 200:
                error_detail = f"Erreur ElevenLabs TTS: {response.status_code}"
                try:
                    error_json = response.json()
                    error_detail += f" - {error_json.get('detail', {}).get('message', 'Unknown error')}"
                except:
                    error_detail += f" - {response.text}"
                
                logging.error(f"❌ {error_detail}")
                
                detail = error_detail if os.getenv("DEBUG") else "Erreur lors de la génération audio"
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=detail
                )
            
            # Convertir l'audio en base64
            audio_data = response.content
            logging.info(f"🎵 Audio reçu: {len(audio_data)} bytes")
            
            import base64
            audio_base64 = base64.b64encode(audio_data).decode()
            
            logging.info("✅ Audio encodé en base64")
            
            # 5. Mettre à jour l'historique (garder max 10 messages)
            updated_history = conversation_history[-9:] if len(conversation_history) > 9 else conversation_history
            updated_history.append({
                "role": "user",
                "content": text,
                "timestamp": str(datetime.now())
            })
            
            return {
                "reponse_courte": analyse["reponse_courte"],
                "reponse_detaillee": analyse["reponse_detaillee"],
                "audio_data": audio_base64,
                "analyse_complete": analyse,
                "ratios_calculés": ratios,
                "conversation_history": updated_history
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"❌ Erreur lors du traitement de la commande: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne du serveur"
        )

@router.get("/elevenlabs/signed-url")
async def get_elevenlabs_signed_url(
    current_user: dict = Depends(get_current_user),
):
    """
    Endpoint officiel pour obtenir une URL signée ElevenLabs ConvAI.
    """
    try:
        # Récupérer les variables d'environnement
        api_key = os.getenv("ELEVENLABS_API_KEY")
        agent_id = os.getenv("ELEVENLABS_AGENT_ID")
        
        logging.info("🔗 Génération URL signée ElevenLabs ConvAI:")
        logging.info(f"  - API Key exists: {bool(api_key)}")
        logging.info(f"  - API Key length: {len(api_key) if api_key else 0}")
        logging.info(f"  - startsWithSk: {api_key.startswith('sk-') if api_key else False}")
        if api_key:
            logging.info(f"  - firstChars: {api_key[:15]}...")
        
        logging.info(f"🤖 Agent ID demandé: {agent_id}")
        
        if not api_key or not agent_id:
            logging.error("❌ Configuration ElevenLabs manquante")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Configuration ElevenLabs manquante",
            )

        logging.info("🌐 Appel à l'API ElevenLabs...")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.elevenlabs.io/v1/convai/conversation/get-signed-url?agent_id={agent_id}",
                headers={
                    "xi-api-key": api_key,
                },
                timeout=15.0  # Réduit de 30s à 15s pour plus de rapidité
            )

            logging.info(f"📡 Réponse ElevenLabs: {response.status_code}")
            
            if response.status_code == 403:
                logging.error("❌ Erreur 403 - Clé API invalide ou permissions insuffisantes")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Clé API ElevenLabs invalide ou permissions insuffisantes. Vérifiez que votre clé a les permissions convai_write."
                )
            
            if response.status_code != 200:
                logging.error(f"❌ Erreur API ElevenLabs: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Erreur ElevenLabs: {response.status_code}",
                )

            data = response.json()
            
            return {
                "signed_url": data.get("signed_url"),
                "agent_id": agent_id
            }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"❌ Erreur lors de la génération de l'URL signée: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne du serveur"
        )


@router.post("/realtime/session", response_model=VoiceSessionResponse)
async def create_voice_session(
    request: VoiceSessionRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Crée une session vocale avec OpenAI Realtime API.
    
    Le client reçoit les informations nécessaires pour établir une connexion WebRTC
    sans jamais avoir accès à la clé OpenAI directement.
    """
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    try:
        session_response = await voice_service.create_realtime_session(request)
        return session_response
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la création de la session vocale: {str(e)}",
        )


@router.delete("/realtime/session/{session_id}")
async def end_voice_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Termine une session vocale active.
    """
    try:
        success = await voice_service.end_session(session_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session non trouvée ou déjà terminée.",
            )
        return {"message": "Session terminée avec succès"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la terminaison de la session: {str(e)}",
        )


@router.get("/realtime/session/{session_id}/status", response_model=VoiceSessionStatus)
async def get_session_status(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère le statut d'une session vocale.
    """
    try:
        status_info = await voice_service.get_session_status(session_id)
        if status_info["status"] == "not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session non trouvée.",
            )
        
        return VoiceSessionStatus(
            session_id=session_id,
            status=status_info["status"],
            duration_seconds=status_info.get("duration_seconds"),
            transcript_count=0  # À implémenter si besoin
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération du statut: {str(e)}",
        )


@router.get("/health")
async def voice_health_check():
    """Vérifie que le service vocal est opérationnel."""
    return {
        "status": "healthy",
        "service": "OpenAI Realtime API Voice Chat",
        "active_sessions": len(voice_service.active_sessions)
    }
