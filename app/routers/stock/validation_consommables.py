from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.stock.validation_consommable import (
    create_validation_consommable_request,
    get_validation_consommable_by_id,
    list_validation_consommables_by_gestionnaire,
    list_validation_consommables_pending_drh,
    rejeter_consommable_modification_drh,
    valider_consommable_modification_drh,
)
from app.schemas.stock.validation_consommable import (
    ConsommableModificationRequestCreate,
    ConsommableModificationRequestPublic,
    ValidationConsommableDRH,
)

router = APIRouter(
    prefix="/stock/validation-consommables",
    tags=["stock-validation-consommables"],
)


@router.post("", response_model=ConsommableModificationRequestPublic)
async def create_validation_consommable_endpoint(
    request_in: ConsommableModificationRequestCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    Crée une demande de validation pour création/modification de consommable (gestionnaire de stock).
    """
    user_role = current_user.get("role", "user")
    user_id = current_user.get("id")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "gestionnaire_stock"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les gestionnaires de stock peuvent créer des demandes de validation.",
        )

    try:
        request_data = request_in.model_dump()
        validation_request = await create_validation_consommable_request(
            request_data, str(user_id), str(user_org_id)
        )
        return validation_request
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


@router.get("/gestionnaire/mes-demandes", response_model=List[ConsommableModificationRequestPublic])
async def list_my_validation_requests_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """
    Liste les demandes de validation du gestionnaire connecté.
    """
    user_id = current_user.get("id")
    user_role = current_user.get("role", "user")

    if user_role not in ["admin", "gestionnaire_stock"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les gestionnaires de stock peuvent voir leurs demandes.",
        )

    if not user_id:
        return []

    try:
        requests = await list_validation_consommables_by_gestionnaire(str(user_id))
        return requests
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.get("/drh/a-valider", response_model=List[ConsommableModificationRequestPublic])
async def list_validation_requests_pending_drh_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """
    Liste les demandes de validation de consommables en attente de validation DRH.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "agent_stock_drh"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les agents DRH peuvent valider les demandes de consommables.",
        )

    try:
        requests = await list_validation_consommables_pending_drh(str(user_org_id))
        return requests
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.get("/{request_id}", response_model=ConsommableModificationRequestPublic)
async def get_validation_request_endpoint(
    request_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère une demande de validation par son ID.
    """
    try:
        request = await get_validation_consommable_by_id(request_id)
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Demande introuvable.",
            )

        # Vérifier les permissions
        user_id = current_user.get("id")
        user_role = current_user.get("role", "user")
        user_org_id = current_user.get("organization_id")

        has_access = (
            request["gestionnaire_id"] == str(user_id)
            or (user_role in ["admin", "agent_stock_drh"])
            and request["organization_id"] == str(user_org_id)
        )

        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'avez pas accès à cette demande.",
            )

        return request
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.post("/{request_id}/valider")
async def valider_consommable_modification_endpoint(
    request_id: str,
    validation: ValidationConsommableDRH,
    current_user: dict = Depends(get_current_user),
):
    """
    Valide une demande de modification/création de consommable par l'agent DRH.
    """
    user_role = current_user.get("role", "user")
    user_id = current_user.get("id")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "agent_stock_drh"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les agents DRH peuvent valider les demandes de consommables.",
        )

    try:
        request = await get_validation_consommable_by_id(request_id)
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Demande introuvable.",
            )

        if request["organization_id"] != str(user_org_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez valider que les demandes de votre organisation.",
            )

        if request["statut"] != "en_attente":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cette demande a déjà été traitée.",
            )

        updated = await valider_consommable_modification_drh(
            request_id, str(user_id), validation.commentaire
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la validation.",
            )

        return updated
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la validation: {str(e)}",
        )


@router.post("/{request_id}/rejeter")
async def rejeter_consommable_modification_endpoint(
    request_id: str,
    validation: ValidationConsommableDRH,
    current_user: dict = Depends(get_current_user),
):
    """
    Rejette une demande de modification/création de consommable par l'agent DRH.
    """
    user_role = current_user.get("role", "user")
    user_id = current_user.get("id")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "agent_stock_drh"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les agents DRH peuvent rejeter les demandes de consommables.",
        )

    try:
        request = await get_validation_consommable_by_id(request_id)
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Demande introuvable.",
            )

        if request["organization_id"] != str(user_org_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez rejeter que les demandes de votre organisation.",
            )

        if request["statut"] != "en_attente":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cette demande a déjà été traitée.",
            )

        updated = await rejeter_consommable_modification_drh(
            request_id, str(user_id), validation.commentaire
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors du rejet.",
            )

        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du rejet: {str(e)}",
        )

