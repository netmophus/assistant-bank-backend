from fastapi import APIRouter, HTTPException, status, Depends

from app.schemas.organization import OrganizationCreate, OrganizationPublic, OrganizationUpdate
from app.models.organization import create_organization, list_organizations, update_organization
from app.core.deps import get_superadmin

router = APIRouter(
    prefix="/organizations",
    tags=["organizations"],
)


@router.post("", response_model=OrganizationPublic)
async def create_org(org_in: OrganizationCreate, current_user: dict = Depends(get_superadmin)):
    """
    Création d'une organisation (banque). Réservé au superadmin.
    """
    try:
        org = await create_organization(org_in)
        return org
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("", response_model=list[OrganizationPublic])
async def get_orgs(current_user: dict = Depends(get_superadmin)):
    """
    Liste des organisations. Réservé au superadmin.
    """
    orgs = await list_organizations()
    return orgs


@router.put("/{org_id}", response_model=OrganizationPublic)
async def update_org(org_id: str, org_update: OrganizationUpdate, current_user: dict = Depends(get_superadmin)):
    """
    Met à jour une organisation. Réservé au superadmin.
    """
    try:
        update_data = org_update.model_dump(exclude_unset=True)
        org = await update_organization(org_id, update_data)
        return org
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
