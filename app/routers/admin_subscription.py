"""
Endpoints ADMIN pour traiter les demandes d'abonnement recues via le formulaire
public de www.miznas.co/tarifs. Reserves au superadmin.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import get_current_user
from app.models.subscription_request import (
    get_subscription_request_by_id,
    list_subscription_requests,
    update_subscription_request_status,
)
from app.schemas.subscription_request import (
    SubscriptionRequestPublic,
    UpdateSubscriptionRequestStatus,
)

router = APIRouter(
    prefix="/admin/subscription-requests",
    tags=["Admin - Subscription"],
)


def _require_superadmin(current_user: dict) -> None:
    if current_user.get("role") != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acces reserve aux super administrateurs.",
        )


@router.get("", response_model=list[SubscriptionRequestPublic])
async def list_requests(
    req_status: Optional[str] = Query(None, alias="status"),
    plan: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Liste les demandes, triees par date decroissante. Filtres status / plan."""
    _require_superadmin(current_user)
    return await list_subscription_requests(status=req_status, plan=plan)


@router.get("/{req_id}", response_model=SubscriptionRequestPublic)
async def get_request(
    req_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Detail d'une demande precise."""
    _require_superadmin(current_user)
    req = await get_subscription_request_by_id(req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Demande introuvable.")
    return req


@router.patch("/{req_id}/status", response_model=SubscriptionRequestPublic)
async def update_status(
    req_id: str,
    payload: UpdateSubscriptionRequestStatus,
    current_user: dict = Depends(get_current_user),
):
    """Change le statut + notes admin. Horodate automatiquement contacted_at / activated_at."""
    _require_superadmin(current_user)
    try:
        return await update_subscription_request_status(
            req_id, payload.status, payload.admin_notes
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
