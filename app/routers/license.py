from fastapi import APIRouter, HTTPException, status, Depends

from app.schemas.license import LicenseCreate, LicensePublic, LicenseUpdate
from app.models.license import create_license, list_licenses_by_org, update_license, org_has_active_license
from app.core.db import get_database
from app.core.deps import get_current_user

router = APIRouter(
    prefix="/licenses",
    tags=["licenses"],
)


@router.post("", response_model=LicensePublic)
async def create_lic(lic_in: LicenseCreate):
    """
    Crée une licence pour une organisation (banque).
    Plus tard : réservé au super_admin.
    """
    try:
        lic = await create_license(lic_in)
        return lic
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/by-org/{org_id}", response_model=list[LicensePublic])
async def get_licenses_for_org(org_id: str):
    """
    Liste des licences d'une organisation.
    """
    items = await list_licenses_by_org(org_id)
    return items


@router.get("", response_model=list[LicensePublic])
async def get_all_licenses():
    """
    Liste toutes les licences (pour super admin).
    """
    from app.models.license import list_licenses_by_org
    
    # Récupérer toutes les licences en listant toutes les organisations
    # Pour simplifier, on fait une requête directe
    from app.models.license import LICENSES_COLLECTION, _license_doc_to_public
    
    db = get_database()
    cursor = db[LICENSES_COLLECTION].find({})
    licenses = []
    async for doc in cursor:
        licenses.append(_license_doc_to_public(doc))
    return licenses


@router.put("/{license_id}", response_model=LicensePublic)
async def update_lic(license_id: str, lic_update: LicenseUpdate):
    """
    Met à jour une licence.
    """
    try:
        # Convertir le modèle Pydantic en dict, en excluant les valeurs None
        update_data = lic_update.model_dump(exclude_unset=True)
        lic = await update_license(license_id, update_data)
        return lic
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/check-active")
async def check_active_license(current_user: dict = Depends(get_current_user)):
    """
    Vérifie si l'organisation de l'utilisateur connecté a une licence active.
    Utilisé par le frontend pour conditionner l'affichage des fonctionnalités premium.
    
    Returns:
        {
            "has_active_license": bool,
            "organization_id": str | None
        }
    """
    organization_id = current_user.get("organization_id")
    
    if not organization_id:
        # Superadmin ou utilisateur sans organisation
        return {
            "has_active_license": True,  # Superadmin a toujours accès
            "organization_id": None
        }
    
    has_license = await org_has_active_license(organization_id)
    
    return {
        "has_active_license": has_license,
        "organization_id": organization_id
    }
