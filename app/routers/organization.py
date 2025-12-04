from fastapi import APIRouter, HTTPException, status

from app.schemas.organization import OrganizationCreate, OrganizationPublic, OrganizationUpdate
from app.models.organization import create_organization, list_organizations, update_organization

router = APIRouter(
    prefix="/organizations",
    tags=["organizations"],
)


@router.post("", response_model=OrganizationPublic)
async def create_org(org_in: OrganizationCreate):
    """
    Création d'une organisation (banque).
    Plus tard : réservé au super_admin.
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
async def get_orgs():
    """
    Liste des organisations (temporaire, pour tests).
    """
    orgs = await list_organizations()
    return orgs


@router.put("/{org_id}", response_model=OrganizationPublic)
async def update_org(org_id: str, org_update: OrganizationUpdate):
    """
    Met à jour une organisation.
    """
    try:
        # Convertir le modèle Pydantic en dict, en excluant les valeurs None
        update_data = org_update.model_dump(exclude_unset=True)
        org = await update_organization(org_id, update_data)
        return org
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
