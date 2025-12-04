from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.core.security import create_access_token
from app.models.department import get_department_by_id, get_service_by_id
from app.models.license import get_active_license_for_org  # 🔒 nouveau
from app.models.organization import (
    get_organization_by_id,  # Pour récupérer le nom de l'organisation
)
from app.models.user import (
    authenticate_user,
    count_users_by_org,
    create_user,
    create_user_for_org,
    list_users,
    list_users_by_org,
    update_user,
)
from app.schemas.user import LoginData, Token, UserCreate, UserPublic, UserUpdate

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post("/register", response_model=UserPublic)
async def register(user_in: UserCreate):
    try:
        user = await create_user(user_in)
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        # Capturer toutes les autres exceptions pour éviter les 500
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la création de l'utilisateur: {str(e)}",
        )


@router.post("/login", response_model=Token)
async def login(data: LoginData):
    """
    Connexion : vérifie email + mot de passe,
    puis vérifie qu'il existe une licence active pour la banque.
    Les super admins (rôle "superadmin") peuvent se connecter sans licence.
    """
    # 1) Vérifier les identifiants
    user = await authenticate_user(data.email, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect.",
        )

    # 2) Vérifier si c'est un super admin (rôle "superadmin")
    user_role = user.get("role", "user")
    is_super_admin = user_role == "superadmin"

    # 3) Si ce n'est pas un super admin, vérifier la licence active
    if not is_super_admin:
        org_id = str(user["organization_id"])
        license_doc = await get_active_license_for_org(org_id)
        if not license_doc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Aucune licence active pour cette banque. Veuillez contacter l'administrateur.",
            )
        org_id = str(user["organization_id"])
    else:
        # Pour les super admins, pas d'organization_id (None)
        org_id = None

    # 4) Tout est OK → création du token JWT
    token_data = {
        "sub": str(user["_id"]),
        "email": user["email"],
        "role": user_role,  # Ajouter le rôle dans le JWT
    }
    # Ajouter org seulement si ce n'est pas un super admin
    if org_id:
        token_data["org"] = org_id

    token = create_access_token(token_data)
    return Token(access_token=token)


@router.get("/me", response_model=UserPublic)
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    Retourne les infos de l'utilisateur connecté (à partir du JWT).
    """
    organization_id = (
        str(current_user["organization_id"])
        if current_user.get("organization_id")
        else None
    )
    organization_name = None
    department_id = (
        str(current_user["department_id"])
        if current_user.get("department_id")
        else None
    )
    department_name = None
    service_id = (
        str(current_user["service_id"]) if current_user.get("service_id") else None
    )
    service_name = None

    # Récupérer le nom de l'organisation si elle existe
    if organization_id:
        org = await get_organization_by_id(organization_id)
        if org:
            organization_name = org.get("name")

    # Récupérer le nom du département si il existe
    if department_id:
        dept = await get_department_by_id(department_id)
        if dept:
            department_name = dept.get("name")

    # Récupérer le nom du service si il existe
    if service_id:
        service = await get_service_by_id(service_id)
        if service:
            service_name = service.get("name")

    return UserPublic(
        id=current_user["id"],
        email=current_user["email"],
        full_name=current_user["full_name"],
        organization_id=organization_id,
        organization_name=organization_name,
        department_id=department_id,
        department_name=department_name,
        service_id=service_id,
        service_name=service_name,
        role=current_user.get("role", "user"),
    )


@router.get("/users", response_model=list[UserPublic])
async def get_users(current_user: dict = Depends(get_current_user)):
    """
    Liste tous les utilisateurs (réservé aux super admins).
    """
    user_role = current_user.get("role", "user")
    if user_role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux super administrateurs.",
        )

    users = await list_users()
    return users


@router.put("/users/{user_id}", response_model=UserPublic)
async def update_user_endpoint(
    user_id: str,
    user_update: UserUpdate,
    current_user: dict = Depends(get_current_user),
):
    """
    Met à jour un utilisateur (réservé aux super admins, sauf le super admin lui-même).
    """
    user_role = current_user.get("role", "user")
    if user_role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux super administrateurs.",
        )

    try:
        # Convertir le modèle Pydantic en dict, en excluant les valeurs None
        update_data = user_update.model_dump(exclude_unset=True)
        user = await update_user(user_id, update_data)
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/users/org", response_model=UserPublic)
async def create_user_for_organization(
    user_in: UserCreate, current_user: dict = Depends(get_current_user)
):
    """
    Crée un utilisateur pour l'organisation de l'admin connecté.
    Vérifie les limites de la licence.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est un admin d'organisation (pas super admin)
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent créer des utilisateurs.",
        )

    # Vérifier que l'utilisateur est créé pour la même organisation
    if str(user_org_id) != user_in.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez créer des utilisateurs que pour votre propre organisation.",
        )

    try:
        user = await create_user_for_org(user_in, str(user_org_id))
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/users/org", response_model=list[UserPublic])
async def get_users_for_organization(current_user: dict = Depends(get_current_user)):
    """
    Liste les utilisateurs de l'organisation de l'admin connecté.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est un admin d'organisation (pas super admin)
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent voir les utilisateurs.",
        )

    users = await list_users_by_org(str(user_org_id))
    return users


@router.get("/users/org/stats")
async def get_org_user_stats(current_user: dict = Depends(get_current_user)):
    """
    Retourne les statistiques d'utilisation de la licence pour l'organisation.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est un admin d'organisation (pas super admin)
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs d'organisation.",
        )

    org_id = str(user_org_id)

    # Récupérer la licence active
    license_doc = await get_active_license_for_org(org_id)
    if not license_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucune licence active trouvée.",
        )

    # Compter les utilisateurs
    current_count = await count_users_by_org(org_id)
    max_users = license_doc["max_users"]

    return {
        "current_users": current_count,
        "max_users": max_users,
        "remaining_slots": max_users - current_count,
        "license_plan": license_doc["plan"],
        "license_status": license_doc["status"],
    }
