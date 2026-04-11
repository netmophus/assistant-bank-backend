import os
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional

from app.core.deps import get_current_user
from app.core.db import get_database
from app.core.security import create_access_token, hash_password
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
    list_users_by_org_with_filters,
    update_user,
)
from app.schemas.user import LoginData, Token, UserCreate, UserPublic, UserUpdate, StockUserCreate

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post("/register", response_model=UserPublic)
async def register(user_in: UserCreate):
    # Si pas d'organisation fournie → compte démo, on assigne à MIZNAS
    if not user_in.organization_id:
        from app.core.db import get_database
        db = get_database()
        miznas_org = await db["organizations"].find_one({"code": "MIZNAS_TEST"})
        if not miznas_org:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Organisation démo indisponible. Contactez l'administrateur.",
            )
        user_in = user_in.model_copy(update={"organization_id": str(miznas_org["_id"])})

    try:
        user = await create_user(user_in)
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la creation du compte: {str(e)}",
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
        "role_departement": user.get(
            "role_departement", "agent"
        ),  # Rôle dans le département
        "department_id": str(user["department_id"])
        if user.get("department_id")
        else None,
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
        role=current_user.get("role"),
        role_departement=current_user.get("role_departement"),
        is_active=current_user.get("is_active", True),
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
    import logging
    logger = logging.getLogger(__name__)
    
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    logger.info(f"[create_user_for_organization] Début création utilisateur")
    logger.info(f"[create_user_for_organization] current_user role={user_role}, org_id={user_org_id}")
    logger.info(f"[create_user_for_organization] user_in={user_in.dict()}")

    # Vérifier que l'utilisateur est un admin d'organisation (pas super admin)
    if user_role != "admin" or not user_org_id:
        logger.warning(f"[create_user_for_organization] Accès refusé: role={user_role}, org_id={user_org_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent créer des utilisateurs.",
        )

    # Vérifier que l'utilisateur est créé pour la même organisation
    if str(user_org_id) != user_in.organization_id:
        logger.warning(f"[create_user_for_organization] Organisation différente: user_org={user_org_id}, user_in.org={user_in.organization_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez créer des utilisateurs que pour votre propre organisation.",
        )

    try:
        logger.info(f"[create_user_for_organization] Appel create_user_for_org")
        user = await create_user_for_org(user_in, str(user_org_id))
        logger.info(f"[create_user_for_organization] Utilisateur créé avec succès: {user.get('id')}")
        return user
    except ValueError as e:
        logger.error(f"[create_user_for_organization] Erreur ValueError: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"[create_user_for_organization] Erreur inattendue: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la création de l'utilisateur: {str(e)}",
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


@router.get("/users/org/filtered", response_model=list[UserPublic])
async def get_users_with_filters(
    department_id: Optional[str] = None,
    service_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Liste les utilisateurs de l'organisation avec filtres optionnels par département et service.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est un admin d'organisation (pas super admin)
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent voir les utilisateurs.",
        )

    users = await list_users_by_org_with_filters(str(user_org_id), department_id, service_id)
    return users


@router.get("/users/org/simple")
async def get_users_for_organization_simple(current_user: dict = Depends(get_current_user)):
    """
    Liste simplifiée des utilisateurs de l'organisation pour les permissions.
    Retourne uniquement les champs nécessaires pour le select dans TabPermissionsTab.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est un admin d'organisation (pas super admin)
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent voir les utilisateurs.",
        )

    try:
        users = await list_users_by_org(str(user_org_id))
        
        # Retourner uniquement les champs nécessaires
        # list_users_by_org retourne une List[dict], pas des objets UserPublic
        return [
            {
                "id": user.get("id", ""),
                "full_name": user.get("full_name", ""),
                "email": user.get("email", ""),
                "department_id": user.get("department_id"),
                "service_id": user.get("service_id"),
                "role_departement": user.get("role_departement"),
            }
            for user in users
        ]
    except Exception as e:
        import traceback
        error_detail = f"Erreur lors de la récupération des utilisateurs: {str(e)}\n{traceback.format_exc()}"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail,
        )


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


@router.post("/users/org/stock", response_model=UserPublic)
async def create_stock_user(
    user_in: StockUserCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    Crée un gestionnaire de stock ou un agent stock DRH pour l'organisation de l'admin connecté.
    Rôles acceptés : 'gestionnaire_stock' ou 'agent_stock_drh'
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est un admin d'organisation
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent créer des gestionnaires de stock.",
        )

    # Vérifier que le rôle est valide
    valid_roles = ["gestionnaire_stock", "agent_stock_drh"]
    if user_in.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rôle invalide. Rôles acceptés : {', '.join(valid_roles)}",
        )

    try:
        # Créer un UserCreate à partir de StockUserCreate
        user_create_data = UserCreate(
            email=user_in.email,
            full_name=user_in.full_name,
            password=user_in.password,
            organization_id=str(user_org_id),
            department_id=user_in.department_id,
            role=user_in.role,
            role_departement=None,  # Pas de rôle département pour les gestionnaires de stock
        )

        user = await create_user_for_org(user_create_data, str(user_org_id))
        return user
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


@router.get("/users/org/stock", response_model=list[UserPublic])
async def get_stock_users(current_user: dict = Depends(get_current_user)):
    """
    Liste les gestionnaires de stock et agents stock DRH de l'organisation de l'admin connecté.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est un admin d'organisation
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent voir les gestionnaires de stock.",
        )

    try:
        # Récupérer tous les utilisateurs de l'organisation
        all_users = await list_users_by_org(str(user_org_id))
        
        # Filtrer pour ne garder que les gestionnaires de stock et agents DRH
        stock_users = [
            user for user in all_users
            if user.get("role") in ["gestionnaire_stock", "agent_stock_drh"]
        ]
        
        return stock_users
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.put("/users/org/{user_id}", response_model=UserPublic)
async def update_user_for_organization(
    user_id: str,
    user_update: UserUpdate,
    current_user: dict = Depends(get_current_user),
):
    """
    Met à jour un utilisateur de l'organisation de l'admin connecté.
    Permet de modifier les informations et de désactiver/réactiver l'utilisateur.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est un admin d'organisation
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent modifier des utilisateurs.",
        )

    try:
        # Vérifier que l'utilisateur à modifier appartient à la même organisation
        from app.models.user import get_user_by_id
        target_user = await get_user_by_id(user_id)
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur introuvable.",
            )
        
        target_org_id = target_user.get("organization_id")
        if not target_org_id or str(target_org_id) != str(user_org_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez modifier que les utilisateurs de votre organisation.",
            )

        # Ne pas permettre de modifier le rôle en superadmin ou admin via cet endpoint
        update_data = user_update.model_dump(exclude_unset=True)
        if "role" in update_data and update_data["role"] in ["superadmin", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez pas modifier le rôle en superadmin ou admin.",
            )

        # Ne pas permettre de changer l'organization_id
        if "organization_id" in update_data:
            del update_data["organization_id"]

        # Mettre à jour l'utilisateur
        updated_user = await update_user(user_id, update_data)
        return updated_user
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
            detail=f"Erreur lors de la mise à jour: {str(e)}",
        )


@router.post("/forgot-password")
async def forgot_password(data: dict):
    """Envoie un email de réinitialisation du mot de passe via Gmail SMTP."""
    from app.models.user import get_user_by_email
    from app.services.email_service import send_email, reset_password_html

    email = data.get("email", "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="L'email est requis")

    # Toujours répondre la même chose (sécurité : ne pas révéler si l'email existe)
    ok_response = {"message": "Si l'email existe, un lien de réinitialisation a été envoyé"}

    user = await get_user_by_email(email)
    if not user:
        return ok_response

    # Générer un token sécurisé
    token = secrets.token_urlsafe(48)
    expires_at = datetime.utcnow() + timedelta(hours=1)

    db = get_database()
    # Invalider les anciens tokens pour cet email
    await db["password_reset_tokens"].delete_many({"email": email})
    await db["password_reset_tokens"].insert_one({
        "email": email,
        "token": token,
        "expires_at": expires_at,
        "used": False,
    })

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    reset_link = f"{frontend_url}/reset-password?token={token}"

    user_name = user.get("full_name", "")
    html = reset_password_html(reset_link, user_name)

    try:
        await send_email(email, "Réinitialisation de votre mot de passe — Miznas Pilot", html)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur envoi email : {str(e)}")

    return ok_response


@router.post("/reset-password")
async def reset_password(data: dict):
    """Valide le token et met à jour le mot de passe."""
    token    = data.get("token", "").strip()
    password = data.get("password", "").strip()

    if not token or not password:
        raise HTTPException(status_code=400, detail="Token et mot de passe requis")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 8 caractères")

    db = get_database()
    record = await db["password_reset_tokens"].find_one({"token": token, "used": False})

    if not record:
        raise HTTPException(status_code=400, detail="Lien invalide ou déjà utilisé")
    if record["expires_at"] < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Lien expiré. Veuillez refaire une demande.")

    # Mettre à jour le mot de passe
    new_hash = hash_password(password)
    await db["users"].update_one(
        {"email": record["email"]},
        {"$set": {"password_hash": new_hash}}
    )

    # Invalider le token
    await db["password_reset_tokens"].update_one(
        {"token": token},
        {"$set": {"used": True}}
    )

    return {"message": "Mot de passe mis à jour avec succès"}
