from fastapi import APIRouter, HTTPException, status, Depends
from typing import List

from app.schemas.stock.consommable import ConsommableCreate, ConsommablePublic, ConsommableUpdate, StockUpdate
from app.schemas.stock.validation_consommable import ConsommableModificationRequestPublic
from app.models.stock.consommable import (
    create_consommable,
    list_consommables_by_org,
    list_consommables_available,
    get_consommable_by_id,
    update_consommable,
    delete_consommable,
    update_stock,
    get_consommables_low_stock,
)
from app.core.deps import get_current_user
from bson import ObjectId

router = APIRouter(
    prefix="/stock/consommables",
    tags=["stock-consommables"],
)


@router.post("", response_model=ConsommablePublic, status_code=status.HTTP_201_CREATED)
async def create_consommable_endpoint(
    consommable_in: ConsommableCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Crée un consommable pour l'organisation.
    - Admin : création directe
    - Gestionnaire de stock : crée une demande de validation
    """
    user_role = current_user.get("role", "user")
    user_id = current_user.get("id")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "gestionnaire_stock"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation et les gestionnaires de stock peuvent créer des consommables.",
        )
    
    try:
        consommable_data = consommable_in.model_dump()
        
        # Si admin : création directe
        if user_role == "admin":
            consommable = await create_consommable(consommable_data, str(user_org_id))
            return consommable
        
        # Si gestionnaire de stock : créer une demande de validation
        from app.models.stock.validation_consommable import create_validation_consommable_request
        
        request_data = {
            "action": "create",
            "consommable_data": consommable_data,
            "motif": None,
        }
        
        validation_request = await create_validation_consommable_request(
            request_data, str(user_id), str(user_org_id)
        )
        
        # Retourner une erreur avec le statut 202 pour indiquer que la demande est en attente
        # Le frontend devra gérer ce cas spécial
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "message": "Demande de création de consommable créée. Elle sera validée par l'agent DRH.",
                "validation_request": validation_request
            }
        )
    except HTTPException:
        raise
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


@router.get("", response_model=List[ConsommablePublic])
async def list_consommables_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Liste toutes les consommables de l'organisation (admin, gestionnaire de stock et agent DRH).
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "gestionnaire_stock", "agent_stock_drh"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs, gestionnaires de stock et agents DRH peuvent voir toutes les consommables.",
        )
    
    try:
        consommables = await list_consommables_by_org(str(user_org_id))
        return consommables
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.get("/user/available", response_model=List[ConsommablePublic])
async def list_consommables_available_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Liste les consommables disponibles (stock > 0) pour les utilisateurs.
    """
    user_org_id = current_user.get("organization_id")
    
    if not user_org_id:
        return []
    
    try:
        consommables = await list_consommables_available(str(user_org_id))
        return consommables
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.get("/alerts", response_model=List[ConsommablePublic])
async def get_alerts_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Récupère les consommables en alerte (stock <= limite_alerte).
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent voir les alertes.",
        )
    
    try:
        consommables = await get_consommables_low_stock(str(user_org_id))
        return consommables
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.get("/{consommable_id}", response_model=ConsommablePublic)
async def get_consommable_endpoint(
    consommable_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Récupère un consommable par son ID.
    """
    try:
        consommable = await get_consommable_by_id(consommable_id)
        if not consommable:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Consommable introuvable.",
            )
        
        # Vérifier les permissions
        user_org_id = current_user.get("organization_id")
        if consommable["organization_id"] != str(user_org_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'avez pas accès à ce consommable.",
            )
        
        return consommable
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.put("/{consommable_id}", response_model=ConsommablePublic)
async def update_consommable_endpoint(
    consommable_id: str,
    consommable_in: ConsommableUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Met à jour un consommable.
    - Admin : modification directe
    - Gestionnaire de stock : crée une demande de validation
    """
    user_role = current_user.get("role", "user")
    user_id = current_user.get("id")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "gestionnaire_stock"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs et les gestionnaires de stock peuvent modifier des consommables.",
        )
    
    try:
        consommable = await get_consommable_by_id(consommable_id)
        if not consommable:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Consommable introuvable.",
            )
        
        if consommable["organization_id"] != str(user_org_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez modifier que les consommables de votre organisation.",
            )
        
        update_data = {k: v for k, v in consommable_in.model_dump().items() if v is not None}
        
        # Si admin : modification directe
        if user_role == "admin":
            updated = await update_consommable(consommable_id, update_data)
            if not updated:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Erreur lors de la mise à jour.",
                )
            return updated
        
        # Si gestionnaire de stock : créer une demande de validation
        from app.models.stock.validation_consommable import create_validation_consommable_request
        
        request_data = {
            "action": "update",
            "consommable_id": consommable_id,
            "consommable_data": update_data,
            "motif": None,
        }
        
        validation_request = await create_validation_consommable_request(
            request_data, str(user_id), str(user_org_id)
        )
        
        # Retourner une réponse avec le statut 202 pour indiquer que la demande est en attente
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "message": "Demande de modification de consommable créée. Elle sera validée par l'agent DRH.",
                "validation_request": validation_request
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la mise à jour: {str(e)}",
        )


@router.put("/{consommable_id}/stock", response_model=ConsommablePublic)
async def update_stock_endpoint(
    consommable_id: str,
    stock_update: StockUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Crée une demande d'introduction de stock (nécessite validation DRH).
    Le stock ne sera mis à jour qu'après validation par le DRH.
    """
    from app.models.stock.introduction_stock import create_introduction_stock
    
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
        consommable = await get_consommable_by_id(consommable_id)
        if not consommable:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Consommable introuvable.",
            )
        
        if consommable["organization_id"] != str(user_org_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez modifier que le stock de votre organisation.",
            )
        
        # Créer une demande d'introduction de stock (en attente de validation DRH)
        introduction_data = {
            "consommable_id": consommable_id,
            "gestionnaire_id": str(user_id),
            "organization_id": str(user_org_id),
            "quantite": stock_update.quantite,
            "operation": stock_update.operation,
            "motif": f"Introduction de stock - {stock_update.operation}",
        }
        
        introduction = await create_introduction_stock(introduction_data)
        
        # Retourner le consommable (le stock n'est pas encore mis à jour)
        return consommable
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la création de la demande d'introduction: {str(e)}",
        )


@router.delete("/{consommable_id}")
async def delete_consommable_endpoint(
    consommable_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Supprime un consommable (admin ou gestionnaire de stock).
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "gestionnaire_stock"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs et les gestionnaires de stock peuvent supprimer des consommables.",
        )
    
    try:
        consommable = await get_consommable_by_id(consommable_id)
        if not consommable:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Consommable introuvable.",
            )
        
        if consommable["organization_id"] != str(user_org_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez supprimer que les consommables de votre organisation.",
            )
        
        success = await delete_consommable(consommable_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la suppression.",
            )
        
        return {"message": "Consommable supprimé avec succès."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la suppression: {str(e)}",
        )

