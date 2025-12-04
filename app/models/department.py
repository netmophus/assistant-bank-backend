from datetime import datetime
from typing import Optional, List
from bson import ObjectId

from app.core.db import get_database
from app.models.organization import get_organization_by_id
from app.schemas.department import DepartmentCreate, ServiceCreate

DEPARTMENTS_COLLECTION = "departments"
SERVICES_COLLECTION = "services"


def _department_doc_to_public(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc["name"],
        "code": doc["code"],
        "description": doc.get("description"),
        "organization_id": str(doc["organization_id"]),
        "status": doc.get("status", "active"),
    }


def _service_doc_to_public(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc["name"],
        "code": doc["code"],
        "description": doc.get("description"),
        "department_id": str(doc["department_id"]),
        "status": doc.get("status", "active"),
    }


async def get_department_by_id(dept_id: str) -> Optional[dict]:
    """Récupère un département par son ID."""
    db = get_database()
    try:
        dept_oid = ObjectId(dept_id)
    except Exception:
        return None
    dept = await db[DEPARTMENTS_COLLECTION].find_one({"_id": dept_oid})
    return dept


async def get_service_by_id(service_id: str) -> Optional[dict]:
    """Récupère un service par son ID."""
    db = get_database()
    try:
        service_oid = ObjectId(service_id)
    except Exception:
        return None
    service = await db[SERVICES_COLLECTION].find_one({"_id": service_oid})
    return service


async def create_department(dept_in: DepartmentCreate, org_id: str) -> dict:
    """Crée un département pour une organisation."""
    db = get_database()
    
    # Vérifier que l'organisation existe
    org = await get_organization_by_id(org_id)
    if not org:
        raise ValueError("Organisation introuvable.")
    
    # Vérifier que le code n'existe pas déjà dans cette organisation
    existing = await db[DEPARTMENTS_COLLECTION].find_one({
        "organization_id": ObjectId(org_id),
        "code": dept_in.code
    })
    if existing:
        raise ValueError(f"Un département avec le code '{dept_in.code}' existe déjà dans cette organisation.")
    
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        raise ValueError("organization_id invalide.")
    
    doc = {
        "name": dept_in.name,
        "code": dept_in.code,
        "description": dept_in.description,
        "organization_id": org_oid,
        "status": "active",
        "created_at": datetime.utcnow(),
    }
    
    result = await db[DEPARTMENTS_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _department_doc_to_public(doc)


async def list_departments_by_org(org_id: str) -> List[dict]:
    """Liste tous les départements d'une organisation."""
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return []
    
    cursor = db[DEPARTMENTS_COLLECTION].find({"organization_id": org_oid})
    departments = []
    async for doc in cursor:
        dept = _department_doc_to_public(doc)
        # Compter les services et utilisateurs
        services_count = await db[SERVICES_COLLECTION].count_documents({"department_id": doc["_id"]})
        users_count = await db["users"].count_documents({"department_id": doc["_id"], "is_active": True})
        dept["services_count"] = services_count
        dept["users_count"] = users_count
        departments.append(dept)
    return departments


async def update_department(dept_id: str, update_data: dict, org_id: str) -> dict:
    """Met à jour un département."""
    db = get_database()
    try:
        dept_oid = ObjectId(dept_id)
    except Exception:
        raise ValueError("department_id invalide.")
    
    # Vérifier que le département existe et appartient à l'organisation
    existing = await db[DEPARTMENTS_COLLECTION].find_one({
        "_id": dept_oid,
        "organization_id": ObjectId(org_id)
    })
    if not existing:
        raise ValueError("Département introuvable ou n'appartient pas à votre organisation.")
    
    # Si le code change, vérifier qu'il n'existe pas déjà
    if "code" in update_data and update_data["code"] != existing.get("code"):
        existing_code = await db[DEPARTMENTS_COLLECTION].find_one({
            "organization_id": ObjectId(org_id),
            "code": update_data["code"],
            "_id": {"$ne": dept_oid}
        })
        if existing_code:
            raise ValueError(f"Un département avec le code '{update_data['code']}' existe déjà.")
    
    update_doc = {}
    if "name" in update_data:
        update_doc["name"] = update_data["name"]
    if "code" in update_data:
        update_doc["code"] = update_data["code"]
    if "description" in update_data:
        update_doc["description"] = update_data["description"]
    if "status" in update_data:
        update_doc["status"] = update_data["status"]
    
    update_doc["updated_at"] = datetime.utcnow()
    
    await db[DEPARTMENTS_COLLECTION].update_one(
        {"_id": dept_oid},
        {"$set": update_doc}
    )
    
    updated = await db[DEPARTMENTS_COLLECTION].find_one({"_id": dept_oid})
    return _department_doc_to_public(updated)


async def create_service(service_in: ServiceCreate, dept_id: str, org_id: str) -> dict:
    """Crée un service pour un département."""
    db = get_database()
    
    # Vérifier que le département existe et appartient à l'organisation
    dept = await get_department_by_id(dept_id)
    if not dept:
        raise ValueError("Département introuvable.")
    
    if str(dept["organization_id"]) != org_id:
        raise ValueError("Le département n'appartient pas à votre organisation.")
    
    # Vérifier que le code n'existe pas déjà dans ce département
    existing = await db[SERVICES_COLLECTION].find_one({
        "department_id": ObjectId(dept_id),
        "code": service_in.code
    })
    if existing:
        raise ValueError(f"Un service avec le code '{service_in.code}' existe déjà dans ce département.")
    
    try:
        dept_oid = ObjectId(dept_id)
    except Exception:
        raise ValueError("department_id invalide.")
    
    doc = {
        "name": service_in.name,
        "code": service_in.code,
        "description": service_in.description,
        "department_id": dept_oid,
        "status": "active",
        "created_at": datetime.utcnow(),
    }
    
    result = await db[SERVICES_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _service_doc_to_public(doc)


async def list_services_by_department(dept_id: str) -> List[dict]:
    """Liste tous les services d'un département."""
    db = get_database()
    try:
        dept_oid = ObjectId(dept_id)
    except Exception:
        return []
    
    cursor = db[SERVICES_COLLECTION].find({"department_id": dept_oid})
    services = []
    async for doc in cursor:
        service = _service_doc_to_public(doc)
        # Compter les utilisateurs
        users_count = await db["users"].count_documents({"service_id": doc["_id"], "is_active": True})
        service["users_count"] = users_count
        services.append(service)
    return services


async def update_service(service_id: str, update_data: dict, org_id: str) -> dict:
    """Met à jour un service."""
    db = get_database()
    try:
        service_oid = ObjectId(service_id)
    except Exception:
        raise ValueError("service_id invalide.")
    
    # Vérifier que le service existe et appartient à l'organisation
    existing = await db[SERVICES_COLLECTION].find_one({"_id": service_oid})
    if not existing:
        raise ValueError("Service introuvable.")
    
    # Vérifier que le département appartient à l'organisation
    dept = await get_department_by_id(str(existing["department_id"]))
    if not dept or str(dept["organization_id"]) != org_id:
        raise ValueError("Le service n'appartient pas à votre organisation.")
    
    # Si le code change, vérifier qu'il n'existe pas déjà
    if "code" in update_data and update_data["code"] != existing.get("code"):
        existing_code = await db[SERVICES_COLLECTION].find_one({
            "department_id": existing["department_id"],
            "code": update_data["code"],
            "_id": {"$ne": service_oid}
        })
        if existing_code:
            raise ValueError(f"Un service avec le code '{update_data['code']}' existe déjà dans ce département.")
    
    update_doc = {}
    if "name" in update_data:
        update_doc["name"] = update_data["name"]
    if "code" in update_data:
        update_doc["code"] = update_data["code"]
    if "description" in update_data:
        update_doc["description"] = update_data["description"]
    if "status" in update_data:
        update_doc["status"] = update_data["status"]
    
    update_doc["updated_at"] = datetime.utcnow()
    
    await db[SERVICES_COLLECTION].update_one(
        {"_id": service_oid},
        {"$set": update_doc}
    )
    
    updated = await db[SERVICES_COLLECTION].find_one({"_id": service_oid})
    return _service_doc_to_public(updated)

