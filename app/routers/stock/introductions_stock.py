from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.stock.introduction_stock import (
    create_introduction_stock,
    get_introduction_by_id,
    list_introductions_by_gestionnaire,
    list_introductions_pending_drh,
    rejeter_introduction_drh,
    valider_introduction_drh,
)
from app.schemas.stock.introduction_stock import (
    IntroductionStockCreate,
    IntroductionStockPublic,
    ValidationDRHStock,
)

router = APIRouter(
    prefix="/stock/introductions",
    tags=["stock-introductions"],
)


@router.post("", response_model=IntroductionStockPublic)
async def create_introduction_stock_endpoint(
    introduction_in: IntroductionStockCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    Crée une demande d'introduction de stock (gestionnaire de stock).
    """
    user_role = current_user.get("role", "user")
    user_id = current_user.get("id")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est gestionnaire de stock ou admin
    if user_role not in ["admin", "gestionnaire_stock"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les gestionnaires de stock peuvent introduire du stock.",
        )

    try:
        introduction_data = introduction_in.model_dump()
        introduction_data["gestionnaire_id"] = str(user_id)
        introduction_data["organization_id"] = str(user_org_id)

        introduction = await create_introduction_stock(introduction_data)
        return introduction
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


@router.get("/gestionnaire/mes-introductions", response_model=List[IntroductionStockPublic])
async def list_my_introductions_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """
    Liste les introductions de stock du gestionnaire connecté.
    """
    user_id = current_user.get("id")
    user_role = current_user.get("role", "user")

    if user_role not in ["admin", "gestionnaire_stock"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les gestionnaires de stock peuvent voir leurs introductions.",
        )

    if not user_id:
        return []

    try:
        introductions = await list_introductions_by_gestionnaire(str(user_id))
        return introductions
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.get("/drh/a-valider", response_model=List[IntroductionStockPublic])
async def list_introductions_pending_drh_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """
    Liste les introductions de stock en attente de validation DRH.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est agent DRH ou admin
    if user_role not in ["admin", "agent_stock_drh"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les agents DRH peuvent valider les introductions de stock.",
        )

    try:
        introductions = await list_introductions_pending_drh(str(user_org_id))
        return introductions
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.get("/{introduction_id}", response_model=IntroductionStockPublic)
async def get_introduction_endpoint(
    introduction_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère une introduction de stock par son ID.
    """
    try:
        introduction = await get_introduction_by_id(introduction_id)
        if not introduction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Introduction introuvable.",
            )

        # Vérifier les permissions
        user_id = current_user.get("id")
        user_role = current_user.get("role", "user")
        user_org_id = current_user.get("organization_id")

        has_access = (
            introduction["gestionnaire_id"] == str(user_id)
            or (user_role in ["admin", "agent_stock_drh"])
            and introduction["organization_id"] == str(user_org_id)
        )

        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'avez pas accès à cette introduction.",
            )

        return introduction
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.post("/{introduction_id}/valider")
async def valider_introduction_endpoint(
    introduction_id: str,
    validation: ValidationDRHStock,
    current_user: dict = Depends(get_current_user),
):
    """
    Valide une introduction de stock par l'agent DRH (applique la mise à jour du stock).
    """
    user_role = current_user.get("role", "user")
    user_id = current_user.get("id")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est agent DRH ou admin
    if user_role not in ["admin", "agent_stock_drh"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les agents DRH peuvent valider les introductions de stock.",
        )

    try:
        introduction = await get_introduction_by_id(introduction_id)
        if not introduction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Introduction introuvable.",
            )

        if introduction["organization_id"] != str(user_org_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez valider que les introductions de votre organisation.",
            )

        if introduction["statut"] != "en_attente":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cette introduction a déjà été traitée.",
            )

        updated = await valider_introduction_drh(
            introduction_id, str(user_id), validation.commentaire
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


@router.post("/{introduction_id}/rejeter")
async def rejeter_introduction_endpoint(
    introduction_id: str,
    validation: ValidationDRHStock,
    current_user: dict = Depends(get_current_user),
):
    """
    Rejette une introduction de stock par l'agent DRH.
    """
    user_role = current_user.get("role", "user")
    user_id = current_user.get("id")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est agent DRH ou admin
    if user_role not in ["admin", "agent_stock_drh"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les agents DRH peuvent rejeter les introductions de stock.",
        )

    try:
        introduction = await get_introduction_by_id(introduction_id)
        if not introduction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Introduction introuvable.",
            )

        if introduction["organization_id"] != str(user_org_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez rejeter que les introductions de votre organisation.",
            )

        if introduction["statut"] != "en_attente":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cette introduction a déjà été traitée.",
            )

        updated = await rejeter_introduction_drh(
            introduction_id, str(user_id), validation.commentaire
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
