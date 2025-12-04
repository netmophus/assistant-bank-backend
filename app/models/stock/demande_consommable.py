from datetime import datetime
from typing import Optional, List
from bson import ObjectId

from app.core.db import get_database
from app.models.stock.consommable import get_consommable_by_id, update_stock

DEMANDES_CONSOMABLES_COLLECTION = "demandes_consommables"


def _demande_doc_to_public(doc) -> dict:
    """Convertit un document MongoDB en dictionnaire public"""
    return {
        "id": str(doc["_id"]),
        "consommable_id": str(doc["consommable_id"]),
        "user_id": str(doc["user_id"]),
        "department_id": str(doc["department_id"]),
        "quantite_demandee": doc.get("quantite_demandee", 0),
        "motif": doc.get("motif", ""),
        "statut": doc.get("statut", "en_attente"),
        "approbation_directeur": doc.get("approbation_directeur", {}),
        "traitement_stock": doc.get("traitement_stock", {}),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") and isinstance(doc.get("created_at"), datetime) else None,
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") and isinstance(doc.get("updated_at"), datetime) else None,
    }


async def create_demande(demande_data: dict) -> dict:
    """
    Crée une demande de consommable.
    """
    db = get_database()
    
    try:
        consommable_oid = ObjectId(demande_data["consommable_id"])
        user_oid = ObjectId(demande_data["user_id"])
        dept_oid = ObjectId(demande_data["department_id"])
    except Exception:
        raise ValueError("IDs invalides.")
    
    # Vérifier que le consommable existe et a du stock
    consommable = await get_consommable_by_id(demande_data["consommable_id"])
    if not consommable:
        raise ValueError("Consommable introuvable.")
    
    if consommable["quantite_stock"] <= 0:
        raise ValueError("Stock insuffisant pour ce consommable.")
    
    demande_doc = {
        "consommable_id": consommable_oid,
        "user_id": user_oid,
        "department_id": dept_oid,
        "quantite_demandee": demande_data.get("quantite_demandee", 0),
        "motif": demande_data.get("motif", ""),
        "statut": "en_attente",
        "approbation_directeur": {
            "statut": "en_attente",
            "directeur_id": None,
            "date": None,
            "commentaire": None,
        },
        "traitement_stock": {
            "gestionnaire_id": None,
            "date": None,
            "quantite_accordee": None,
            "commentaire": None,
        },
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    
    result = await db[DEMANDES_CONSOMABLES_COLLECTION].insert_one(demande_doc)
    demande_doc["_id"] = result.inserted_id
    
    return _demande_doc_to_public(demande_doc)


async def get_demande_by_id(demande_id: str) -> Optional[dict]:
    """Récupère une demande par son ID"""
    db = get_database()
    try:
        doc = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one({"_id": ObjectId(demande_id)})
        if doc:
            return _demande_doc_to_public(doc)
        return None
    except Exception:
        return None


async def list_demandes_by_user(user_id: str) -> List[dict]:
    """Liste les demandes d'un utilisateur"""
    db = get_database()
    try:
        user_oid = ObjectId(user_id)
    except Exception:
        return []
    
    cursor = db[DEMANDES_CONSOMABLES_COLLECTION].find({"user_id": user_oid}).sort("created_at", -1)
    demandes = []
    async for doc in cursor:
        demandes.append(_demande_doc_to_public(doc))
    return demandes


async def list_demandes_by_department(department_id: str) -> List[dict]:
    """Liste les demandes d'un département"""
    db = get_database()
    try:
        dept_oid = ObjectId(department_id)
    except Exception:
        return []
    
    cursor = db[DEMANDES_CONSOMABLES_COLLECTION].find({"department_id": dept_oid}).sort("created_at", -1)
    demandes = []
    async for doc in cursor:
        demandes.append(_demande_doc_to_public(doc))
    return demandes


async def list_demandes_pending_directeur(department_id: str) -> List[dict]:
    """Liste les demandes en attente de validation par le directeur"""
    db = get_database()
    try:
        dept_oid = ObjectId(department_id)
    except Exception:
        return []
    
    cursor = db[DEMANDES_CONSOMABLES_COLLECTION].find({
        "department_id": dept_oid,
        "statut": "en_attente",
        "approbation_directeur.statut": "en_attente"
    }).sort("created_at", 1)
    
    demandes = []
    async for doc in cursor:
        demandes.append(_demande_doc_to_public(doc))
    return demandes


async def list_demandes_pending_gestionnaire(org_id: str) -> List[dict]:
    """Liste les demandes approuvées en attente de traitement par le gestionnaire"""
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return []
    
    # Récupérer les consommables de l'organisation
    from app.models.stock.consommable import list_consommables_by_org
    consommables = await list_consommables_by_org(org_id)
    consommable_ids = [ObjectId(c["id"]) for c in consommables]
    
    cursor = db[DEMANDES_CONSOMABLES_COLLECTION].find({
        "consommable_id": {"$in": consommable_ids},
        "statut": "approuve_directeur",
        "approbation_directeur.statut": "approuve"
    }).sort("approbation_directeur.date", 1)
    
    demandes = []
    async for doc in cursor:
        demandes.append(_demande_doc_to_public(doc))
    return demandes


async def approve_demande_directeur(demande_id: str, directeur_id: str, commentaire: Optional[str] = None) -> Optional[dict]:
    """Approuve une demande par le directeur"""
    db = get_database()
    try:
        demande_oid = ObjectId(demande_id)
        directeur_oid = ObjectId(directeur_id)
    except Exception:
        return None
    
    result = await db[DEMANDES_CONSOMABLES_COLLECTION].update_one(
        {"_id": demande_oid},
        {
            "$set": {
                "statut": "approuve_directeur",
                "approbation_directeur": {
                    "statut": "approuve",
                    "directeur_id": directeur_oid,
                    "date": datetime.utcnow(),
                    "commentaire": commentaire,
                },
                "updated_at": datetime.utcnow(),
            }
        }
    )
    
    if result.modified_count > 0:
        updated_doc = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one({"_id": demande_oid})
        if updated_doc:
            return _demande_doc_to_public(updated_doc)
    
    return None


async def reject_demande_directeur(demande_id: str, directeur_id: str, commentaire: Optional[str] = None) -> Optional[dict]:
    """Rejette une demande par le directeur"""
    db = get_database()
    try:
        demande_oid = ObjectId(demande_id)
        directeur_oid = ObjectId(directeur_id)
    except Exception:
        return None
    
    result = await db[DEMANDES_CONSOMABLES_COLLECTION].update_one(
        {"_id": demande_oid},
        {
            "$set": {
                "statut": "rejete_directeur",
                "approbation_directeur": {
                    "statut": "rejete",
                    "directeur_id": directeur_oid,
                    "date": datetime.utcnow(),
                    "commentaire": commentaire,
                },
                "updated_at": datetime.utcnow(),
            }
        }
    )
    
    if result.modified_count > 0:
        updated_doc = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one({"_id": demande_oid})
        if updated_doc:
            return _demande_doc_to_public(updated_doc)
    
    return None


async def traiter_demande_gestionnaire(demande_id: str, gestionnaire_id: str, quantite_accordee: int, commentaire: Optional[str] = None) -> Optional[dict]:
    """Traite une demande approuvée par le gestionnaire de stock"""
    db = get_database()
    try:
        demande_oid = ObjectId(demande_id)
        gestionnaire_oid = ObjectId(gestionnaire_id)
    except Exception:
        return None
    
    # Récupérer la demande
    demande = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one({"_id": demande_oid})
    if not demande:
        return None
    
    # Vérifier que la demande est approuvée
    if demande.get("statut") != "approuve_directeur":
        return None
    
    # Vérifier le stock disponible
    consommable = await get_consommable_by_id(str(demande["consommable_id"]))
    if not consommable:
        return None
    
    quantite_finale = min(quantite_accordee, consommable["quantite_stock"])
    
    # Débiter le stock
    await update_stock(str(demande["consommable_id"]), quantite_finale, "subtract")
    
    # Mettre à jour la demande
    result = await db[DEMANDES_CONSOMABLES_COLLECTION].update_one(
        {"_id": demande_oid},
        {
            "$set": {
                "statut": "traite",
                "traitement_stock": {
                    "gestionnaire_id": gestionnaire_oid,
                    "date": datetime.utcnow(),
                    "quantite_accordee": quantite_finale,
                    "commentaire": commentaire,
                },
                "updated_at": datetime.utcnow(),
            }
        }
    )
    
    if result.modified_count > 0:
        updated_doc = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one({"_id": demande_oid})
        if updated_doc:
            return _demande_doc_to_public(updated_doc)
    
    return None


async def get_demande_history(demande_id: str) -> List[dict]:
    """Récupère l'historique complet d'une demande"""
    demande = await get_demande_by_id(demande_id)
    if not demande:
        return []
    
    history = []
    
    # Étape 1: Création
    history.append({
        "date": demande["created_at"],
        "action": "Demande créée",
        "user_id": demande["user_id"],
    })
    
    # Étape 2: Validation directeur
    if demande.get("approbation_directeur", {}).get("date"):
        approbation = demande["approbation_directeur"]
        history.append({
            "date": approbation["date"],
            "action": "Approuvée par le directeur" if approbation["statut"] == "approuve" else "Rejetée par le directeur",
            "user_id": approbation.get("directeur_id"),
            "commentaire": approbation.get("commentaire"),
        })
    
    # Étape 3: Traitement gestionnaire
    if demande.get("traitement_stock", {}).get("date"):
        traitement = demande["traitement_stock"]
        history.append({
            "date": traitement["date"],
            "action": f"Traitée - {traitement.get('quantite_accordee', 0)} unités accordées",
            "user_id": traitement.get("gestionnaire_id"),
            "commentaire": traitement.get("commentaire"),
        })
    
    return sorted(history, key=lambda x: x["date"] or "")

