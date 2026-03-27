"""
Router FastAPI pour le moteur de décision de crédit particulier.

Endpoints:
  GET  /credit-policy/config              — Config active (tous utilisateurs)
  POST /credit-policy/config              — Créer/mettre à jour la config (admin)
  GET  /credit-policy/versions            — Historique des versions (admin)
  POST /credit-policy/restore/{id}        — Restaurer une version (admin)
  POST /credit-policy/analyze             — Analyser une demande de crédit
  GET  /credit-policy/applications        — Demandes de l'utilisateur courant
  GET  /credit-policy/applications/org    — Toutes les demandes de l'org (admin)
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Any, Dict

from app.core.deps import get_current_user, get_org_admin
from app.schemas.credit_policy import (
    CreditPolicyConfigCreate,
    CreditPolicyConfigPublic,
    CreditApplicationInput,
)
from app.models.credit_policy import (
    get_active_credit_policy,
    create_or_update_credit_policy,
    get_policy_versions,
    restore_policy_version,
    save_credit_application,
    get_user_applications,
    get_org_applications,
)
from app.services.credit_decision_engine import make_credit_decision

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/credit-policy", tags=["credit-policy"])


def _get_default_config(org_id: str) -> Dict[str, Any]:
    """Retourne une configuration par défaut si aucune n'est enregistrée."""
    from app.schemas.credit_policy import CreditPolicyConfigBase
    default = CreditPolicyConfigBase()
    return {
        **default.model_dump(),
        "id": "default",
        "organization_id": org_id,
        "version": "1.0",
        "status": "active",
        "effectiveDate": datetime.utcnow().isoformat(),
        "updatedAt": datetime.utcnow().isoformat(),
        "updatedBy": "",
    }


@router.get("/config", response_model=Dict[str, Any])
async def get_credit_policy_config(current_user: Any = Depends(get_current_user)):
    """
    Récupère la configuration active de crédit pour l'organisation de l'utilisateur.
    Retourne une configuration par défaut si aucune n'est enregistrée.
    """
    org_id = current_user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="L'utilisateur n'appartient à aucune organisation")

    config = await get_active_credit_policy(org_id)
    if config:
        return config
    return _get_default_config(org_id)


@router.post("/config", response_model=Dict[str, Any])
async def save_credit_policy_config(
    config_data: CreditPolicyConfigCreate,
    current_user: Any = Depends(get_org_admin)
):
    """
    Crée ou met à jour la configuration de crédit pour l'organisation.
    Nécessite le rôle admin. Archive automatiquement la version précédente.
    """
    org_id = current_user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="L'utilisateur n'appartient à aucune organisation")

    user_name = current_user.get("full_name") or current_user.get("email", "")
    user_id = current_user.get("id") or str(current_user.get("_id", ""))

    try:
        saved = await create_or_update_credit_policy(
            organization_id=org_id,
            config_data=config_data.model_dump(),
            user_id=user_id,
            user_name=user_name
        )
        return saved
    except Exception as e:
        logger.error(f"Erreur sauvegarde politique crédit: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la sauvegarde: {str(e)}")


@router.get("/versions", response_model=List[Dict[str, Any]])
async def list_policy_versions(current_user: Any = Depends(get_org_admin)):
    """
    Liste l'historique des versions de la configuration de crédit.
    Nécessite le rôle admin.
    """
    org_id = current_user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="L'utilisateur n'appartient à aucune organisation")
    return await get_policy_versions(org_id)


@router.post("/restore/{version_id}", response_model=Dict[str, Any])
async def restore_credit_policy_version(
    version_id: str,
    current_user: Any = Depends(get_org_admin)
):
    """
    Restaure une version archivée comme configuration active.
    Nécessite le rôle admin.
    """
    org_id = current_user.get("organization_id")
    user_id = current_user.get("id") or str(current_user.get("_id", ""))

    restored = await restore_policy_version(org_id, version_id, user_id)
    if not restored:
        raise HTTPException(status_code=404, detail="Version non trouvée")
    return restored


@router.post("/analyze", response_model=Dict[str, Any])
async def analyze_credit_application(
    application: CreditApplicationInput,
    current_user: Any = Depends(get_current_user)
):
    """
    Analyse une demande de crédit selon la politique active de l'organisation.

    Processus :
    1. Charge la configuration active
    2. Exécute le moteur de décision (règles + scoring + simulations)
    3. Persiste le résultat
    4. Retourne l'analyse complète
    """
    org_id = current_user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="L'utilisateur n'appartient à aucune organisation")

    user_id = current_user.get("id") or str(current_user.get("_id", ""))

    # Charger la configuration active
    config_doc = await get_active_credit_policy(org_id)
    if config_doc:
        try:
            config = CreditPolicyConfigPublic(**config_doc)
        except Exception as e:
            logger.warning(f"Config invalide, utilisation des défauts: {e}")
            config = CreditPolicyConfigPublic(**_get_default_config(org_id))
    else:
        config = CreditPolicyConfigPublic(**_get_default_config(org_id))

    # Exécuter le moteur de décision
    try:
        result = make_credit_decision(application, config)
    except Exception as e:
        logger.error(f"Erreur moteur décision: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur d'analyse: {str(e)}")

    # Persister la demande et le résultat
    result_dict = result.model_dump()
    try:
        saved = await save_credit_application(
            user_id=user_id,
            organization_id=org_id,
            application_data=application.model_dump(),
            result_data=result_dict
        )
        result_dict["record_id"] = saved.get("id")
    except Exception as e:
        logger.error(f"Erreur persistance: {e}")
        # Retourner le résultat même si la persistance échoue

    return result_dict


@router.get("/applications", response_model=List[Dict[str, Any]])
async def get_my_applications(current_user: Any = Depends(get_current_user)):
    """Récupère l'historique des demandes de crédit de l'utilisateur courant."""
    user_id = current_user.get("id") or str(current_user.get("_id", ""))
    return await get_user_applications(user_id)


@router.get("/applications/org", response_model=List[Dict[str, Any]])
async def get_org_all_applications(current_user: Any = Depends(get_org_admin)):
    """Récupère toutes les demandes de crédit de l'organisation. Nécessite le rôle admin."""
    org_id = current_user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="L'utilisateur n'appartient à aucune organisation")
    return await get_org_applications(org_id)
