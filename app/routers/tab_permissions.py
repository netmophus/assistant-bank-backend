from fastapi import APIRouter, Depends, HTTPException
from typing import List

from app.core.deps import get_current_user, get_org_admin
from app.models.tab_permissions import (
    get_tab_permissions,
    update_tab_permissions,
    get_user_allowed_tabs,
    AVAILABLE_TABS,
)
from app.schemas.tab_permissions import (
    TabPermissionsConfigUpdate,
    UserTabPermissions,
)

router = APIRouter(prefix="/tab-permissions", tags=["tab-permissions"])


@router.get("/available-tabs")
async def get_available_tabs(current_user: dict = Depends(get_current_user)):
    """Retourne la liste de tous les onglets disponibles"""
    return {"tabs": AVAILABLE_TABS}


@router.get("/organization")
async def get_organization_tab_permissions(current_user: dict = Depends(get_org_admin)):
    """
    Récupère les permissions des onglets pour l'organisation de l'utilisateur.
    Réservé aux org_admin.
    """
    org_id = current_user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="Utilisateur non associé à une organisation")
    
    permissions = await get_tab_permissions(org_id)
    return permissions


@router.put("/organization/tab/{tab_id}")
async def update_organization_tab_permissions(
    tab_id: str,
    config: TabPermissionsConfigUpdate,
    current_user: dict = Depends(get_org_admin),
):
    """
    Met à jour les permissions d'un onglet spécifique.
    Réservé aux org_admin.
    """
    org_id = current_user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="Utilisateur non associé à une organisation")
    
    # Vérifier que l'onglet existe
    tab_ids = [tab["id"] for tab in AVAILABLE_TABS]
    if tab_id not in tab_ids:
        raise HTTPException(status_code=400, detail=f"Onglet '{tab_id}' introuvable")
    
    config_dict = {}
    if config.enabled is not None:
        config_dict["enabled"] = config.enabled
    if config.rules is not None:
        config_dict["rules"] = [rule.dict() for rule in config.rules]
    
    updated = await update_tab_permissions(org_id, tab_id, config_dict)
    return updated


@router.get("/user/allowed-tabs")
async def get_user_allowed_tabs_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Retourne la liste des onglets autorisés pour l'utilisateur connecté.
    MODE OPT-IN : Seuls les onglets explicitement activés sont retournés.
    Bootstrap : Les org admins ont toujours accès à "tab-permissions" pour configurer.
    """
    # Log immédiat pour confirmer que l'endpoint est appelé
    import logging
    logger = logging.getLogger(__name__)
    logger.info("=" * 80)
    logger.info("[get_user_allowed_tabs_endpoint] ⚡ ENDPOINT APPELÉ")
    logger.info("=" * 80)
    
    org_id = current_user.get("organization_id")
    user_role = current_user.get("role")
    
    if not org_id:
        # Super admin ou utilisateur sans organisation - retourner tous les onglets
        return UserTabPermissions(allowed_tabs=[tab["id"] for tab in AVAILABLE_TABS])
    
    department_id = current_user.get("department_id")
    service_id = current_user.get("service_id")
    role_departement = current_user.get("role_departement")
    user_id = current_user.get("id")
    
    # Log pour debug
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[get_user_allowed_tabs_endpoint] user_id={user_id}, org_id={org_id}, role={user_role} (type: {type(user_role)}), dept_id={department_id}, service_id={service_id}, role_dept={role_departement}")
    logger.info(f"[get_user_allowed_tabs_endpoint] user_role == 'admin': {user_role == 'admin'}")
    logger.info(f"[get_user_allowed_tabs_endpoint] user_role == 'user': {user_role == 'user'}")
    
    allowed_tabs = await get_user_allowed_tabs(
        org_id,
        department_id,
        service_id,
        role_departement,
        user_id,
        user_role,  # Passer user_role pour distinguer admin/user
    )
    
    logger.info(f"[get_user_allowed_tabs_endpoint] Résultat avant bootstrap: {len(allowed_tabs)} onglets autorisés: {allowed_tabs}")
    
    # Bootstrap pour les org admins : si aucune config n'existe, leur donner au minimum "tab-permissions"
    # pour qu'ils puissent configurer les permissions
    if user_role == "admin":
        if len(allowed_tabs) == 0:
            # Aucune config existe → bootstrap minimal pour permettre la configuration
            bootstrap_tabs = ["tab-permissions", "departments", "services", "users"]
            logger.info(f"[get_user_allowed_tabs_endpoint] Bootstrap admin: aucune config → ajout onglets bootstrap: {bootstrap_tabs}")
            allowed_tabs = bootstrap_tabs
        elif "tab-permissions" not in allowed_tabs:
            # Config existe mais "tab-permissions" n'est pas activé → l'ajouter quand même
            allowed_tabs.append("tab-permissions")
            logger.info(f"[get_user_allowed_tabs_endpoint] Bootstrap admin: ajout 'tab-permissions'")
    
    logger.info(f"[get_user_allowed_tabs_endpoint] Résultat final: {len(allowed_tabs)} onglets autorisés: {allowed_tabs}")
    
    return UserTabPermissions(allowed_tabs=allowed_tabs)

