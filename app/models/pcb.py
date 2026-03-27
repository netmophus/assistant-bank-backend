"""
Modèles MongoDB pour le système PCB UEMOA
Gestion des comptes GL, postes réglementaires et rapports financiers
"""
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from bson import ObjectId
from app.core.db import get_database

PCB_GL_COLLECTION = "pcb_gl_accounts"
PCB_POSTES_COLLECTION = "pcb_postes_reglementaires"
PCB_REPORTS_COLLECTION = "pcb_reports"
PCB_POSTE_EXERCICE_VALUES_COLLECTION = "pcb_poste_exercice_values"
PCB_RATIO_VARIABLE_CATALOG_COLLECTION = "pcb_ratio_variable_catalog"
PCB_RATIO_VARIABLE_VALUES_COLLECTION = "pcb_ratio_variable_values"

# Variable pour vérifier si les index ont été créés
_indexes_created = False


async def ensure_pcb_indexes():
    """Crée les index nécessaires pour optimiser les requêtes PCB"""
    global _indexes_created
    if _indexes_created:
        return
    
    db = get_database()
    
    try:
        # Index pour les comptes GL : organization_id + date_solde (pour les requêtes de suppression et de recherche)
        await db[PCB_GL_COLLECTION].create_index([("organization_id", 1), ("date_solde", 1)])
        # Index pour les comptes GL : code (pour les recherches par code)
        await db[PCB_GL_COLLECTION].create_index([("code", 1)])
        # Index pour les postes réglementaires : organization_id
        await db[PCB_POSTES_COLLECTION].create_index([("organization_id", 1)])
        # Index pour les postes réglementaires : parent_id (pour les requêtes hiérarchiques)
        await db[PCB_POSTES_COLLECTION].create_index([("parent_id", 1)])

        # Index pour les valeurs par exercice : organization_id + exercice + poste_id
        await db[PCB_POSTE_EXERCICE_VALUES_COLLECTION].create_index(
            [("organization_id", 1), ("exercice", 1), ("poste_id", 1)],
            unique=True,
        )

        # Catalogue variables ratios: unique par organisation + key
        await db[PCB_RATIO_VARIABLE_CATALOG_COLLECTION].create_index(
            [("organization_id", 1), ("key", 1)],
            unique=True,
        )

        # Valeurs variables ratios: unique par organisation + date_solde + key
        await db[PCB_RATIO_VARIABLE_VALUES_COLLECTION].create_index(
            [("organization_id", 1), ("date_solde", 1), ("key", 1)],
            unique=True,
        )

        _indexes_created = True
    except Exception as e:
        # Logger l'erreur mais ne pas bloquer l'application
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Erreur lors de la création des index PCB: {e}")


def _gl_doc_to_public(doc) -> dict:
    """Convertit un document GL en dict public"""
    return {
        "id": str(doc["_id"]),
        "code": doc.get("code", ""),
        "libelle": doc.get("libelle", ""),
        "classe": doc.get("classe"),
        "sous_classe": doc.get("sous_classe"),
        "type": doc.get("type", ""),  # actif, passif, charge, produit
        "nature": doc.get("nature", ""),  # compte_synthese, compte_detail
        "organization_id": str(doc["organization_id"]) if doc.get("organization_id") else None,
        "solde": doc.get("solde", 0),
        "solde_debit": doc.get("solde_debit", 0),
        "solde_credit": doc.get("solde_credit", 0),
        "date_solde": doc.get("date_solde"),
        "devise": doc.get("devise", "XOF"),
        "is_active": doc.get("is_active", True),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


def _poste_doc_to_public(doc) -> dict:
    """Convertit un document poste réglementaire en dict public"""
    return {
        "id": str(doc["_id"]),
        "code": doc.get("code", ""),
        "libelle": doc.get("libelle", ""),
        "type": doc.get("type", ""),  # bilan_actif, bilan_passif, hors_bilan, cr_produit, cr_charge
        "niveau": doc.get("niveau", 1),
        "parent_id": str(doc["parent_id"]) if doc.get("parent_id") else None,
        "parent_code": doc.get("parent_code"),
        "contribution_signe": doc.get("contribution_signe", "+"),
        "organization_id": str(doc["organization_id"]) if doc.get("organization_id") else None,
        "ordre": doc.get("ordre", 0),
        "gl_codes": doc.get("gl_codes", []),  # Liste de {code: str, signe: str, basis: str}
        "calculation_mode": doc.get("calculation_mode", "gl"),
        "parents_formula": doc.get("parents_formula", []),
        "formule": doc.get("formule"),  # somme, difference, ratio, custom
        "formule_custom": doc.get("formule_custom"),  # Formule personnalisée
        "is_active": doc.get("is_active", True),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


def _report_doc_to_public(doc) -> dict:
    """Convertit un document de rapport en dict public"""
    return {
        "id": str(doc["_id"]),
        "organization_id": str(doc["organization_id"]) if doc.get("organization_id") else None,
        "type": doc.get("type", ""),  # bilan_reglementaire, hors_bilan, compte_resultat
        "section": doc.get("section"),
        "exercice": doc.get("exercice", ""),
        "date_cloture": doc.get("date_cloture"),
        "date_realisation": doc.get("date_realisation"),
        "date_debut": doc.get("date_debut"),
        "date_generation": doc.get("date_generation"),
        "modele_id": str(doc["modele_id"]) if doc.get("modele_id") else None,
        "structure": doc.get("structure", {}),  # Postes et totaux
        "ratios_bancaires": doc.get("ratios_bancaires", {}),
        "interpretation_ia": doc.get("interpretation_ia", ""),
        "statut": doc.get("statut", "generated"),  # generated, validated, error
        "created_at": doc.get("created_at"),
        "created_by": str(doc["created_by"]) if doc.get("created_by") else None,
    }


def _poste_exercice_value_doc_to_public(doc) -> dict:
    """Convertit un document de valeurs poste/exercice en dict public"""
    return {
        "id": str(doc["_id"]),
        "organization_id": str(doc["organization_id"]) if doc.get("organization_id") else None,
        "poste_id": str(doc["poste_id"]) if doc.get("poste_id") else None,
        "exercice": doc.get("exercice", ""),
        "n_1": doc.get("n_1"),
        "budget": doc.get("budget"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


def _ratio_variable_catalog_doc_to_public(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "organization_id": str(doc["organization_id"]) if doc.get("organization_id") else None,
        "key": doc.get("key", ""),
        "label": doc.get("label", ""),
        "unit": doc.get("unit", ""),
        "description": doc.get("description"),
        "is_active": doc.get("is_active", True),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


def _ratio_variable_value_doc_to_public(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "organization_id": str(doc["organization_id"]) if doc.get("organization_id") else None,
        "date_solde": doc.get("date_solde"),
        "key": doc.get("key", ""),
        "value": doc.get("value"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


# ========== COMPTES GL ==========

async def create_or_update_gl_account(gl_data: dict, organization_id: str) -> dict:
    """Crée ou met à jour un compte GL"""
    db = get_database()
    
    # Normaliser la date_solde pour qu'elle soit à minuit (00:00:00) pour éviter les problèmes de comparaison
    date_solde_raw = gl_data.get("date_solde")
    if date_solde_raw:
        if isinstance(date_solde_raw, datetime):
            # Normaliser à minuit (année, mois, jour uniquement) pour la comparaison
            date_solde_normalized = datetime(date_solde_raw.year, date_solde_raw.month, date_solde_raw.day)
        else:
            date_solde_normalized = date_solde_raw
    else:
        date_solde_normalized = None
    
    # Vérifier si le compte existe déjà (code + organization_id + date_solde)
    # Utiliser une plage de dates pour la recherche car les dates peuvent avoir des heures différentes
    query_existing = {
        "code": gl_data["code"],
        "organization_id": ObjectId(organization_id),
    }
    if date_solde_normalized:
        start_of_day = datetime(date_solde_normalized.year, date_solde_normalized.month, date_solde_normalized.day, 0, 0, 0)
        end_of_day = datetime(date_solde_normalized.year, date_solde_normalized.month, date_solde_normalized.day, 23, 59, 59, 999999)
        query_existing["date_solde"] = {"$gte": start_of_day, "$lte": end_of_day}
    
    existing = await db[PCB_GL_COLLECTION].find_one(query_existing)
    
    update_doc = {
        "code": gl_data["code"],
        "libelle": gl_data.get("libelle", ""),
        "classe": gl_data.get("classe"),
        "sous_classe": gl_data.get("sous_classe"),
        "type": gl_data.get("type", ""),
        "nature": gl_data.get("nature", "compte_detail"),
        "organization_id": ObjectId(organization_id),
        "solde_debit": gl_data.get("solde_debit", 0),
        "solde_credit": gl_data.get("solde_credit", 0),
        "date_solde": date_solde_normalized,
        "devise": gl_data.get("devise", "XOF"),
        "is_active": gl_data.get("is_active", True),
        "updated_at": datetime.utcnow(),
    }
    
    # Calculer le solde net
    solde_net = gl_data.get("solde_net")
    if solde_net is not None:
        update_doc["solde"] = solde_net
    else:
        update_doc["solde"] = update_doc["solde_credit"] - update_doc["solde_debit"]
    
    if existing:
        # Mise à jour
        await db[PCB_GL_COLLECTION].update_one(
            {"_id": existing["_id"]},
            {"$set": update_doc}
        )
        updated = await db[PCB_GL_COLLECTION].find_one({"_id": existing["_id"]})
        return _gl_doc_to_public(updated)
    else:
        # Création
        update_doc["created_at"] = datetime.utcnow()
        result = await db[PCB_GL_COLLECTION].insert_one(update_doc)
        new_doc = await db[PCB_GL_COLLECTION].find_one({"_id": result.inserted_id})
        return _gl_doc_to_public(new_doc)


async def get_gl_account_by_code(code: str, organization_id: str, date_solde: Optional[datetime] = None) -> Optional[dict]:
    """Récupère un compte GL par son code"""
    db = get_database()
    query = {
        "code": code,
        "organization_id": ObjectId(organization_id),
    }
    if date_solde:
        # Normaliser la date pour la comparaison (à minuit)
        if isinstance(date_solde, datetime):
            date_normalized = datetime(date_solde.year, date_solde.month, date_solde.day)
            # Rechercher avec une plage pour gérer les différences d'heure
            start_of_day = date_normalized
            end_of_day = datetime(date_normalized.year, date_normalized.month, date_normalized.day, 23, 59, 59)
            query["date_solde"] = {"$gte": start_of_day, "$lte": end_of_day}
        else:
            query["date_solde"] = date_solde
    
    doc = await db[PCB_GL_COLLECTION].find_one(query, sort=[("date_solde", -1)])
    if doc:
        return _gl_doc_to_public(doc)
    return None


# ========== CATALOGUE VARIABLES RATIOS + VALEURS PAR DATE ==========


async def list_ratio_variable_catalog(organization_id: str, include_inactive: bool = True) -> List[dict]:
    await ensure_pcb_indexes()
    db = get_database()

    query: Dict = {"organization_id": ObjectId(organization_id)}
    if not include_inactive:
        query["is_active"] = True

    items: List[dict] = []
    async for doc in db[PCB_RATIO_VARIABLE_CATALOG_COLLECTION].find(query).sort("key", 1):
        items.append(_ratio_variable_catalog_doc_to_public(doc))
    return items


async def create_ratio_variable_catalog_item(data: dict, organization_id: str) -> dict:
    await ensure_pcb_indexes()
    db = get_database()

    key = (data.get("key") or "").strip()
    if not key:
        raise ValueError("Clé variable invalide")

    existing = await db[PCB_RATIO_VARIABLE_CATALOG_COLLECTION].find_one(
        {"organization_id": ObjectId(organization_id), "key": key}
    )
    if existing:
        raise ValueError(f"Une variable avec la clé '{key}' existe déjà")

    now = datetime.utcnow()
    doc = {
        "organization_id": ObjectId(organization_id),
        "key": key,
        "label": (data.get("label") or "").strip(),
        "unit": (data.get("unit") or "").strip(),
        "description": data.get("description"),
        "is_active": bool(data.get("is_active", True)),
        "created_at": now,
        "updated_at": now,
    }
    result = await db[PCB_RATIO_VARIABLE_CATALOG_COLLECTION].insert_one(doc)
    new_doc = await db[PCB_RATIO_VARIABLE_CATALOG_COLLECTION].find_one({"_id": result.inserted_id})
    return _ratio_variable_catalog_doc_to_public(new_doc)


async def update_ratio_variable_catalog_item(item_id: str, update_data: dict, organization_id: str) -> dict:
    await ensure_pcb_indexes()
    db = get_database()

    update_doc = {k: v for k, v in (update_data or {}).items() if v is not None}
    if "key" in update_doc:
        update_doc["key"] = (update_doc.get("key") or "").strip()
        if not update_doc["key"]:
            raise ValueError("Clé variable invalide")

    if "label" in update_doc and isinstance(update_doc["label"], str):
        update_doc["label"] = update_doc["label"].strip()
    if "unit" in update_doc and isinstance(update_doc["unit"], str):
        update_doc["unit"] = update_doc["unit"].strip()

    update_doc["updated_at"] = datetime.utcnow()

    await db[PCB_RATIO_VARIABLE_CATALOG_COLLECTION].update_one(
        {"_id": ObjectId(item_id), "organization_id": ObjectId(organization_id)},
        {"$set": update_doc},
    )

    updated = await db[PCB_RATIO_VARIABLE_CATALOG_COLLECTION].find_one(
        {"_id": ObjectId(item_id), "organization_id": ObjectId(organization_id)}
    )
    if not updated:
        raise ValueError("Variable introuvable")
    return _ratio_variable_catalog_doc_to_public(updated)


async def delete_ratio_variable_catalog_item(item_id: str, organization_id: str) -> bool:
    await ensure_pcb_indexes()
    db = get_database()

    result = await db[PCB_RATIO_VARIABLE_CATALOG_COLLECTION].delete_one(
        {"_id": ObjectId(item_id), "organization_id": ObjectId(organization_id)}
    )
    return result.deleted_count > 0


async def get_ratio_variable_values_for_date(organization_id: str, date_solde: datetime) -> Dict[str, float]:
    """Retourne un dict key->value pour une date exacte (normalisée à minuit)."""
    await ensure_pcb_indexes()
    db = get_database()

    if isinstance(date_solde, datetime):
        date_norm = datetime(date_solde.year, date_solde.month, date_solde.day)
        start_of_day = datetime(date_norm.year, date_norm.month, date_norm.day, 0, 0, 0) - timedelta(hours=12)
        end_of_day = datetime(date_norm.year, date_norm.month, date_norm.day, 23, 59, 59, 999999) + timedelta(hours=12)
        query = {
            "organization_id": ObjectId(organization_id),
            "date_solde": {"$gte": start_of_day, "$lte": end_of_day},
        }
    else:
        query = {
            "organization_id": ObjectId(organization_id),
            "date_solde": date_solde,
        }

    out: Dict[str, float] = {}
    async for doc in db[PCB_RATIO_VARIABLE_VALUES_COLLECTION].find(query):
        key = doc.get("key")
        if not key:
            continue
        try:
            out[str(key)] = float(doc.get("value") or 0.0)
        except Exception:
            out[str(key)] = 0.0
    return out


async def list_ratio_variable_values_public(organization_id: str, date_solde: datetime) -> List[dict]:
    await ensure_pcb_indexes()
    db = get_database()

    if isinstance(date_solde, datetime):
        date_norm = datetime(date_solde.year, date_solde.month, date_solde.day)
        start_of_day = datetime(date_norm.year, date_norm.month, date_norm.day, 0, 0, 0) - timedelta(hours=12)
        end_of_day = datetime(date_norm.year, date_norm.month, date_norm.day, 23, 59, 59, 999999) + timedelta(hours=12)
        query = {"organization_id": ObjectId(organization_id), "date_solde": {"$gte": start_of_day, "$lte": end_of_day}}
    else:
        query = {"organization_id": ObjectId(organization_id), "date_solde": date_solde}
    items: List[dict] = []
    async for doc in db[PCB_RATIO_VARIABLE_VALUES_COLLECTION].find(query).sort("key", 1):
        items.append(_ratio_variable_value_doc_to_public(doc))
    return items


async def upsert_ratio_variable_value(organization_id: str, date_solde: datetime, key: str, value: float) -> dict:
    await ensure_pcb_indexes()
    db = get_database()

    key = (key or "").strip()
    if not key:
        raise ValueError("Clé variable invalide")

    date_norm = datetime(date_solde.year, date_solde.month, date_solde.day) if isinstance(date_solde, datetime) else date_solde

    now = datetime.utcnow()
    await db[PCB_RATIO_VARIABLE_VALUES_COLLECTION].update_one(
        {"organization_id": ObjectId(organization_id), "date_solde": date_norm, "key": key},
        {
            "$set": {"value": value, "updated_at": now},
            "$setOnInsert": {
                "organization_id": ObjectId(organization_id),
                "date_solde": date_norm,
                "key": key,
                "created_at": now,
            },
        },
        upsert=True,
    )

    doc = await db[PCB_RATIO_VARIABLE_VALUES_COLLECTION].find_one(
        {"organization_id": ObjectId(organization_id), "date_solde": date_norm, "key": key}
    )
    return _ratio_variable_value_doc_to_public(doc)


async def list_gl_accounts(organization_id: str, filters: Optional[dict] = None) -> List[dict]:
    """Liste les comptes GL d'une organisation"""
    db = get_database()
    query = {"organization_id": ObjectId(organization_id), "is_active": True}
    
    if filters:
        if filters.get("classe"):
            query["classe"] = filters["classe"]
        if filters.get("code"):
            query["code"] = {"$regex": filters["code"], "$options": "i"}
        if filters.get("date_solde"):
            # Normaliser la date pour la comparaison (à minuit)
            date_solde_filter = filters["date_solde"]
            if isinstance(date_solde_filter, datetime):
                # Extraire seulement la partie date (année, mois, jour)
                date_normalized = datetime(date_solde_filter.year, date_solde_filter.month, date_solde_filter.day)
                # Rechercher toutes les dates qui correspondent à cette date (peu importe l'heure)
                # Utiliser une plage pour capturer toutes les heures possibles, y compris avec décalage horaire
                # Commencer à minuit du jour précédent pour capturer les dates avec décalage horaire négatif (ex: 23:00:00 UTC = 00:00:00 UTC+1)
                start_of_day = datetime(date_normalized.year, date_normalized.month, date_normalized.day, 0, 0, 0) - timedelta(hours=12)
                # Aller jusqu'à minuit du lendemain pour capturer les dates avec décalage horaire positif
                end_of_day = datetime(date_normalized.year, date_normalized.month, date_normalized.day, 23, 59, 59, 999999) + timedelta(hours=12)
                query["date_solde"] = {"$gte": start_of_day, "$lte": end_of_day}
            else:
                query["date_solde"] = date_solde_filter
    
    # Debug: compter les documents avant filtrage pour comprendre le problème
    total_before = await db[PCB_GL_COLLECTION].count_documents({"organization_id": ObjectId(organization_id), "is_active": True})
    
    cursor = db[PCB_GL_COLLECTION].find(query).sort("code", 1)
    accounts = []
    async for doc in cursor:
        accounts.append(_gl_doc_to_public(doc))
    
    # Debug: logger pour comprendre pourquoi rien n'est trouvé
    if filters.get("date_solde") and len(accounts) == 0:
        # Essayer une recherche sans filtre de date pour voir combien de comptes existent
        query_no_date = {"organization_id": ObjectId(organization_id), "is_active": True}
        if filters.get("classe"):
            query_no_date["classe"] = filters["classe"]
        if filters.get("code"):
            query_no_date["code"] = {"$regex": filters["code"], "$options": "i"}
        count_no_date = await db[PCB_GL_COLLECTION].count_documents(query_no_date)
        # Récupérer quelques exemples de dates pour debug
        sample_docs = await db[PCB_GL_COLLECTION].find(query_no_date).limit(5).to_list(length=5)
        sample_dates = [doc.get("date_solde") for doc in sample_docs if doc.get("date_solde")]
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Recherche GL: {len(accounts)} trouvés avec date_solde={filters.get('date_solde')}, "
                      f"mais {count_no_date} sans filtre date. Dates d'exemple: {sample_dates}")
    
    return accounts


async def get_latest_gl_soldes(organization_id: str) -> List[dict]:
    """Récupère les soldes les plus récents pour chaque compte GL"""
    db = get_database()
    pipeline = [
        {"$match": {"organization_id": ObjectId(organization_id), "is_active": True}},
        {"$sort": {"code": 1, "date_solde": -1}},
        {"$group": {
            "_id": "$code",
            "latest": {"$first": "$$ROOT"}
        }},
        {"$replaceRoot": {"newRoot": "$latest"}},
        {"$sort": {"code": 1}}
    ]
    
    accounts = []
    async for doc in db[PCB_GL_COLLECTION].aggregate(pipeline):
        accounts.append(_gl_doc_to_public(doc))
    return accounts


async def get_available_solde_dates(organization_id: str) -> List[datetime]:
    """Récupère toutes les dates de solde disponibles pour une organisation"""
    db = get_database()
    pipeline = [
        {"$match": {"organization_id": ObjectId(organization_id), "is_active": True, "date_solde": {"$ne": None}}},
        {"$group": {"_id": "$date_solde"}},
        {"$sort": {"_id": -1}}
    ]
    
    dates = []
    seen_dates = set()  # Pour éviter les doublons dus aux différences d'heure
    async for doc in db[PCB_GL_COLLECTION].aggregate(pipeline):
        if doc.get("_id"):
            date_val = doc["_id"]
            # Normaliser la date à minuit pour éviter les doublons
            if isinstance(date_val, datetime):
                normalized = datetime(date_val.year, date_val.month, date_val.day)
                # Utiliser une clé basée sur la date normalisée pour éviter les doublons
                date_key = (normalized.year, normalized.month, normalized.day)
                if date_key not in seen_dates:
                    seen_dates.add(date_key)
                    dates.append(normalized)
            else:
                dates.append(date_val)
    
    # Trier par date décroissante
    dates.sort(reverse=True)
    return dates


async def delete_gl_accounts_by_date(organization_id: str, date_solde: datetime) -> int:
    """Supprime tous les comptes GL d'une organisation pour une date de solde donnée"""
    # S'assurer que les index sont créés pour optimiser la requête
    await ensure_pcb_indexes()
    
    db = get_database()
    
    # Normaliser la date pour la comparaison (à minuit)
    if isinstance(date_solde, datetime):
        date_normalized = datetime(date_solde.year, date_solde.month, date_solde.day)
        # Utiliser une plage de 24 heures exactement (de 00:00:00 à 23:59:59)
        # Les dates sont normalisées à minuit lors de la création, donc on cherche dans cette plage
        start_of_day = datetime(date_normalized.year, date_normalized.month, date_normalized.day, 0, 0, 0)
        end_of_day = datetime(date_normalized.year, date_normalized.month, date_normalized.day, 23, 59, 59, 999999)
        query = {
            "organization_id": ObjectId(organization_id),
            "date_solde": {"$gte": start_of_day, "$lte": end_of_day}
        }
    else:
        query = {
            "organization_id": ObjectId(organization_id),
            "date_solde": date_solde
        }
    
    # Utiliser delete_many avec un hint pour optimiser la requête
    # MongoDB utilisera l'index sur organization_id si disponible
    try:
        result = await db[PCB_GL_COLLECTION].delete_many(query)
        return result.deleted_count
    except Exception as e:
        # En cas d'erreur, logger et relancer
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erreur lors de la suppression des GL par date: {e}")
        raise


async def delete_all_gl_accounts(organization_id: str) -> int:
    """Supprime tous les comptes GL d'une organisation"""
    # S'assurer que les index sont créés pour optimiser la requête
    await ensure_pcb_indexes()
    
    db = get_database()
    
    result = await db[PCB_GL_COLLECTION].delete_many({
        "organization_id": ObjectId(organization_id)
    })
    
    return result.deleted_count


# ========== POSTES RÉGLEMENTAIRES ==========

async def create_poste_reglementaire(poste_data: dict, organization_id: str) -> dict:
    """Crée un poste réglementaire"""
    db = get_database()
    
    # Filtrer les GL vides et s'assurer que c'est une liste
    gl_codes = poste_data.get("gl_codes", [])
    if not isinstance(gl_codes, list):
        gl_codes = []
    # Filtrer les GL vides et ajouter basis par défaut si absent
    gl_codes_cleaned = []
    for gl in gl_codes:
        if gl and isinstance(gl, dict) and gl.get("code") and str(gl.get("code", "")).strip():
            gl_clean = {
                "code": str(gl.get("code", "")).strip(),
                "signe": gl.get("signe", "+"),
                "basis": gl.get("basis", "NET")  # Par défaut NET si absent
            }
            gl_codes_cleaned.append(gl_clean)
    gl_codes = gl_codes_cleaned

    parents_formula = poste_data.get("parents_formula", [])
    if not isinstance(parents_formula, list):
        parents_formula = []
    parents_formula_cleaned = []
    for term in parents_formula:
        if not term or not isinstance(term, dict):
            continue
        op = term.get("op")
        if op not in ["+", "-", "*", "/", "(", ")"]:
            continue

        # Parenthèses: token seul
        if op in ["(", ")"]:
            parents_formula_cleaned.append({"op": op})
            continue

        poste_id = str(term.get("poste_id", "")).strip()
        # Opérateur seul (ex: '/')
        if not poste_id:
            parents_formula_cleaned.append({"op": op})
            continue

        # Opérateur + poste
        parents_formula_cleaned.append({"poste_id": poste_id, "op": op})
    parents_formula = parents_formula_cleaned
    
    doc = {
        "code": poste_data["code"],
        "libelle": poste_data["libelle"],
        "type": poste_data["type"],
        "niveau": poste_data.get("niveau", 1),
        "parent_id": ObjectId(poste_data["parent_id"]) if poste_data.get("parent_id") else None,
        "parent_code": poste_data.get("parent_code"),
        "contribution_signe": poste_data.get("contribution_signe", "+") if poste_data.get("contribution_signe") in ["+", "-"] else "+",
        "organization_id": ObjectId(organization_id),
        "ordre": poste_data.get("ordre", 0),
        "gl_codes": gl_codes,
        "calculation_mode": poste_data.get("calculation_mode", "gl"),
        "parents_formula": parents_formula,
        "formule": poste_data.get("formule", "somme"),
        "formule_custom": poste_data.get("formule_custom"),
        "is_active": poste_data.get("is_active", True),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    
    result = await db[PCB_POSTES_COLLECTION].insert_one(doc)
    new_doc = await db[PCB_POSTES_COLLECTION].find_one({"_id": result.inserted_id})
    return _poste_doc_to_public(new_doc)


async def update_poste_reglementaire(poste_id: str, update_data: dict, organization_id: str) -> dict:
    """Met à jour un poste réglementaire"""
    db = get_database()
    
    try:
        poste_oid = ObjectId(poste_id)
    except Exception:
        raise ValueError("ID de poste invalide")
    
    # Vérifier que le poste appartient à l'organisation
    existing = await db[PCB_POSTES_COLLECTION].find_one({
        "_id": poste_oid,
        "organization_id": ObjectId(organization_id)
    })
    if not existing:
        raise ValueError("Poste introuvable ou accès non autorisé")

    update_doc = {}
    if "code" in update_data:
        update_doc["code"] = update_data["code"]
    if "libelle" in update_data:
        update_doc["libelle"] = update_data["libelle"]
    if "type" in update_data:
        update_doc["type"] = update_data["type"]
    if "niveau" in update_data:
        update_doc["niveau"] = update_data["niveau"]
    if "parent_id" in update_data:
        update_doc["parent_id"] = ObjectId(update_data["parent_id"]) if update_data["parent_id"] else None
    if "parent_code" in update_data:
        update_doc["parent_code"] = update_data["parent_code"]
    if "contribution_signe" in update_data:
        update_doc["contribution_signe"] = update_data.get("contribution_signe") if update_data.get("contribution_signe") in ["+", "-"] else "+"
    if "ordre" in update_data:
        update_doc["ordre"] = update_data["ordre"]
    if "gl_codes" in update_data:
        # Filtrer les GL vides et s'assurer que c'est une liste
        gl_codes = update_data["gl_codes"]
        if not isinstance(gl_codes, list):
            gl_codes = []
        # Filtrer les GL vides et ajouter basis par défaut si absent
        gl_codes_cleaned = []
        for gl in gl_codes:
            if gl and isinstance(gl, dict) and gl.get("code") and str(gl.get("code", "")).strip():
                gl_clean = {
                    "code": str(gl.get("code", "")).strip(),
                    "signe": gl.get("signe", "+"),
                    "basis": gl.get("basis", "NET")  # Par défaut NET si absent
                }
                gl_codes_cleaned.append(gl_clean)
        update_doc["gl_codes"] = gl_codes_cleaned
    if "calculation_mode" in update_data:
        update_doc["calculation_mode"] = update_data.get("calculation_mode")
    if "parents_formula" in update_data:
        parents_formula = update_data.get("parents_formula")
        if not isinstance(parents_formula, list):
            parents_formula = []
        parents_formula_cleaned = []
        for term in parents_formula:
            if not term or not isinstance(term, dict):
                continue
            op = term.get("op")
            if op not in ["+", "-", "*", "/", "(", ")"]:
                continue

            if op in ["(", ")"]:
                parents_formula_cleaned.append({"op": op})
                continue

            poste_id = str(term.get("poste_id", "")).strip()
            if not poste_id:
                parents_formula_cleaned.append({"op": op})
                continue

            parents_formula_cleaned.append({"poste_id": poste_id, "op": op})
        update_doc["parents_formula"] = parents_formula_cleaned
    if "formule" in update_data:
        update_doc["formule"] = update_data["formule"]
    if "formule_custom" in update_data:
        update_doc["formule_custom"] = update_data["formule_custom"]
    if "is_active" in update_data:
        update_doc["is_active"] = update_data["is_active"]
    
    update_doc["updated_at"] = datetime.utcnow()
    
    await db[PCB_POSTES_COLLECTION].update_one(
        {"_id": poste_oid},
        {"$set": update_doc}
    )
    
    updated = await db[PCB_POSTES_COLLECTION].find_one({"_id": poste_oid})
    return _poste_doc_to_public(updated)


async def list_postes_reglementaires(organization_id: str, filters: Optional[dict] = None) -> List[dict]:
    """Liste les postes réglementaires d'une organisation"""
    db = get_database()
    query = {"organization_id": ObjectId(organization_id), "is_active": True}
    
    if filters:
        if filters.get("type"):
            query["type"] = filters["type"]
        if filters.get("parent_id"):
            query["parent_id"] = ObjectId(filters["parent_id"]) if filters["parent_id"] else None
        if filters.get("parent_code"):
            query["parent_code"] = filters["parent_code"]
    
    cursor = db[PCB_POSTES_COLLECTION].find(query).sort([("ordre", 1), ("code", 1)])
    postes = []
    async for doc in cursor:
        postes.append(_poste_doc_to_public(doc))
    return postes


async def get_poste_by_id(poste_id: str, organization_id: str) -> Optional[dict]:
    """Récupère un poste par son ID"""
    db = get_database()
    try:
        poste_oid = ObjectId(poste_id)
    except Exception:
        return None
    
    doc = await db[PCB_POSTES_COLLECTION].find_one({
        "_id": poste_oid,
        "organization_id": ObjectId(organization_id)
    })
    if doc:
        return _poste_doc_to_public(doc)
    return None


async def delete_poste_reglementaire(poste_id: str, organization_id: str) -> bool:
    """Supprime (désactive) un poste réglementaire"""
    db = get_database()
    try:
        poste_oid = ObjectId(poste_id)
    except Exception:
        return False
    
    result = await db[PCB_POSTES_COLLECTION].update_one(
        {
            "_id": poste_oid,
            "organization_id": ObjectId(organization_id)
        },
        {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
    )
    return result.modified_count > 0


# ========== VALEURS POSTE PAR EXERCICE (N-1 / BUDGET) ==========

async def list_poste_exercice_values(
    organization_id: str,
    exercice: str,
    postes_ids: Optional[List[str]] = None,
) -> List[dict]:
    """Liste les valeurs N-1/Budget pour un exercice (optionnellement filtrées par postes)"""
    db = get_database()

    query: dict = {
        "organization_id": ObjectId(organization_id),
        "exercice": str(exercice),
    }
    if postes_ids:
        query["poste_id"] = {"$in": [ObjectId(pid) for pid in postes_ids]}

    cursor = db[PCB_POSTE_EXERCICE_VALUES_COLLECTION].find(query)
    items: List[dict] = []
    async for doc in cursor:
        items.append(_poste_exercice_value_doc_to_public(doc))
    return items


async def upsert_poste_exercice_value(
    organization_id: str,
    poste_id: str,
    exercice: str,
    n_1: Optional[float],
    budget: Optional[float],
) -> dict:
    """Crée ou met à jour la valeur N-1/Budget d'un poste pour un exercice"""
    db = get_database()
    try:
        poste_oid = ObjectId(poste_id)
    except Exception:
        raise ValueError("ID de poste invalide")

    now = datetime.utcnow()
    update_doc = {
        "organization_id": ObjectId(organization_id),
        "poste_id": poste_oid,
        "exercice": str(exercice),
        "n_1": n_1,
        "budget": budget,
        "updated_at": now,
    }

    await db[PCB_POSTE_EXERCICE_VALUES_COLLECTION].update_one(
        {
            "organization_id": ObjectId(organization_id),
            "poste_id": poste_oid,
            "exercice": str(exercice),
        },
        {
            "$set": update_doc,
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )

    doc = await db[PCB_POSTE_EXERCICE_VALUES_COLLECTION].find_one(
        {
            "organization_id": ObjectId(organization_id),
            "poste_id": poste_oid,
            "exercice": str(exercice),
        }
    )
    return _poste_exercice_value_doc_to_public(doc)


# ========== RAPPORTS ==========

async def create_report(report_data: dict, organization_id: str, user_id: str) -> dict:
    """Crée un rapport financier"""
    db = get_database()
    
    doc = {
        "organization_id": ObjectId(organization_id),
        "type": report_data["type"],
        "section": report_data.get("section"),
        "exercice": report_data.get("exercice", ""),
        "date_cloture": report_data.get("date_cloture"),
        "date_realisation": report_data.get("date_realisation"),
        "date_debut": report_data.get("date_debut"),
        "date_generation": datetime.utcnow(),
        "modele_id": ObjectId(report_data["modele_id"]) if report_data.get("modele_id") else None,
        "structure": report_data.get("structure", {}),
        "ratios_bancaires": report_data.get("ratios_bancaires", {}),
        "interpretation_ia": report_data.get("interpretation_ia", ""),
        "statut": report_data.get("statut", "generated"),
        "created_at": datetime.utcnow(),
        "created_by": ObjectId(user_id),
    }
    
    result = await db[PCB_REPORTS_COLLECTION].insert_one(doc)
    new_doc = await db[PCB_REPORTS_COLLECTION].find_one({"_id": result.inserted_id})
    return _report_doc_to_public(new_doc)


async def list_reports(organization_id: str, filters: Optional[dict] = None) -> List[dict]:
    """Liste les rapports d'une organisation"""
    db = get_database()
    query = {"organization_id": ObjectId(organization_id)}
    
    if filters:
        if filters.get("type"):
            query["type"] = filters["type"]
        if filters.get("exercice"):
            query["exercice"] = filters["exercice"]
        if filters.get("date_cloture"):
            query["date_cloture"] = filters["date_cloture"]
    
    cursor = db[PCB_REPORTS_COLLECTION].find(query).sort("date_generation", -1)
    reports = []
    async for doc in cursor:
        reports.append(_report_doc_to_public(doc))
    return reports


async def get_report_by_id(report_id: str, organization_id: str) -> Optional[dict]:
    """Récupère un rapport par son ID"""
    db = get_database()
    try:
        report_oid = ObjectId(report_id)
    except Exception:
        return None
    
    doc = await db[PCB_REPORTS_COLLECTION].find_one({
        "_id": report_oid,
        "organization_id": ObjectId(organization_id)
    })
    if doc:
        return _report_doc_to_public(doc)
    return None


async def delete_report(report_id: str, organization_id: str) -> bool:
    """Supprime un rapport par son ID (scopé à l'organisation)."""
    db = get_database()
    try:
        report_oid = ObjectId(report_id)
    except Exception:
        return False

    result = await db[PCB_REPORTS_COLLECTION].delete_one(
        {"_id": report_oid, "organization_id": ObjectId(organization_id)}
    )
    return result.deleted_count > 0

