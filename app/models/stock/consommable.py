from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from app.core.db import get_database
from app.models.organization import get_organization_by_id

CONSOMMABLES_COLLECTION = "consommables"


def _consommable_doc_to_public(doc) -> dict:
    """Convertit un document MongoDB en dictionnaire public"""
    quantite_stock_conteneur = doc.get("quantite_stock_conteneur", 0)
    quantite_par_conteneur = doc.get("quantite_par_conteneur", 1)
    quantite_stock_total = quantite_stock_conteneur * quantite_par_conteneur

    return {
        "id": str(doc["_id"]),
        "type": doc["type"],
        "description": doc.get("description", ""),
        "unite_base": doc.get("unite_base", "unité"),
        "unite_conteneur": doc.get("unite_conteneur", "unité"),
        "quantite_par_conteneur": quantite_par_conteneur,
        "quantite_stock_conteneur": quantite_stock_conteneur,
        "quantite_stock_total": quantite_stock_total,
        "limite_alerte": doc.get("limite_alerte", 0),
        "organization_id": str(doc["organization_id"]),
        "created_at": doc.get("created_at").isoformat()
        if doc.get("created_at") and isinstance(doc.get("created_at"), datetime)
        else None,
        "updated_at": doc.get("updated_at").isoformat()
        if doc.get("updated_at") and isinstance(doc.get("updated_at"), datetime)
        else None,
    }


async def create_consommable(consommable_data: dict, org_id: str) -> dict:
    """
    Crée un consommable.
    """
    db = get_database()

    # Vérifier que l'organisation existe
    org = await get_organization_by_id(org_id)
    if not org:
        raise ValueError("Organisation introuvable.")

    try:
        org_oid = ObjectId(org_id)
    except Exception:
        raise ValueError("organization_id invalide.")

    consommable_doc = {
        "type": consommable_data.get("type"),
        "description": consommable_data.get("description", ""),
        "unite_base": consommable_data.get("unite_base", "unité"),
        "unite_conteneur": consommable_data.get("unite_conteneur", "unité"),
        "quantite_par_conteneur": consommable_data.get("quantite_par_conteneur", 1),
        "quantite_stock_conteneur": consommable_data.get("quantite_stock_conteneur", 0),
        "limite_alerte": consommable_data.get("limite_alerte", 0),
        "organization_id": org_oid,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = await db[CONSOMMABLES_COLLECTION].insert_one(consommable_doc)
    consommable_doc["_id"] = result.inserted_id

    return _consommable_doc_to_public(consommable_doc)


async def get_consommable_by_id(consommable_id: str) -> Optional[dict]:
    """Récupère un consommable par son ID"""
    db = get_database()
    try:
        doc = await db[CONSOMMABLES_COLLECTION].find_one(
            {"_id": ObjectId(consommable_id)}
        )
        if doc:
            return _consommable_doc_to_public(doc)
        return None
    except Exception:
        return None


async def list_consommables_by_org(org_id: str) -> List[dict]:
    """Liste toutes les consommables d'une organisation"""
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return []

    cursor = (
        db[CONSOMMABLES_COLLECTION]
        .find({"organization_id": org_oid})
        .sort("created_at", -1)
    )
    consommables = []
    async for doc in cursor:
        consommables.append(_consommable_doc_to_public(doc))
    return consommables


async def list_consommables_available(org_id: str) -> List[dict]:
    """Liste les consommables disponibles (stock > 0) pour les utilisateurs"""
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return []

    cursor = (
        db[CONSOMMABLES_COLLECTION]
        .find({"organization_id": org_oid, "quantite_stock_conteneur": {"$gt": 0}})
        .sort("type", 1)
    )

    consommables = []
    async for doc in cursor:
        consommables.append(_consommable_doc_to_public(doc))
    return consommables


async def update_consommable(
    consommable_id: str, consommable_data: dict
) -> Optional[dict]:
    """Met à jour un consommable"""
    db = get_database()
    try:
        consommable_oid = ObjectId(consommable_id)
    except Exception:
        return None

    update_data = {
        "updated_at": datetime.utcnow(),
    }

    if "type" in consommable_data:
        update_data["type"] = consommable_data["type"]
    if "description" in consommable_data:
        update_data["description"] = consommable_data.get("description", "")
    if "unite_base" in consommable_data:
        update_data["unite_base"] = consommable_data["unite_base"]
    if "unite_conteneur" in consommable_data:
        update_data["unite_conteneur"] = consommable_data["unite_conteneur"]
    if "quantite_par_conteneur" in consommable_data:
        update_data["quantite_par_conteneur"] = consommable_data[
            "quantite_par_conteneur"
        ]
    if "quantite_stock_conteneur" in consommable_data:
        update_data["quantite_stock_conteneur"] = consommable_data[
            "quantite_stock_conteneur"
        ]
    if "limite_alerte" in consommable_data:
        update_data["limite_alerte"] = consommable_data["limite_alerte"]

    result = await db[CONSOMMABLES_COLLECTION].update_one(
        {"_id": consommable_oid}, {"$set": update_data}
    )

    if result.modified_count > 0:
        updated_doc = await db[CONSOMMABLES_COLLECTION].find_one(
            {"_id": consommable_oid}
        )
        if updated_doc:
            return _consommable_doc_to_public(updated_doc)

    return None


async def update_stock(
    consommable_id: str, quantite: int, operation: str = "set"
) -> Optional[dict]:
    """
    Met à jour le stock d'un consommable en conteneurs.
    operation: "set" (remplacer), "add" (ajouter), "subtract" (soustraire)
    """
    db = get_database()
    try:
        consommable_oid = ObjectId(consommable_id)
    except Exception:
        return None

    consommable = await db[CONSOMMABLES_COLLECTION].find_one({"_id": consommable_oid})
    if not consommable:
        return None

    current_stock = consommable.get("quantite_stock_conteneur", 0)

    if operation == "set":
        new_stock = quantite
    elif operation == "add":
        new_stock = current_stock + quantite
    elif operation == "subtract":
        new_stock = max(0, current_stock - quantite)  # Ne pas aller en négatif
    else:
        return None

    result = await db[CONSOMMABLES_COLLECTION].update_one(
        {"_id": consommable_oid},
        {
            "$set": {
                "quantite_stock_conteneur": new_stock,
                "updated_at": datetime.utcnow(),
            }
        },
    )

    if result.modified_count > 0:
        updated_doc = await db[CONSOMMABLES_COLLECTION].find_one(
            {"_id": consommable_oid}
        )
        if updated_doc:
            return _consommable_doc_to_public(updated_doc)

    return None


async def delete_consommable(consommable_id: str) -> bool:
    """Supprime un consommable"""
    db = get_database()
    try:
        consommable_oid = ObjectId(consommable_id)
    except Exception:
        return False

    result = await db[CONSOMMABLES_COLLECTION].delete_one({"_id": consommable_oid})
    return result.deleted_count > 0


async def get_consommables_low_stock(org_id: str) -> List[dict]:
    """Récupère les consommables en alerte (stock <= limite_alerte)"""
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return []

    cursor = (
        db[CONSOMMABLES_COLLECTION]
        .find(
            {
                "organization_id": org_oid,
                "$expr": {"$lte": ["$quantite_stock_conteneur", "$limite_alerte"]},
            }
        )
        .sort("quantite_stock_conteneur", 1)
    )

    consommables = []
    async for doc in cursor:
        consommables.append(_consommable_doc_to_public(doc))
    return consommables
