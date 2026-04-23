"""
Endpoints ADMIN pour traiter les demandes de demonstration B2B reservees au
superadmin.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import get_current_user
from app.models.institution_demo_request import (
    get_institution_demo_request_by_id,
    list_institution_demo_requests,
    update_institution_demo_status,
)
from app.schemas.institution_demo_request import (
    InstitutionDemoPublic,
    UpdateInstitutionDemoStatus,
)

router = APIRouter(
    prefix="/admin/institution-demos",
    tags=["Admin - Institution Demo"],
)


def _require_superadmin(current_user: dict) -> None:
    if current_user.get("role") != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acces reserve aux super administrateurs.",
        )


@router.get("", response_model=list[InstitutionDemoPublic])
async def list_demos(
    req_status: Optional[str] = Query(None, alias="status"),
    institution_type: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Liste les demandes triees par date decroissante. Filtres status / type."""
    _require_superadmin(current_user)
    return await list_institution_demo_requests(
        status=req_status, institution_type=institution_type
    )


@router.get("/{req_id}", response_model=InstitutionDemoPublic)
async def get_demo(
    req_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Detail d'une demande precise."""
    _require_superadmin(current_user)
    req = await get_institution_demo_request_by_id(req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Demande introuvable.")
    return req


@router.patch("/{req_id}/status", response_model=InstitutionDemoPublic)
async def update_status(
    req_id: str,
    payload: UpdateInstitutionDemoStatus,
    current_user: dict = Depends(get_current_user),
):
    """Change le statut + notes admin. Horodate les transitions."""
    _require_superadmin(current_user)
    try:
        return await update_institution_demo_status(
            req_id, payload.status, payload.admin_notes
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
