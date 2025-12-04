# from datetime import datetime
# from typing import Optional

# from bson import ObjectId

# from app.core.db import get_database
# from app.core.security import hash_password, verify_password
# from app.schemas.user import UserCreate


# USERS_COLLECTION = "users"


# def _user_doc_to_public(doc) -> dict:
#     """
#     Convertit un document Mongo en dict public.
#     """
#     return {
#         "id": str(doc["_id"]),
#         "email": doc["email"],
#         "full_name": doc["full_name"],
#     }


# async def get_user_by_email(email: str) -> Optional[dict]:
#     db = get_database()
#     user = await db[USERS_COLLECTION].find_one({"email": email})
#     return user


# async def get_user_by_id(user_id: str) -> Optional[dict]:
#     db = get_database()
#     try:
#         oid = ObjectId(user_id)
#     except Exception:
#         return None
#     user = await db[USERS_COLLECTION].find_one({"_id": oid})
#     return user


# async def create_user(user_in: UserCreate) -> dict:
#     """
#     Crée un utilisateur dans MongoDB.
#     """
#     db = get_database()
#     existing = await get_user_by_email(user_in.email)
#     if existing:
#         raise ValueError("Un utilisateur avec cet email existe déjà.")

#     doc = {
#         "email": user_in.email,
#         "full_name": user_in.full_name,
#         "password_hash": hash_password(user_in.password),
#         "is_active": True,
#         "created_at": datetime.utcnow(),
#     }

#     result = await db[USERS_COLLECTION].insert_one(doc)
#     doc["_id"] = result.inserted_id
#     return _user_doc_to_public(doc)


# async def authenticate_user(email: str, password: str) -> Optional[dict]:
#     """
#     Vérifie email + mot de passe. Retourne le document user si OK, sinon None.
#     """
#     user = await get_user_by_email(email)
#     if not user:
#         return None
#     if not verify_password(password, user["password_hash"]):
#         return None
#     return user





from datetime import datetime
from typing import Optional, List

from bson import ObjectId

from app.core.db import get_database
from app.core.security import hash_password, verify_password
from app.schemas.user import UserCreate
from app.models.organization import get_organization_by_id
from app.models.department import get_department_by_id, get_service_by_id

USERS_COLLECTION = "users"


def _user_doc_to_public(doc) -> dict:
    result = {
        "id": str(doc["_id"]),
        "email": doc["email"],
        "full_name": doc["full_name"],
        "organization_id": str(doc["organization_id"]) if doc.get("organization_id") else None,
        "department_id": str(doc["department_id"]) if doc.get("department_id") else None,
        "service_id": str(doc["service_id"]) if doc.get("service_id") else None,
        "role": doc.get("role", "user"),
        "department_name": doc.get("department_name"),  # Sera rempli si fourni
        "service_name": doc.get("service_name"),  # Sera rempli si fourni
    }
    return result


async def get_user_by_email(email: str) -> Optional[dict]:
    db = get_database()
    user = await db[USERS_COLLECTION].find_one({"email": email})
    return user


async def get_user_by_id(user_id: str) -> Optional[dict]:
    db = get_database()
    try:
        oid = ObjectId(user_id)
    except Exception:
        return None
    user = await db[USERS_COLLECTION].find_one({"_id": oid})
    return user


async def create_user(user_in: UserCreate) -> dict:
    """
    Crée un utilisateur dans MongoDB, rattaché à une organisation.
    """
    db = get_database()
    existing = await get_user_by_email(user_in.email)
    if existing:
        raise ValueError("Un utilisateur avec cet email existe déjà.")

    # Vérifier que l'organisation existe
    org = await get_organization_by_id(user_in.organization_id)
    if not org:
        raise ValueError("Organisation introuvable pour cet organization_id.")

    try:
        org_oid = ObjectId(user_in.organization_id)
    except Exception:
        raise ValueError("organization_id invalide.")

    # Déterminer le rôle : par défaut "user"
    role = user_in.role if hasattr(user_in, "role") and user_in.role else "user"
    
    # Vérifier le département si fourni
    dept_oid = None
    if hasattr(user_in, "department_id") and user_in.department_id:
        dept = await get_department_by_id(user_in.department_id)
        if not dept:
            raise ValueError("Département introuvable.")
        if str(dept["organization_id"]) != user_in.organization_id:
            raise ValueError("Le département n'appartient pas à cette organisation.")
        dept_oid = ObjectId(user_in.department_id)
    
    # Vérifier le service si fourni
    # Note: Un utilisateur peut être dans un département sans service (agents directs du département)
    service_oid = None
    if hasattr(user_in, "service_id") and user_in.service_id:
        if not dept_oid:
            raise ValueError("Un service doit être assigné à un département. Veuillez d'abord sélectionner un département.")
        service = await get_service_by_id(user_in.service_id)
        if not service:
            raise ValueError("Service introuvable.")
        if str(service["department_id"]) != user_in.department_id:
            raise ValueError("Le service n'appartient pas à ce département.")
        service_oid = ObjectId(user_in.service_id)
    
    doc = {
        "email": user_in.email,
        "full_name": user_in.full_name,
        "organization_id": org_oid,
        "department_id": dept_oid,
        "service_id": service_oid,
        "password_hash": hash_password(user_in.password),
        "role": role,
        "is_active": True,
        "created_at": datetime.utcnow(),
    }

    result = await db[USERS_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _user_doc_to_public(doc)


async def authenticate_user(email: str, password: str) -> Optional[dict]:
    """
    Vérifie email + mot de passe. Retourne le document user si OK, sinon None.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    user = await get_user_by_email(email)
    if not user:
        logger.debug(f"authenticate_user: User not found for email: {email}")
        return None
    
    # Check if password_hash exists
    if "password_hash" not in user or not user["password_hash"]:
        logger.warning(f"authenticate_user: No password_hash found for user: {email}")
        return None
    
    if not verify_password(password, user["password_hash"]):
        logger.debug(f"authenticate_user: Password verification failed for user: {email}")
        return None
    
    logger.debug(f"authenticate_user: Authentication successful for user: {email}")
    return user


async def list_users() -> List[dict]:
    """
    Liste tous les utilisateurs (pour super admin) avec les noms des départements et services.
    """
    db = get_database()
    cursor = db[USERS_COLLECTION].find({})
    users = []
    async for doc in cursor:
        user_dict = _user_doc_to_public(doc)
        
        # Ajouter le nom du département si présent
        if doc.get("department_id"):
            dept = await get_department_by_id(str(doc["department_id"]))
            if dept:
                user_dict["department_name"] = dept.get("name")
        
        # Ajouter le nom du service si présent
        if doc.get("service_id"):
            service = await get_service_by_id(str(doc["service_id"]))
            if service:
                user_dict["service_name"] = service.get("name")
        
        users.append(user_dict)
    return users


async def count_users_by_org(org_id: str) -> int:
    """
    Compte le nombre d'utilisateurs actifs d'une organisation.
    """
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return 0
    
    count = await db[USERS_COLLECTION].count_documents({
        "organization_id": org_oid,
        "is_active": True
    })
    return count


async def list_users_by_org(org_id: str) -> List[dict]:
    """
    Liste les utilisateurs d'une organisation avec les noms des départements et services.
    """
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return []
    
    cursor = db[USERS_COLLECTION].find({"organization_id": org_oid})
    users = []
    async for doc in cursor:
        user_dict = _user_doc_to_public(doc)
        
        # Ajouter le nom du département si présent
        if doc.get("department_id"):
            dept = await get_department_by_id(str(doc["department_id"]))
            if dept:
                user_dict["department_name"] = dept.get("name")
        
        # Ajouter le nom du service si présent
        if doc.get("service_id"):
            service = await get_service_by_id(str(doc["service_id"]))
            if service:
                user_dict["service_name"] = service.get("name")
        
        users.append(user_dict)
    return users


async def create_user_for_org(user_in: UserCreate, org_id: str) -> dict:
    """
    Crée un utilisateur pour une organisation avec vérification de la licence.
    Les utilisateurs créés par l'admin d'organisation sont toujours des "user" (pas admin).
    """
    from app.models.license import get_active_license_for_org
    
    # Vérifier que l'organisation existe
    org = await get_organization_by_id(org_id)
    if not org:
        raise ValueError("Organisation introuvable.")
    
    # Vérifier que l'utilisateur est créé pour la bonne organisation
    if user_in.organization_id != org_id:
        raise ValueError("L'utilisateur doit être créé pour votre organisation.")
    
    # Vérifier la licence active
    license_doc = await get_active_license_for_org(org_id)
    if not license_doc:
        raise ValueError("Aucune licence active pour cette organisation.")
    
    # Compter les utilisateurs actuels
    current_count = await count_users_by_org(org_id)
    
    # Vérifier la limite
    if current_count >= license_doc["max_users"]:
        raise ValueError(
            f"Limite d'utilisateurs atteinte ({license_doc['max_users']} utilisateurs maximum). "
            f"Vous avez actuellement {current_count} utilisateurs actifs."
        )
    
    # Forcer le rôle à "user" pour les utilisateurs créés par l'admin d'organisation
    # (seuls les super admins peuvent créer des admins d'organisation)
    user_in.role = "user"
    
    # Créer l'utilisateur
    return await create_user(user_in)


async def update_user(user_id: str, update_data: dict) -> dict:
    """
    Met à jour un utilisateur (sauf le super admin).
    """
    db = get_database()
    try:
        user_oid = ObjectId(user_id)
    except Exception:
        raise ValueError("user_id invalide.")
    
    # Vérifier que l'utilisateur existe
    existing = await db[USERS_COLLECTION].find_one({"_id": user_oid})
    if not existing:
        raise ValueError("Utilisateur introuvable.")
    
    # Ne pas permettre la modification du super admin
    if existing.get("role") == "superadmin":
        raise ValueError("Le super administrateur ne peut pas être modifié.")
    
    # Préparer les données de mise à jour
    update_doc = {}
    
    if "email" in update_data:
        # Vérifier que l'email n'est pas déjà utilisé par un autre utilisateur
        existing_email = await get_user_by_email(update_data["email"])
        if existing_email and str(existing_email["_id"]) != user_id:
            raise ValueError("Un utilisateur avec cet email existe déjà.")
        update_doc["email"] = update_data["email"]
    
    if "full_name" in update_data:
        update_doc["full_name"] = update_data["full_name"]
    
    if "password" in update_data:
        update_doc["password_hash"] = hash_password(update_data["password"])
    
    if "organization_id" in update_data:
        if update_data["organization_id"]:
            # Vérifier que l'organisation existe
            org = await get_organization_by_id(update_data["organization_id"])
            if not org:
                raise ValueError("Organisation introuvable.")
            update_doc["organization_id"] = ObjectId(update_data["organization_id"])
        else:
            update_doc["organization_id"] = None
    
    if "role" in update_data:
        # Ne pas permettre de créer un super admin via update
        if update_data["role"] == "superadmin":
            raise ValueError("Impossible de créer un super admin via la modification.")
        update_doc["role"] = update_data["role"]
    
    if "is_active" in update_data:
        update_doc["is_active"] = update_data["is_active"]
    
    update_doc["updated_at"] = datetime.utcnow()
    
    await db[USERS_COLLECTION].update_one(
        {"_id": user_oid},
        {"$set": update_doc}
    )
    
    # Récupérer l'utilisateur mis à jour
    updated = await db[USERS_COLLECTION].find_one({"_id": user_oid})
    return _user_doc_to_public(updated)
