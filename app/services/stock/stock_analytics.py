from datetime import datetime, timedelta
from typing import List, Dict, Optional
from bson import ObjectId

from app.core.db import get_database
from app.models.stock.consommable import list_consommables_by_org, get_consommables_low_stock
from app.models.stock.demande_consommable import DEMANDES_CONSOMABLES_COLLECTION


async def get_stock_stats(org_id: str) -> Dict:
    """
    Calcule les statistiques générales du stock.
    """
    db = get_database()
    
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return {}
    
    # Récupérer tous les consommables
    consommables = await list_consommables_by_org(org_id)
    
    # Récupérer les alertes
    alertes = await get_consommables_low_stock(org_id)
    
    # Compter les demandes par statut
    demandes_en_attente = await db[DEMANDES_CONSOMABLES_COLLECTION].count_documents({
        "statut": "en_attente"
    })
    
    demandes_approuvees = await db[DEMANDES_CONSOMABLES_COLLECTION].count_documents({
        "statut": "approuve_directeur"
    })
    
    # Calculer la consommation du mois en cours
    debut_mois = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    consommation_mois = await db[DEMANDES_CONSOMABLES_COLLECTION].aggregate([
        {
            "$match": {
                "statut": "traite",
                "traitement_stock.date": {"$gte": debut_mois}
            }
        },
        {
            "$group": {
                "_id": None,
                "total": {"$sum": "$traitement_stock.quantite_accordee"}
            }
        }
    ])
    
    total_consommation = 0
    async for doc in consommation_mois:
        total_consommation = doc.get("total", 0)
    
    return {
        "total_consommables": len(consommables),
        "total_alertes": len(alertes),
        "demandes_en_attente": demandes_en_attente,
        "demandes_approuvees": demandes_approuvees,
        "consommation_mois_courant": total_consommation,
    }


async def get_consumption_data(org_id: str, days: int = 30) -> List[Dict]:
    """
    Récupère les données de consommation pour les graphiques.
    """
    db = get_database()
    
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return []
    
    # Récupérer les consommables de l'organisation
    consommables = await list_consommables_by_org(org_id)
    consommable_ids = [ObjectId(c["id"]) for c in consommables]
    
    # Date de début
    date_debut = datetime.utcnow() - timedelta(days=days)
    
    # Agréger les données par jour
    pipeline = [
        {
            "$match": {
                "consommable_id": {"$in": consommable_ids},
                "statut": "traite",
                "traitement_stock.date": {"$gte": date_debut}
            }
        },
        {
            "$group": {
                "_id": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": "$traitement_stock.date"
                    }
                },
                "total_quantite": {"$sum": "$traitement_stock.quantite_accordee"},
                "nombre_demandes": {"$sum": 1}
            }
        },
        {
            "$sort": {"_id": 1}
        }
    ]
    
    cursor = db[DEMANDES_CONSOMABLES_COLLECTION].aggregate(pipeline)
    data = []
    async for doc in cursor:
        data.append({
            "date": doc["_id"],
            "quantite": doc["total_quantite"],
            "nombre_demandes": doc["nombre_demandes"]
        })
    
    return data


async def get_top_consumables(org_id: str, limit: int = 5) -> List[Dict]:
    """
    Récupère les consommables les plus demandés.
    """
    db = get_database()
    
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return []
    
    # Récupérer les consommables de l'organisation
    consommables = await list_consommables_by_org(org_id)
    consommable_ids = [ObjectId(c["id"]) for c in consommables]
    
    # Agréger par consommable
    pipeline = [
        {
            "$match": {
                "consommable_id": {"$in": consommable_ids},
                "statut": "traite"
            }
        },
        {
            "$group": {
                "_id": "$consommable_id",
                "total_quantite": {"$sum": "$traitement_stock.quantite_accordee"},
                "nombre_demandes": {"$sum": 1}
            }
        },
        {
            "$sort": {"total_quantite": -1}
        },
        {
            "$limit": limit
        }
    ]
    
    cursor = db[DEMANDES_CONSOMABLES_COLLECTION].aggregate(pipeline)
    results = []
    
    # Créer un mapping des IDs vers les noms
    consommables_map = {c["id"]: c for c in consommables}
    
    async for doc in cursor:
        consommable_id = str(doc["_id"])
        consommable = consommables_map.get(consommable_id, {})
        
        results.append({
            "consommable_id": consommable_id,
            "type": consommable.get("type", "Inconnu"),
            "total_quantite": doc["total_quantite"],
            "nombre_demandes": doc["nombre_demandes"]
        })
    
    return results


async def get_department_consumption(org_id: str) -> List[Dict]:
    """
    Récupère la consommation par département.
    """
    db = get_database()
    
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return []
    
    # Récupérer les consommables de l'organisation
    consommables = await list_consommables_by_org(org_id)
    consommable_ids = [ObjectId(c["id"]) for c in consommables]
    
    # Agréger par département
    pipeline = [
        {
            "$match": {
                "consommable_id": {"$in": consommable_ids},
                "statut": "traite"
            }
        },
        {
            "$group": {
                "_id": "$department_id",
                "total_quantite": {"$sum": "$traitement_stock.quantite_accordee"},
                "nombre_demandes": {"$sum": 1}
            }
        },
        {
            "$sort": {"total_quantite": -1}
        }
    ]
    
    cursor = db[DEMANDES_CONSOMABLES_COLLECTION].aggregate(pipeline)
    results = []
    
    # Récupérer les noms des départements
    departments_map = {}
    async for doc in cursor:
        dept_id = str(doc["_id"])
        dept_doc = await db["departments"].find_one({"_id": ObjectId(dept_id)})
        dept_name = dept_doc.get("name", "Inconnu") if dept_doc else "Inconnu"
        
        results.append({
            "department_id": dept_id,
            "department_name": dept_name,
            "total_quantite": doc["total_quantite"],
            "nombre_demandes": doc["nombre_demandes"]
        })
    
    return results

