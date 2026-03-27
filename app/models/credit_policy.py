"""
Couche d'accès aux données MongoDB pour la politique de crédit.

Collections:
- credit_policy_config    : configuration active par organisation
- credit_policy_versions  : historique des versions archivées
- credit_policy_applications : demandes analysées
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from bson import ObjectId
from app.core.db import get_database


POLICY_CONFIG_COLLECTION = "credit_policy_config"
POLICY_VERSIONS_COLLECTION = "credit_policy_versions"
POLICY_APPLICATIONS_COLLECTION = "credit_policy_applications"


def _doc_to_config(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convertit un document MongoDB en dict public (ObjectId → string)"""
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


def _doc_to_version(doc: Dict[str, Any]) -> Dict[str, Any]:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


def _doc_to_application(doc: Dict[str, Any]) -> Dict[str, Any]:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


async def get_active_credit_policy(organization_id: str) -> Optional[Dict[str, Any]]:
    """Récupère la configuration active de crédit pour une organisation."""
    db = get_database()
    doc = await db[POLICY_CONFIG_COLLECTION].find_one(
        {"organization_id": organization_id, "status": "active"}
    )
    if doc:
        return _doc_to_config(doc)
    return None


async def create_or_update_credit_policy(
    organization_id: str,
    config_data: Dict[str, Any],
    user_id: str,
    user_name: str = ""
) -> Dict[str, Any]:
    """
    Crée ou met à jour la configuration active.
    Archive automatiquement la version précédente avant mise à jour.
    """
    db = get_database()
    now = datetime.utcnow()

    # Récupérer la config actuelle pour l'archiver
    existing = await db[POLICY_CONFIG_COLLECTION].find_one(
        {"organization_id": organization_id, "status": "active"}
    )

    if existing:
        # Calculer la prochaine version
        current_version = existing.get("version", "1.0")
        try:
            major, minor = current_version.split(".")
            new_version = f"{major}.{int(minor) + 1}"
        except Exception:
            new_version = "1.1"

        # Archiver la version précédente
        version_snapshot = {k: v for k, v in existing.items() if k != "_id"}
        version_snapshot["config_id"] = str(existing["_id"])
        version_snapshot["archived_at"] = now
        await db[POLICY_VERSIONS_COLLECTION].insert_one(version_snapshot)

        # Mettre à jour la config active
        update_data = {
            **config_data,
            "organization_id": organization_id,
            "version": new_version,
            "status": "active",
            "updatedAt": now,
            "updatedBy": user_name or user_id,
            "effectiveDate": existing.get("effectiveDate", now),
        }
        await db[POLICY_CONFIG_COLLECTION].update_one(
            {"_id": existing["_id"]},
            {"$set": update_data}
        )
        updated = await db[POLICY_CONFIG_COLLECTION].find_one({"_id": existing["_id"]})
        return _doc_to_config(updated)
    else:
        # Créer une nouvelle configuration
        new_doc = {
            **config_data,
            "organization_id": organization_id,
            "version": "1.0",
            "status": "active",
            "effectiveDate": now,
            "updatedAt": now,
            "updatedBy": user_name or user_id,
        }
        result = await db[POLICY_CONFIG_COLLECTION].insert_one(new_doc)
        created = await db[POLICY_CONFIG_COLLECTION].find_one({"_id": result.inserted_id})
        return _doc_to_config(created)


async def get_policy_versions(organization_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Récupère l'historique des versions de configuration."""
    db = get_database()
    cursor = db[POLICY_VERSIONS_COLLECTION].find(
        {"organization_id": organization_id}
    ).sort("archived_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [_doc_to_version(d) for d in docs]


async def restore_policy_version(
    organization_id: str,
    version_id: str,
    user_id: str
) -> Optional[Dict[str, Any]]:
    """Restaure une version archivée comme configuration active."""
    db = get_database()
    try:
        version_doc = await db[POLICY_VERSIONS_COLLECTION].find_one(
            {"_id": ObjectId(version_id), "organization_id": organization_id}
        )
    except Exception:
        return None

    if not version_doc:
        return None

    # Extraire uniquement les données de config
    excluded = {"_id", "id", "archived_at", "config_id", "organization_id",
                "version", "status", "updatedAt", "updatedBy", "effectiveDate"}
    config_data = {k: v for k, v in version_doc.items() if k not in excluded}

    return await create_or_update_credit_policy(
        organization_id, config_data, user_id, "restored"
    )


async def save_credit_application(
    user_id: str,
    organization_id: str,
    application_data: Dict[str, Any],
    result_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Enregistre une demande analysée en base."""
    db = get_database()
    doc = {
        "user_id": user_id,
        "organization_id": organization_id,
        "application": application_data,
        "result": result_data,
        "created_at": datetime.utcnow(),
    }
    result = await db[POLICY_APPLICATIONS_COLLECTION].insert_one(doc)
    created = await db[POLICY_APPLICATIONS_COLLECTION].find_one({"_id": result.inserted_id})
    return _doc_to_application(created)


async def get_user_applications(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Récupère les demandes analysées d'un utilisateur."""
    db = get_database()
    cursor = db[POLICY_APPLICATIONS_COLLECTION].find(
        {"user_id": user_id}
    ).sort("created_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [_doc_to_application(d) for d in docs]


async def get_org_applications(organization_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Récupère toutes les demandes d'une organisation (vue admin)."""
    db = get_database()
    cursor = db[POLICY_APPLICATIONS_COLLECTION].find(
        {"organization_id": organization_id}
    ).sort("created_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [_doc_to_application(d) for d in docs]
