from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.credit_config import (
    create_credit_config,
    create_default_credit_config_for_org,
    get_credit_config_by_org,
    get_credit_stats_by_org,
    update_credit_config,
)
from app.schemas.credit_config import (
    CreditConfigCreate,
    CreditConfigPublic,
    CreditConfigUpdate,
    CreditStats,
)

router = APIRouter(
    prefix="/credit",
    tags=["credit"],
)


@router.get("/config", response_model=CreditConfigPublic)
async def get_credit_config_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Récupère la configuration de crédit de l'organisation.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent accéder à cette ressource.",
        )

    try:
        config = await get_credit_config_by_org(user_org_id)

        if not config:
            # Créer une configuration par défaut si elle n'existe pas
            config = await create_default_credit_config_for_org(user_org_id)

        return config
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération de la configuration: {str(e)}",
        )


@router.put("/config", response_model=CreditConfigPublic)
async def update_credit_config_endpoint(
    config_update: CreditConfigUpdate, current_user: dict = Depends(get_current_user)
):
    """
    Met à jour la configuration de crédit de l'organisation.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent modifier cette configuration.",
        )

    try:
        # Vérifier si la config existe
        existing_config = await get_credit_config_by_org(user_org_id)

        if not existing_config:
            # Créer la config si elle n'existe pas
            config_data = config_update.model_dump()
            config = await create_credit_config(user_org_id, config_data)
        else:
            # Mettre à jour la config existante
            config_data = config_update.model_dump()
            config = await update_credit_config(user_org_id, config_data)

        if not config:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la mise à jour de la configuration",
            )

        return config
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la mise à jour: {str(e)}",
        )


@router.post("/config", response_model=CreditConfigPublic)
async def create_credit_config_endpoint(
    config_create: CreditConfigCreate, current_user: dict = Depends(get_current_user)
):
    """
    Crée une nouvelle configuration de crédit pour l'organisation.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent créer cette configuration.",
        )

    try:
        config_data = config_create.model_dump()
        config = await create_credit_config(user_org_id, config_data)
        return config
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la création: {str(e)}",
        )


@router.get("/stats", response_model=CreditStats)
async def get_credit_stats_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Récupère les statistiques de crédit de l'organisation.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent accéder aux statistiques.",
        )

    try:
        stats = await get_credit_stats_by_org(user_org_id)
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des statistiques: {str(e)}",
        )


@router.get("/rates", response_model=Dict[str, float])
async def get_current_rates_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Récupère les taux actuels de l'organisation (pour affichage public).
    """
    user_org_id = current_user.get("organization_id")

    if not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Utilisateur non rattaché à une organisation.",
        )

    try:
        config = await get_credit_config_by_org(user_org_id)

        if not config:
            # Retourner des taux par défaut
            return {
                "taux_base": 5.0,
                "taux_premium": 3.5,
                "frais_dossier": 500,
            }

        return {
            "taux_base": config["taux_interet_base"],
            "taux_premium": config["taux_interet_premium"],
            "frais_dossier": config["frais_dossier"],
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des taux: {str(e)}",
        )
