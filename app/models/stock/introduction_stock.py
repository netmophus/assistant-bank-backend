from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from app.core.db import get_database
from app.models.stock.consommable import get_consommable_by_id, update_stock

INTRODUCTIONS_STOCK_COLLECTION = "introductions_stock"


def _introduction_doc_to_public(doc) -> dict:
    """Convertit un document MongoDB en dictionnaire public"""
    validation_drh = doc.get("validation_drh", {})
    # Convertir les ObjectId en string dans validation_drh
    validation_drh_clean = {}
    if validation_drh and isinstance(validation_drh, dict):
        for key, value in validation_drh.items():
            if key == "agent_drh_id" and value:
                # Convertir ObjectId en string
                validation_drh_clean[key] = str(value)
            elif key == "date" and value:
                # Convertir datetime en string ISO
                if isinstance(value, datetime):
                    validation_drh_clean[key] = value.isoformat()
                elif isinstance(value, str):
                    validation_drh_clean[key] = value
                else:
                    validation_drh_clean[key] = None
            else:
                validation_drh_clean[key] = value
    
    return {
        "id": str(doc["_id"]),
        "consommable_id": str(doc["consommable_id"]),
        "gestionnaire_id": str(doc["gestionnaire_id"]),
        "organization_id": str(doc["organization_id"]),
        "quantite": doc.get("quantite", 0),
        "type_quantite": doc.get("type_quantite", "conteneur"),
        "operation": doc.get("operation", "add"),
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


async def create_introduction_stock(introduction_data: dict) -> dict:
    """
    Crée une demande d'introduction de stock.
    """
    db = get_database()

    try:
        consommable_oid = ObjectId(introduction_data["consommable_id"])
        gestionnaire_oid = ObjectId(introduction_data["gestionnaire_id"])
        org_oid = ObjectId(introduction_data["organization_id"])
    except Exception:
        raise ValueError("IDs invalides.")

    # Vérifier que le consommable existe
    consommable = await get_consommable_by_id(introduction_data["consommable_id"])
    if not consommable:
        raise ValueError("Consommable introuvable.")

    if consommable["organization_id"] != introduction_data["organization_id"]:
        raise ValueError("Le consommable n'appartient pas à cette organisation.")

    introduction_doc = {
        "consommable_id": consommable_oid,
        "gestionnaire_id": gestionnaire_oid,
        "organization_id": org_oid,
        "quantite": introduction_data.get("quantite", 0),
        "type_quantite": introduction_data.get("type_quantite", "conteneur"),
        "operation": introduction_data.get("operation", "add"),
        "motif": introduction_data.get("motif", ""),
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

    result = await db[INTRODUCTIONS_STOCK_COLLECTION].insert_one(introduction_doc)
    introduction_doc["_id"] = result.inserted_id

    return _introduction_doc_to_public(introduction_doc)


async def get_introduction_by_id(introduction_id: str) -> Optional[dict]:
    """Récupère une introduction de stock par son ID"""
    db = get_database()
    try:
        doc = await db[INTRODUCTIONS_STOCK_COLLECTION].find_one(
            {"_id": ObjectId(introduction_id)}
        )
        if doc:
            return _introduction_doc_to_public(doc)
        return None
    except Exception:
        return None


async def list_introductions_pending_drh(org_id: str) -> List[dict]:
    """Liste les introductions de stock en attente de validation DRH"""
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return []

    cursor = (
        db[INTRODUCTIONS_STOCK_COLLECTION]
        .find(
            {
                "organization_id": org_oid,
                "statut": "en_attente",
                "validation_drh.statut": "en_attente",
            }
        )
        .sort("created_at", 1)
    )

    introductions = []
    async for doc in cursor:
        introductions.append(_introduction_doc_to_public(doc))
    return introductions


async def list_introductions_by_gestionnaire(gestionnaire_id: str) -> List[dict]:
    """Liste les introductions de stock d'un gestionnaire (exclut les introductions validées)"""
    db = get_database()
    try:
        gestionnaire_oid = ObjectId(gestionnaire_id)
    except Exception:
        return []

    # Filtrer pour exclure les introductions validées (statut != "valide")
    cursor = (
        db[INTRODUCTIONS_STOCK_COLLECTION]
        .find({
            "gestionnaire_id": gestionnaire_oid,
            "statut": {"$ne": "valide"}  # Exclure les introductions validées
        })
        .sort("created_at", -1)
    )

    introductions = []
    async for doc in cursor:
        introductions.append(_introduction_doc_to_public(doc))
    return introductions


async def valider_introduction_drh(
    introduction_id: str, agent_drh_id: str, commentaire: Optional[str] = None
) -> Optional[dict]:
    """Valide une introduction de stock par l'agent DRH et applique la mise à jour du stock"""
    db = get_database()
    try:
        introduction_oid = ObjectId(introduction_id)
        agent_drh_oid = ObjectId(agent_drh_id)
    except Exception as e:
        raise ValueError(f"ID invalide: {str(e)}")

    # Récupérer l'introduction
    introduction = await db[INTRODUCTIONS_STOCK_COLLECTION].find_one(
        {"_id": introduction_oid}
    )
    if not introduction:
        raise ValueError("Introduction introuvable.")
    
    if introduction.get("statut") != "en_attente":
        raise ValueError(f"Cette introduction a déjà été traitée (statut: {introduction.get('statut')}).")

    # Appliquer la mise à jour du stock
    consommable_id = str(introduction["consommable_id"])
    quantite = introduction.get("quantite", 0)
    type_quantite = introduction.get("type_quantite", "conteneur")
    operation = introduction.get("operation", "add")

    if quantite <= 0:
        raise ValueError("La quantité doit être supérieure à 0.")

    # Récupérer le consommable pour obtenir quantite_par_conteneur
    consommable = await get_consommable_by_id(consommable_id)
    if not consommable:
        raise ValueError("Consommable introuvable.")

    # Convertir les unités en conteneurs si nécessaire
    quantite_conteneurs = quantite
    if type_quantite == "unite":
        quantite_par_conteneur = consommable.get("quantite_par_conteneur", 1)
        if quantite_par_conteneur <= 0:
            quantite_par_conteneur = 1
        # Convertir les unités en conteneurs (arrondi à l'entier supérieur pour éviter la perte)
        quantite_conteneurs = (quantite + quantite_par_conteneur - 1) // quantite_par_conteneur

    # Mettre à jour le stock (la fonction update_stock lève une exception en cas d'erreur)
    await update_stock(consommable_id, quantite_conteneurs, operation)

    # Mettre à jour l'introduction
    result = await db[INTRODUCTIONS_STOCK_COLLECTION].update_one(
        {"_id": introduction_oid},
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
        raise ValueError("Erreur lors de la mise à jour de l'introduction.")

    updated_doc = await db[INTRODUCTIONS_STOCK_COLLECTION].find_one(
        {"_id": introduction_oid}
    )
    if updated_doc:
        return _introduction_doc_to_public(updated_doc)
    
    raise ValueError("Erreur lors de la récupération de l'introduction mise à jour.")


async def rejeter_introduction_drh(
    introduction_id: str, agent_drh_id: str, commentaire: Optional[str] = None
) -> Optional[dict]:
    """Rejette une introduction de stock par l'agent DRH"""
    db = get_database()
    try:
        introduction_oid = ObjectId(introduction_id)
        agent_drh_oid = ObjectId(agent_drh_id)
    except Exception:
        return None

    # Récupérer l'introduction
    introduction = await db[INTRODUCTIONS_STOCK_COLLECTION].find_one(
        {"_id": introduction_oid}
    )
    if not introduction or introduction.get("statut") != "en_attente":
        return None

    # Mettre à jour l'introduction
    result = await db[INTRODUCTIONS_STOCK_COLLECTION].update_one(
        {"_id": introduction_oid},
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
        updated_doc = await db[INTRODUCTIONS_STOCK_COLLECTION].find_one(
            {"_id": introduction_oid}
        )
        if updated_doc:
            return _introduction_doc_to_public(updated_doc)

    return None
