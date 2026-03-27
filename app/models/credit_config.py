from datetime import datetime
from typing import Optional

from bson import ObjectId

from app.core.db import get_database

CREDIT_CONFIG_COLLECTION = "credit_config"


def _credit_config_doc_to_public(doc) -> dict:
    """Convertit un document MongoDB en dictionnaire public"""
    return {
        "id": str(doc["_id"]),
        "organization_id": str(doc["organization_id"]),
        "taux_interet_base": doc.get("taux_interet_base", 5.0),
        "taux_interet_premium": doc.get("taux_interet_premium", 3.5),
        "montant_max_credit": doc.get("montant_max_credit", 100000),
        "duree_max_mois": doc.get("duree_max_mois", 120),
        "apport_minimum_pct": doc.get("apport_minimum_pct", 20),
        "frais_dossier": doc.get("frais_dossier", 500),
        "assurance_obligatoire": doc.get("assurance_obligatoire", True),
        "taux_assurance": doc.get("taux_assurance", 0.5),
        "criteres_eligibilite": doc.get(
            "criteres_eligibilite",
            {
                "salaire_minimum": 2000,
                "anciennete_minimum_mois": 6,
                "age_maximum": 65,
                "taux_endettement_max": 33,
            },
        ),
        "created_at": doc.get("created_at").isoformat()
        if doc.get("created_at") and isinstance(doc.get("created_at"), datetime)
        else None,
        "updated_at": doc.get("updated_at").isoformat()
        if doc.get("updated_at") and isinstance(doc.get("updated_at"), datetime)
        else None,
    }


async def get_credit_config_by_org(org_id: str) -> Optional[dict]:
    """Récupère la configuration de crédit d'une organisation"""
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return None

    doc = await db[CREDIT_CONFIG_COLLECTION].find_one({"organization_id": org_oid})

    if doc:
        return _credit_config_doc_to_public(doc)
    return None


async def create_credit_config(org_id: str, config_data: dict) -> dict:
    """Crée une configuration de crédit pour une organisation"""
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        raise ValueError("ID d'organisation invalide")

    # Vérifier qu'il n'y a pas déjà une config pour cette org
    existing = await db[CREDIT_CONFIG_COLLECTION].find_one({"organization_id": org_oid})
    if existing:
        raise ValueError(
            "Une configuration de crédit existe déjà pour cette organisation"
        )

    doc = {
        "organization_id": org_oid,
        "taux_interet_base": config_data.get("taux_interet_base", 5.0),
        "taux_interet_premium": config_data.get("taux_interet_premium", 3.5),
        "montant_max_credit": config_data.get("montant_max_credit", 100000),
        "duree_max_mois": config_data.get("duree_max_mois", 120),
        "apport_minimum_pct": config_data.get("apport_minimum_pct", 20),
        "frais_dossier": config_data.get("frais_dossier", 500),
        "assurance_obligatoire": config_data.get("assurance_obligatoire", True),
        "taux_assurance": config_data.get("taux_assurance", 0.5),
        "criteres_eligibilite": config_data.get(
            "criteres_eligibilite",
            {
                "salaire_minimum": 2000,
                "anciennete_minimum_mois": 6,
                "age_maximum": 65,
                "taux_endettement_max": 33,
            },
        ),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = await db[CREDIT_CONFIG_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _credit_config_doc_to_public(doc)


async def update_credit_config(org_id: str, config_data: dict) -> Optional[dict]:
    """Met à jour la configuration de crédit d'une organisation"""
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return None

    update_doc = {
        "taux_interet_base": config_data.get("taux_interet_base"),
        "taux_interet_premium": config_data.get("taux_interet_premium"),
        "montant_max_credit": config_data.get("montant_max_credit"),
        "duree_max_mois": config_data.get("duree_max_mois"),
        "apport_minimum_pct": config_data.get("apport_minimum_pct"),
        "frais_dossier": config_data.get("frais_dossier"),
        "assurance_obligatoire": config_data.get("assurance_obligatoire"),
        "taux_assurance": config_data.get("taux_assurance"),
        "criteres_eligibilite": config_data.get("criteres_eligibilite"),
        "updated_at": datetime.utcnow(),
    }

    # Supprimer les valeurs None
    update_doc = {k: v for k, v in update_doc.items() if v is not None}

    result = await db[CREDIT_CONFIG_COLLECTION].update_one(
        {"organization_id": org_oid}, {"$set": update_doc}
    )

    if result.modified_count > 0:
        updated_doc = await db[CREDIT_CONFIG_COLLECTION].find_one(
            {"organization_id": org_oid}
        )
        if updated_doc:
            return _credit_config_doc_to_public(updated_doc)

    return None


async def get_credit_stats_by_org(org_id: str) -> dict:
    """Récupère les statistiques de crédit d'une organisation"""
    db = get_database()

    # Pour l'instant, retourner des statistiques mock
    # TODO: Implémenter avec de vraies données quand le module crédit sera complet
    return {
        "demandes_en_cours": 15,
        "credits_actifs": 42,
        "taux_approbation": 75.5,
        "montant_total_encours": 2500000.0,
        "encours_par_type": {
            "immobilier": 1800000.0,
            "consommation": 500000.0,
            "professionnel": 200000.0,
        },
        "evolution_mensuelle": {
            "janvier": 8,
            "fevrier": 12,
            "mars": 15,
            "avril": 18,
            "mai": 22,
            "juin": 25,
        },
    }


async def create_default_credit_config_for_org(org_id: str) -> dict:
    """Crée une configuration de crédit par défaut pour une nouvelle organisation"""
    default_config = {
        "taux_interet_base": 5.0,
        "taux_interet_premium": 3.5,
        "montant_max_credit": 100000,
        "duree_max_mois": 120,
        "apport_minimum_pct": 20,
        "frais_dossier": 500,
        "assurance_obligatoire": True,
        "taux_assurance": 0.5,
        "criteres_eligibilite": {
            "salaire_minimum": 2000,
            "anciennete_minimum_mois": 6,
            "age_maximum": 65,
            "taux_endettement_max": 33,
        },
    }

    return await create_credit_config(org_id, default_config)
