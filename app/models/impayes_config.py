from datetime import datetime
from typing import Optional
from bson import ObjectId
from app.core.db import get_database
from app.schemas.impayes_config import ImpayesConfig

IMPAYES_CONFIG_COLLECTION = "impayes_config"


def _config_doc_to_public(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "organization_id": str(doc["organization_id"]),
        "tranches_retard": doc.get("tranches_retard", []),
        "regle_restructuration": doc.get("regle_restructuration", {}),
        "modeles_sms": doc.get("modeles_sms", []),
        "parametres_techniques": doc.get("parametres_techniques", {}),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else datetime.utcnow().isoformat(),
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else datetime.utcnow().isoformat(),
    }


async def get_impayes_config(organization_id: str) -> Optional[dict]:
    """Récupère la configuration des impayés pour une organisation"""
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return None
    
    doc = await db[IMPAYES_CONFIG_COLLECTION].find_one({"organization_id": org_oid})
    
    if doc:
        config = _config_doc_to_public(doc)
        # Si aucun modèle SMS n'est configuré, créer des modèles par défaut
        if not config.get("modeles_sms") or len(config.get("modeles_sms", [])) == 0:
            from app.schemas.impayes_config import _get_default_modeles_sms
            default_modeles = _get_default_modeles_sms()
            # Convertir en dict pour MongoDB
            modeles_dict = [m.model_dump() for m in default_modeles]
            # Mettre à jour la config avec les modèles par défaut
            await db[IMPAYES_CONFIG_COLLECTION].update_one(
                {"organization_id": org_oid},
                {"$set": {"modeles_sms": modeles_dict, "updated_at": datetime.utcnow()}}
            )
            config["modeles_sms"] = modeles_dict
            print(f"[DEBUG] Modèles SMS par défaut créés pour l'organisation {organization_id}")
        return config
    
    return None


async def create_or_update_impayes_config(
    organization_id: str,
    config: ImpayesConfig
) -> dict:
    """Crée ou met à jour la configuration des impayés"""
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        raise ValueError("ID organisation invalide")
    
    config_data = config.model_dump()
    
    # Vérifier si une config existe déjà
    existing = await db[IMPAYES_CONFIG_COLLECTION].find_one({"organization_id": org_oid})
    
    if existing:
        # Mettre à jour
        await db[IMPAYES_CONFIG_COLLECTION].update_one(
            {"organization_id": org_oid},
            {
                "$set": {
                    "tranches_retard": config_data.get("tranches_retard", []),
                    "regle_restructuration": config_data.get("regle_restructuration", {}),
                    "modeles_sms": config_data.get("modeles_sms", []),
                    "parametres_techniques": config_data.get("parametres_techniques", {}),
                    "updated_at": datetime.utcnow(),
                }
            }
        )
        doc = await db[IMPAYES_CONFIG_COLLECTION].find_one({"organization_id": org_oid})
    else:
        # Créer
        doc = {
            "organization_id": org_oid,
            "tranches_retard": config_data.get("tranches_retard", []),
            "regle_restructuration": config_data.get("regle_restructuration", {}),
            "modeles_sms": config_data.get("modeles_sms", []),
            "parametres_techniques": config_data.get("parametres_techniques", {}),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await db[IMPAYES_CONFIG_COLLECTION].insert_one(doc)
        doc["_id"] = result.inserted_id
    
    return _config_doc_to_public(doc)

