from fastapi import APIRouter, HTTPException, status, Depends
from typing import List

from app.schemas.stock.consommable import ConsommableCreate, ConsommablePublic, ConsommableUpdate, StockUpdate
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


@router.post("", response_model=ConsommablePublic)
async def create_consommable_endpoint(
    consommable_in: ConsommableCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Crée un consommable pour l'organisation de l'admin connecté.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent créer des consommables.",
        )
    
    try:
        consommable_data = consommable_in.model_dump()
        consommable = await create_consommable(consommable_data, str(user_org_id))
        return consommable
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
    Liste toutes les consommables de l'organisation (admin uniquement).
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent voir toutes les consommables.",
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
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent modifier des consommables.",
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
        updated = await update_consommable(consommable_id, update_data)
        
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la mise à jour.",
            )
        
        return updated
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
    Met à jour le stock d'un consommable.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent modifier le stock.",
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
        
        updated = await update_stock(consommable_id, stock_update.quantite, stock_update.operation)
        
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la mise à jour du stock.",
            )
        
        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la mise à jour: {str(e)}",
        )


@router.delete("/{consommable_id}")
async def delete_consommable_endpoint(
    consommable_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Supprime un consommable.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent supprimer des consommables.",
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

