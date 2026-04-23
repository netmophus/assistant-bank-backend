import logging
from typing import Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.deps import get_current_user
from app.core.db import get_database

logger = logging.getLogger(__name__)


def _to_org_oid(org_id) -> Optional[ObjectId]:
    """
    Cast l'organization_id (qui peut etre une string depuis le JWT ou deja
    un ObjectId) en ObjectId. Renvoie None si invalide.
    Necessaire pour eviter de creer des docs parasites avec _id en string.
    """
    if org_id is None:
        return None
    if isinstance(org_id, ObjectId):
        return org_id
    try:
        return ObjectId(str(org_id))
    except Exception:
        return None

router = APIRouter(
    prefix="/ai-config",
    tags=["ai-config"],
)

# Schémas Pydantic pour la validation
class AISearchConfig(BaseModel):
    source_priority: list[str] = ["ORG", "GLOBAL", "AI"]
    org_limit: int = 5
    global_limit: int = 3
    min_similarity_score: float = 0.7
    enable_global: bool = True
    enable_ai_fallback: bool = True
    filter_by_category: bool = False
    filter_by_department: bool = False

class QuotaConfig(BaseModel):
    global_quota: int = 1000
    default_user_quota: int = 100
    department_quotas: list[dict] = []
    service_quotas: list[dict] = []
    user_exceptions: list[dict] = []  # user_id, quota (null = illimité)

class AIResponseConfig(BaseModel):
    system_prompt: str = "Tu es un assistant IA expert en formation bancaire."
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 2000
    response_style: str = "professional"  # formal, professional, friendly, technical
    response_format: str = "markdown"  # markdown, text, structured
    include_user_context: bool = True
    include_department: bool = True
    include_service: bool = True
    custom_instructions: str = "Réponds de manière professionnelle et précise."

@router.get("/search-config")
async def get_search_config(
    current_user: dict = Depends(get_current_user),
):
    """Récupérer la configuration de recherche IA de l'organisation."""
    try:
        db = get_database()
        org_id = current_user.get("organization_id")
        
        # Si l'utilisateur n'a pas d'organisation_id, retourner la configuration par défaut
        if not org_id:
            logger.info(f"Utilisateur {current_user.get('id')} sans organisation_id - utilisation de la configuration par défaut")
            return DEFAULT_CONFIG
        
        # Récupérer la configuration depuis la collection organizations
        org = await db["organizations"].find_one({"_id": org_id})
        
        if not org:
            logger.warning(f"Organisation {org_id} non trouvée pour l'utilisateur {current_user.get('id')} - création d'une configuration par défaut")
            # Créer une configuration par défaut pour cette organisation
            default_config = {
                "source_priority": ["ORG", "GLOBAL", "AI"],
                "org_limit": 5,
                "global_limit": 3,
                "min_similarity_score": 0.7,
                "enable_global": True,
                "enable_ai_fallback": True,
                "filter_by_category": False,
                "filter_by_department": False,
            }
            
            # Insérer la configuration par défaut dans l'organisation
            await db["organizations"].update_one(
                {"_id": org_id},
                {"$set": {"ai_search_config": default_config}}
            )
            
            return default_config
        
        # Retourner la configuration existante
        config = org.get("ai_search_config")
        if config:
            return config
        
        # Si aucune configuration n'existe, créer la configuration par défaut
        logger.info(f"Aucune configuration trouvée pour l'organisation {org_id} - création de la configuration par défaut")
        default_config = {
            "source_priority": ["ORG", "GLOBAL", "AI"],
            "org_limit": 5,
            "global_limit": 3,
            "min_similarity_score": 0.7,
            "enable_global": True,
            "enable_ai_fallback": True,
            "filter_by_category": False,
            "filter_by_department": False,
        }
        
        await db["organizations"].update_one(
            {"_id": org_id},
            {"$set": {"ai_search_config": default_config}}
        )
        
        return default_config
        
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de la config recherche IA: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la récupération de la configuration"
        )

@router.put("/search-config")
async def update_search_config(
    config: AISearchConfig,
    current_user: dict = Depends(get_current_user),
):
    """Mettre à jour la configuration de recherche IA de l'organisation."""
    try:
        db = get_database()
        org_id = current_user.get("organization_id")
        
        # Si l'utilisateur n'a pas d'organisation_id, retourner un message informatif
        if not org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Impossible de sauvegarder la configuration: l'utilisateur n'est pas associé à une organisation"
            )
        
        # Valider les données
        if config.min_similarity_score < 0 or config.min_similarity_score > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le score de similarité doit être entre 0 et 1"
            )
        
        if config.org_limit < 1 or config.org_limit > 20:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La limite organisationnelle doit être entre 1 et 20"
            )
        
        if config.global_limit < 1 or config.global_limit > 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La limite globale doit être entre 1 et 10"
            )
        
        # Mettre à jour la configuration dans l'organisation
        result = await db["organizations"].update_one(
            {"_id": org_id},
            {"$set": {"ai_search_config": config.dict()}}
        )
        
        if result.matched_count == 0:
            logger.warning(f"Organisation {org_id} non trouvée lors de la mise à jour - création de l'organisation avec configuration")
            # Si l'organisation n'existe pas, la créer avec la configuration
            await db["organizations"].insert_one({
                "_id": org_id,
                "ai_search_config": config.dict(),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            })
        else:
            logger.info(f"Configuration recherche IA mise à jour pour l'organisation {org_id}")
        
        return {"message": "Configuration mise à jour avec succès"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour de la config recherche IA: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la mise à jour de la configuration"
        )

@router.get("/response-config")
async def get_response_config(
    current_user: dict = Depends(get_current_user),
):
    """Récupérer la configuration de réponse IA de l'organisation."""
    try:
        db = get_database()
        org_id = current_user.get("organization_id")
        
        # Si l'utilisateur n'a pas d'organisation_id, retourner la configuration par défaut
        if not org_id:
            logger.info(f"Utilisateur {current_user.get('id')} sans organisation_id - utilisation de la configuration par défaut")
            return {
                "system_prompt": "Tu es un assistant IA expert en formation bancaire.",
                "model": "gpt-4o-mini",
                "temperature": 0.7,
                "max_tokens": 2000,
                "response_style": "professional",
                "response_format": "markdown",
                "include_user_context": True,
                "include_department": True,
                "include_service": True,
                "custom_instructions": "Réponds de manière professionnelle et précise."
            }
        
        # Récupérer la configuration depuis la collection organizations
        org = await db["organizations"].find_one({"_id": org_id})
        
        if not org:
            logger.warning(f"Organisation {org_id} non trouvée pour l'utilisateur {current_user.get('id')} - création d'une configuration par défaut")
            # Créer une configuration par défaut pour cette organisation
            default_config = {
                "system_prompt": "Tu es un assistant IA expert en formation bancaire.",
                "model": "gpt-4o-mini",
                "temperature": 0.7,
                "max_tokens": 2000,
                "response_style": "professional",
                "response_format": "markdown",
                "include_user_context": True,
                "include_department": True,
                "include_service": True,
                "custom_instructions": "Réponds de manière professionnelle et précise."
            }
            
            # Insérer la configuration par défaut dans l'organisation
            await db["organizations"].update_one(
                {"_id": org_id},
                {"$set": {"ai_response_config": default_config}}
            )
            
            return default_config
        
        # Retourner la configuration existante
        config = org.get("ai_response_config")
        if config:
            return config
        
        # Si aucune configuration n'existe, créer la configuration par défaut
        logger.info(f"Aucune configuration trouvée pour l'organisation {org_id} - création de la configuration par défaut")
        default_config = {
            "system_prompt": "Tu es un assistant IA expert en formation bancaire.",
            "model": "gpt-4o-mini",
            "temperature": 0.7,
            "max_tokens": 2000,
            "response_style": "professional",
            "response_format": "markdown",
            "include_user_context": True,
            "include_department": True,
            "include_service": True,
            "custom_instructions": "Réponds de manière professionnelle et précise."
        }
        
        await db["organizations"].update_one(
            {"_id": org_id},
            {"$set": {"ai_response_config": default_config}}
        )
        
        return default_config
        
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de la config réponse IA: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la récupération de la configuration"
        )

@router.put("/response-config")
async def update_response_config(
    config: AIResponseConfig,
    current_user: dict = Depends(get_current_user),
):
    """Mettre à jour la configuration de réponse IA de l'organisation."""
    try:
        db = get_database()
        org_id = current_user.get("organization_id")
        
        # Si l'utilisateur n'a pas d'organisation_id, retourner un message informatif
        if not org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Impossible de sauvegarder la configuration: l'utilisateur n'est pas associé à une organisation"
            )
        
        # Valider les données
        if config.temperature < 0 or config.temperature > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La température doit être entre 0 et 1"
            )
        
        if config.max_tokens < 100 or config.max_tokens > 4000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le nombre maximum de tokens doit être entre 100 et 4000"
            )
        
        # Valider les valeurs autorisées
        valid_styles = ["formal", "professional", "friendly", "technical"]
        if config.response_style not in valid_styles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Le style de réponse doit être parmi: {', '.join(valid_styles)}"
            )
        
        valid_formats = ["markdown", "text", "structured"]
        if config.response_format not in valid_formats:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Le format de réponse doit être parmi: {', '.join(valid_formats)}"
            )
        
        # Mettre à jour la configuration dans l'organisation
        result = await db["organizations"].update_one(
            {"_id": org_id},
            {"$set": {"ai_response_config": config.dict()}}
        )
        
        if result.matched_count == 0:
            logger.warning(f"Organisation {org_id} non trouvée lors de la mise à jour - création de l'organisation avec configuration")
            # Si l'organisation n'existe pas, la créer avec la configuration
            await db["organizations"].insert_one({
                "_id": org_id,
                "ai_response_config": config.dict(),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            })
        else:
            logger.info(f"Configuration réponse IA mise à jour pour l'organisation {org_id}")
        
        return {"message": "Configuration mise à jour avec succès"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour de la config réponse IA: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la mise à jour de la configuration"
        )

@router.get("/quotas-config")
async def get_quotas_config(
    current_user: dict = Depends(get_current_user),
):
    """Récupérer la configuration des quotas de l'organisation."""
    try:
        db = get_database()
        org_id = current_user.get("organization_id")
        
        # Si l'utilisateur n'a pas d'organisation_id, retourner la configuration par défaut
        if not org_id:
            logger.info(f"Utilisateur {current_user.get('id')} sans organisation_id - utilisation de la configuration par défaut")
            return {
                "global_quota": 1000,
                "default_user_quota": 100,
                "department_quotas": [],
                "service_quotas": [],
                "user_exceptions": []
            }
        
        # Cast org_id en ObjectId pour eviter de creer un doc parasite avec _id string
        org_oid = _to_org_oid(org_id)
        if org_oid is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"organization_id invalide: {org_id}",
            )

        # Récupérer la configuration depuis la collection organizations
        org = await db["organizations"].find_one({"_id": org_oid})

        if not org:
            logger.error(f"Organisation {org_id} non trouvée — aucune config quotas retournée")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organisation introuvable.",
            )

        # Retourner la configuration existante
        config = org.get("quotas_config")
        if config:
            return config

        # Si aucune configuration n'existe, créer la configuration par défaut
        logger.info(f"Aucune configuration trouvée pour l'organisation {org_id} - création de la configuration par défaut")
        default_config = {
            "global_quota": 1000,
            "default_user_quota": 100,
            "department_quotas": [],
            "service_quotas": [],
            "user_exceptions": []
        }

        await db["organizations"].update_one(
            {"_id": org_oid},
            {"$set": {"quotas_config": default_config}}
        )

        return default_config
        
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de la config quotas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la récupération de la configuration"
        )

@router.put("/quotas-config")
async def update_quotas_config(
    config: QuotaConfig,
    current_user: dict = Depends(get_current_user),
):
    """Mettre à jour la configuration des quotas de l'organisation."""
    try:
        db = get_database()
        org_id = current_user.get("organization_id")
        
        # Si l'utilisateur n'a pas d'organisation_id, retourner un message informatif
        if not org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Impossible de sauvegarder la configuration: l'utilisateur n'est pas associé à une organisation"
            )
        
        # Valider les données
        if config.global_quota < 0 or config.global_quota > 10000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le quota global doit être entre 0 et 10000"
            )
        
        if config.default_user_quota < 0 or config.default_user_quota > 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le quota par défaut doit être entre 0 et 1000"
            )
        
        # Valider les quotas de départements et services
        for dept_quota in config.department_quotas:
            if dept_quota["quota"] < 0 or dept_quota["quota"] > 1000:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Le quota de département doit être entre 0 et 1000"
                )
        
        for service_quota in config.service_quotas:
            if service_quota["quota"] < 0 or service_quota["quota"] > 1000:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Le quota de service doit être entre 0 et 1000"
                )
        
        # Valider les exceptions utilisateur
        for user_exception in config.user_exceptions:
            if user_exception["quota"] is not None and (user_exception["quota"] < 0 or user_exception["quota"] > 1000):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Le quota d'utilisateur doit être entre 0 et 1000, ou null pour illimité"
                )
        
        # Cast org_id en ObjectId. Sans ca, l'update_one cherche par string,
        # ne trouve rien, et le bloc d'insert_one ci-dessous creait jadis un
        # doc parasite avec _id en string (bug DEMO).
        org_oid = _to_org_oid(org_id)
        if org_oid is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"organization_id invalide: {org_id}",
            )

        # Mettre à jour la configuration dans l'organisation
        result = await db["organizations"].update_one(
            {"_id": org_oid},
            {"$set": {"quotas_config": config.dict()}}
        )

        if result.matched_count == 0:
            # Ne JAMAIS creer un doc parasite ici. Si l'org n'existe pas
            # c'est une vraie erreur d'integrite — on remonte 404.
            logger.error(f"Organisation {org_id} non trouvée lors de la sauvegarde des quotas")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organisation introuvable.",
            )

        logger.info(f"Configuration quotas mise à jour pour l'organisation {org_id}")
        return {"message": "Configuration mise à jour avec succès"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour de la config quotas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la mise à jour de la configuration"
        )
