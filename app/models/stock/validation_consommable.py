from datetime import datetime
from typing import List, Optional, Dict, Any

from bson import ObjectId

from app.core.db import get_database
from app.models.stock.consommable import create_consommable, update_consommable, get_consommable_by_id

VALIDATION_CONSOMMABLES_COLLECTION = "validation_consommables"


def _validation_consommable_doc_to_public(doc) -> dict:
    """Convertit un document MongoDB en dictionnaire public"""
    validation_drh = doc.get("validation_drh", {})
    # Convertir les ObjectId en string dans validation_drh
    validation_drh_clean = {}
    if validation_drh and isinstance(validation_drh, dict):
        for key, value in validation_drh.items():
            if key == "agent_drh_id" and value:
                validation_drh_clean[key] = str(value)
            elif key == "date" and value:
                if isinstance(value, datetime):
                    validation_drh_clean[key] = value.isoformat()
                elif isinstance(value, str):
                    validation_drh_clean[key] = value
                else:
                    validation_drh_clean[key] = None
            else:
                validation_drh_clean[key] = value

    consommable_id = doc.get("consommable_id")
    if consommable_id:
        consommable_id = str(consommable_id)
    else:
        consommable_id = None

    return {
        "id": str(doc["_id"]),
        "action": doc.get("action", "create"),
        "consommable_id": consommable_id,
        "consommable_data": doc.get("consommable_data", {}),
        "gestionnaire_id": str(doc["gestionnaire_id"]),
        "organization_id": str(doc["organization_id"]),
        "motif": doc.get("motif", ""),
        "statut": doc.get("statut", "en_attente"),
        "validation_drh": validation_drh_clean,
        "created_at": doc.get("created_at").isoformat()
        if doc.get("created_at") and isinstance(doc.get("created_at"), datetime)
        else None,
        "updated_at": doc.get("updated_at").isoformat()
        if doc.get("updated_at") and isinstance(doc.get("updated_at"), datetime)
        else None,
    }


async def create_validation_consommable_request(
    request_data: Dict[str, Any], gestionnaire_id: str, organization_id: str
) -> dict:
    """Crée une demande de validation pour création/modification de consommable"""
    db = get_database()

    try:
        gestionnaire_oid = ObjectId(gestionnaire_id)
        org_oid = ObjectId(organization_id)
    except Exception:
        raise ValueError("IDs invalides.")

    # Si c'est une modification, vérifier que le consommable existe
    if request_data.get("action") == "update":
        consommable_id = request_data.get("consommable_id")
        if not consommable_id:
            raise ValueError("consommable_id requis pour une modification.")
        
        consommable = await get_consommable_by_id(consommable_id)
        if not consommable:
            raise ValueError("Consommable introuvable.")
        
        if consommable["organization_id"] != organization_id:
            raise ValueError("Le consommable n'appartient pas à cette organisation.")

    request_doc = {
        "action": request_data.get("action", "create"),
        "consommable_id": ObjectId(request_data["consommable_id"]) if request_data.get("consommable_id") else None,
        "consommable_data": request_data.get("consommable_data", {}),
        "gestionnaire_id": gestionnaire_oid,
        "organization_id": org_oid,
        "motif": request_data.get("motif", ""),
        "statut": "en_attente",
        "validation_drh": {
            "statut": "en_attente",
            "agent_drh_id": None,
            "date": None,
            "commentaire": None,
        },
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = await db[VALIDATION_CONSOMMABLES_COLLECTION].insert_one(request_doc)
    request_doc["_id"] = result.inserted_id

    return _validation_consommable_doc_to_public(request_doc)


async def list_validation_consommables_pending_drh(org_id: str) -> List[dict]:
    """Liste les demandes de validation de consommables en attente de validation DRH"""
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return []

    cursor = (
        db[VALIDATION_CONSOMMABLES_COLLECTION]
        .find(
            {
                "organization_id": org_oid,
                "statut": "en_attente",
                "validation_drh.statut": "en_attente",
            }
        )
        .sort("created_at", 1)
    )

    requests = []
    async for doc in cursor:
        requests.append(_validation_consommable_doc_to_public(doc))
    return requests


async def list_validation_consommables_by_gestionnaire(gestionnaire_id: str) -> List[dict]:
    """Liste les demandes de validation de consommables d'un gestionnaire (exclut les demandes validées)"""
    db = get_database()
    try:
        gestionnaire_oid = ObjectId(gestionnaire_id)
    except Exception:
        return []

    # Filtrer pour exclure les demandes validées (statut != "valide")
    cursor = (
        db[VALIDATION_CONSOMMABLES_COLLECTION]
        .find({
            "gestionnaire_id": gestionnaire_oid,
            "statut": {"$ne": "valide"}  # Exclure les demandes validées
        })
        .sort("created_at", -1)
    )

    requests = []
    async for doc in cursor:
        requests.append(_validation_consommable_doc_to_public(doc))
    return requests


async def get_validation_consommable_by_id(request_id: str) -> Optional[dict]:
    """Récupère une demande de validation par son ID"""
    db = get_database()
    try:
        doc = await db[VALIDATION_CONSOMMABLES_COLLECTION].find_one(
            {"_id": ObjectId(request_id)}
        )
        if doc:
            return _validation_consommable_doc_to_public(doc)
        return None
    except Exception:
        return None


async def valider_consommable_modification_drh(
    request_id: str, agent_drh_id: str, commentaire: Optional[str] = None
) -> Optional[dict]:
    """Valide une demande de modification/création de consommable par l'agent DRH"""
    db = get_database()
    try:
        request_oid = ObjectId(request_id)
        agent_drh_oid = ObjectId(agent_drh_id)
    except Exception as e:
        raise ValueError(f"ID invalide: {str(e)}")

    # Récupérer la demande
    request_doc = await db[VALIDATION_CONSOMMABLES_COLLECTION].find_one(
        {"_id": request_oid}
    )
    if not request_doc:
        raise ValueError("Demande introuvable.")
    
    if request_doc.get("statut") != "en_attente":
        raise ValueError(f"Cette demande a déjà été traitée (statut: {request_doc.get('statut')}).")

    action = request_doc.get("action", "create")
    consommable_data = request_doc.get("consommable_data", {})
    organization_id = str(request_doc["organization_id"])

    # Appliquer la création ou modification
    if action == "create":
        consommable = await create_consommable(consommable_data, organization_id)
        if not consommable:
            raise ValueError("Erreur lors de la création du consommable.")
    elif action == "update":
        consommable_id = str(request_doc.get("consommable_id"))
        if not consommable_id:
            raise ValueError("consommable_id manquant pour la modification.")
        
        # Vérifier que le consommable existe
        existing_consommable = await get_consommable_by_id(consommable_id)
        if not existing_consommable:
            raise ValueError("Consommable introuvable pour la modification.")
        
        # Filtrer les valeurs None pour la mise à jour
        update_data = {k: v for k, v in consommable_data.items() if v is not None}
        if not update_data:
            raise ValueError("Aucune donnée à mettre à jour.")
        
        updated = await update_consommable(consommable_id, update_data)
        if not updated:
            raise ValueError("Erreur lors de la modification du consommable (aucune modification effectuée).")
    else:
        raise ValueError(f"Action invalide: {action}")

    # Mettre à jour la demande
    result = await db[VALIDATION_CONSOMMABLES_COLLECTION].update_one(
        {"_id": request_oid},
        {
            "$set": {
                "statut": "valide",
                "validation_drh": {
                    "statut": "valide",
                    "agent_drh_id": agent_drh_oid,
                    "date": datetime.utcnow(),
                    "commentaire": commentaire,
                },
                "updated_at": datetime.utcnow(),
            }
        },
    )

    if result.modified_count == 0:
        raise ValueError("Erreur lors de la mise à jour de la demande.")

    updated_doc = await db[VALIDATION_CONSOMMABLES_COLLECTION].find_one(
        {"_id": request_oid}
    )
    if updated_doc:
        return _validation_consommable_doc_to_public(updated_doc)
    
    raise ValueError("Erreur lors de la récupération de la demande mise à jour.")


async def rejeter_consommable_modification_drh(
    request_id: str, agent_drh_id: str, commentaire: Optional[str] = None
) -> Optional[dict]:
    """Rejette une demande de modification/création de consommable par l'agent DRH"""
    db = get_database()
    try:
        request_oid = ObjectId(request_id)
        agent_drh_oid = ObjectId(agent_drh_id)
    except Exception:
        return None

    # Récupérer la demande
    request_doc = await db[VALIDATION_CONSOMMABLES_COLLECTION].find_one(
        {"_id": request_oid}
    )
    if not request_doc or request_doc.get("statut") != "en_attente":
        return None

    # Mettre à jour la demande
    result = await db[VALIDATION_CONSOMMABLES_COLLECTION].update_one(
        {"_id": request_oid},
        {
            "$set": {
                "statut": "rejete",
                "validation_drh": {
                    "statut": "rejete",
                    "agent_drh_id": agent_drh_oid,
                    "date": datetime.utcnow(),
                    "commentaire": commentaire,
                },
                "updated_at": datetime.utcnow(),
            }
        },
    )

    if result.modified_count > 0:
        updated_doc = await db[VALIDATION_CONSOMMABLES_COLLECTION].find_one(
            {"_id": request_oid}
        )
        if updated_doc:
            return _validation_consommable_doc_to_public(updated_doc)

    return None

