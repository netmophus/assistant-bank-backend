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
async def create_lic(lic_in: LicenseCreate, current_user: dict = Depends(get_current_user)):
    """
    Crée une licence pour une organisation. Réservé au superadmin.
    """
    if current_user.get("role") != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès réservé au superadmin.")
    try:
        lic = await create_license(lic_in)
        return lic
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/by-org/{org_id}", response_model=list[LicensePublic])
async def get_licenses_for_org(org_id: str, current_user: dict = Depends(get_current_user)):
    """
    Liste des licences d'une organisation. Superadmin ou admin de la même org.
    """
    role = current_user.get("role")
    if role != "superadmin" and current_user.get("organization_id") != org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès non autorisé.")
    items = await list_licenses_by_org(org_id)
    return items


@router.get("", response_model=list[LicensePublic])
async def get_all_licenses(current_user: dict = Depends(get_current_user)):
    """
    Liste toutes les licences. Réservé au superadmin.
    """
    if current_user.get("role") != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès réservé au superadmin.")
    from app.models.license import LICENSES_COLLECTION, _license_doc_to_public
    db = get_database()
    cursor = db[LICENSES_COLLECTION].find({})
    licenses = []
    async for doc in cursor:
        licenses.append(_license_doc_to_public(doc))
    return licenses


@router.put("/{license_id}", response_model=LicensePublic)
async def update_lic(license_id: str, lic_update: LicenseUpdate, current_user: dict = Depends(get_current_user)):
    """
    Met à jour une licence. Réservé au superadmin.
    """
    if current_user.get("role") != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès réservé au superadmin.")
    try:
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
