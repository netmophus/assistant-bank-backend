"""Accès DB (MongoDB) pour les formations.

Ce module contient la logique de persistance des formations dans MongoDB.

Modèle stocké (simplifié):
- formations:
  - titre, description, organization_id, status
  - modules[]:
    - _id, titre, ordre, chapitres[], questions_qcm[]
    - chapitres[]:
      - _id, titre, introduction, ordre, parties[], contenu_genere
      - parties[]:
        - _id, titre, contenu (prompt), ordre, contenu_genere

Note: le backend accepte des données partielles (brouillons) et reconstruit la
structure en générant des ObjectId et des champs `ordre`.
"""

from datetime import datetime
from typing import Optional, List
from bson import ObjectId

from app.core.db import get_database
from app.models.organization import get_organization_by_id

FORMATIONS_COLLECTION = "formations"


# -----------------------------------------------------------------------------
# Helpers: conversion "document Mongo" -> "objet public API"
# -----------------------------------------------------------------------------

def _formation_doc_to_public(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "titre": doc["titre"],
        "description": doc.get("description"),
        "organization_id": str(doc["organization_id"]),
        "status": doc.get("status", "draft"),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") and isinstance(doc.get("created_at"), datetime) else None,
    }


def _module_doc_to_public(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "titre": doc["titre"],
        "nombre_chapitres": doc.get("nombre_chapitres", 0),
        "ordre": doc.get("ordre", 0),
        "chapitres": [_chapitre_doc_to_public(ch) for ch in doc.get("chapitres", [])],
        "questions_qcm": doc.get("questions_qcm", []),
    }


def _chapitre_doc_to_public(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "titre": doc.get("titre", ""),
        "introduction": doc["introduction"],
        "nombre_parties": doc.get("nombre_parties", 0),
        "ordre": doc.get("ordre", 0),
        "parties": [_partie_doc_to_public(p) for p in doc.get("parties", [])],
        "contenu_genere": doc.get("contenu_genere"),
    }


def _partie_doc_to_public(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "titre": doc["titre"],
        "contenu": doc["contenu"],
        "ordre": doc.get("ordre", 0),
        "contenu_genere": doc.get("contenu_genere"),
    }


async def create_formation(formation_in: dict, org_id: str) -> dict:
    """
    Crée une formation avec sa structure complète (modules, chapitres, parties).

    Important:
    - Ce endpoint est utilisé aussi pour les brouillons, donc on tolère des champs
      vides (titres, chapitres/parties inexistants, etc.).
    - Les IDs (_id) des sous-documents sont générés ici.
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
    
    # Construire la structure complète (accepter les données partielles pour les brouillons)
    modules_data = []
    modules_list = formation_in.get("modules", [])
    
    # Debug: vérifier que les modules sont bien présents
    if not modules_list:
        print(f"ATTENTION: Aucun module dans formation_in: {formation_in}")
    
    for idx, module in enumerate(modules_list):
        # Vérifier que le module a au moins un titre ou des chapitres
        if not module.get("titre") and not module.get("chapitres"):
            print(f"Module {idx} ignoré car vide: {module}")
            continue
            
        chapitres_data = []
        chapitres_list = module.get("chapitres", [])
        
        for ch_idx, chapitre in enumerate(chapitres_list):
            parties_data = []
            parties_list = chapitre.get("parties", [])
            
            for p_idx, partie in enumerate(parties_list):
                # Accepter les parties même si elles sont incomplètes
                parties_data.append({
                    "_id": ObjectId(),
                    "titre": partie.get("titre", ""),
                    "contenu": partie.get("contenu", ""),
                    "ordre": p_idx + 1,
                })
            
            # Accepter les chapitres même s'ils sont incomplets (même sans parties)
            chapitres_data.append({
                "_id": ObjectId(),
                "titre": chapitre.get("titre", ""),
                "introduction": chapitre.get("introduction", ""),
                "nombre_parties": len(parties_data),
                "ordre": ch_idx + 1,
                "parties": parties_data,
                "contenu_genere": chapitre.get("contenu_genere"),
            })
        
        # Accepter les modules même s'ils sont incomplets (même sans chapitres)
        modules_data.append({
            "_id": ObjectId(),
            "titre": module.get("titre", ""),
            "nombre_chapitres": len(chapitres_data),
            "ordre": idx + 1,
            "chapitres": chapitres_data,
            "questions_qcm": module.get("questions_qcm", []),
        })
    
    print(f"Modules créés: {len(modules_data)} modules avec {sum(len(m.get('chapitres', [])) for m in modules_data)} chapitres")
    
    # Utiliser le statut fourni ou "draft" par défaut
    status = formation_in.get("status", "draft")
    
    doc = {
        "titre": formation_in.get("titre", ""),
        "description": formation_in.get("description"),
        "organization_id": org_oid,
        "status": status,
        "modules": modules_data,
        "created_at": datetime.utcnow(),
    }
    
    result = await db[FORMATIONS_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    
    formation_public = _formation_doc_to_public(doc)
    formation_public["modules"] = [_module_doc_to_public(m) for m in modules_data]
    formation_public["modules_count"] = len(modules_data)
    
    return formation_public


async def list_formations_by_org(org_id: str) -> List[dict]:
    """
    Liste toutes les formations d'une organisation.

    Retourne la structure "publique" (id en str) + modules/chapitres/parties.
    """
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return []
    
    cursor = db[FORMATIONS_COLLECTION].find({"organization_id": org_oid}).sort("created_at", -1)
    formations = []
    async for doc in cursor:
        formation = _formation_doc_to_public(doc)
        formation["modules"] = [_module_doc_to_public(m) for m in doc.get("modules", [])]
        formation["modules_count"] = len(doc.get("modules", []))
        formations.append(formation)
    return formations


async def get_formation_by_id(formation_id: str) -> Optional[dict]:
    """
    Récupère une formation complète par son ID.
    """
    db = get_database()
    try:
        formation_oid = ObjectId(formation_id)
    except Exception:
        return None
    
    doc = await db[FORMATIONS_COLLECTION].find_one({"_id": formation_oid})
    if not doc:
        return None
    
    formation = _formation_doc_to_public(doc)
    formation["modules"] = [_module_doc_to_public(m) for m in doc.get("modules", [])]
    formation["modules_count"] = len(doc.get("modules", []))
    
    return formation


async def update_formation(formation_id: str, update_data: dict, org_id: str) -> dict:
    """
    Met à jour une formation.

    Spécificité:
    - Si `modules` est fourni, on reconstruit la structure en essayant de
      préserver les ObjectId existants (pour stabiliser les références côté UI).
    """
    db = get_database()
    try:
        formation_oid = ObjectId(formation_id)
    except Exception:
        raise ValueError("formation_id invalide.")
    
    # Vérifier que la formation existe et appartient à l'organisation
    existing = await db[FORMATIONS_COLLECTION].find_one({
        "_id": formation_oid,
        "organization_id": ObjectId(org_id)
    })
    if not existing:
        raise ValueError("Formation introuvable ou n'appartient pas à votre organisation.")
    
    update_doc = {}
    if "titre" in update_data:
        update_doc["titre"] = update_data["titre"]
    if "description" in update_data:
        update_doc["description"] = update_data["description"]
    if "status" in update_data:
        update_doc["status"] = update_data["status"]
    
    # Si on met à jour les modules, reconstruire la structure en préservant les IDs existants
    if "modules" in update_data:
        # Récupérer la formation existante pour préserver les IDs
        existing_doc = await db[FORMATIONS_COLLECTION].find_one({"_id": formation_oid})
        existing_modules = existing_doc.get("modules", []) if existing_doc else []
        
        modules_data = []
        for idx, module in enumerate(update_data["modules"]):
            # Essayer de trouver le module existant par son ID ou par l'ordre
            existing_module = None
            if "id" in module:
                try:
                    module_oid = ObjectId(module["id"])
                    existing_module = next((m for m in existing_modules if m["_id"] == module_oid), None)
                except:
                    pass
            
            if not existing_module and idx < len(existing_modules):
                existing_module = existing_modules[idx]
            
            chapitres_data = []
            existing_chapitres = existing_module.get("chapitres", []) if existing_module else []
            
            for ch_idx, chapitre in enumerate(module.get("chapitres", [])):
                # Essayer de trouver le chapitre existant par son ID ou par l'ordre
                existing_chapitre = None
                if "id" in chapitre:
                    try:
                        chapitre_oid = ObjectId(chapitre["id"])
                        existing_chapitre = next((ch for ch in existing_chapitres if ch["_id"] == chapitre_oid), None)
                    except:
                        pass
                
                if not existing_chapitre and ch_idx < len(existing_chapitres):
                    existing_chapitre = existing_chapitres[ch_idx]
                
                parties_data = []
                existing_parties = existing_chapitre.get("parties", []) if existing_chapitre else []
                
                for p_idx, partie in enumerate(chapitre.get("parties", [])):
                    # Essayer de préserver l'ID de la partie existante
                    partie_id = ObjectId()
                    if p_idx < len(existing_parties):
                        partie_id = existing_parties[p_idx]["_id"]
                    
                    parties_data.append({
                        "_id": partie_id,
                        "titre": partie.get("titre", ""),
                        "contenu": partie.get("contenu", ""),
                        "ordre": p_idx + 1,
                    })
                
                # Préserver l'ID du chapitre existant ou créer un nouveau
                chapitre_id = ObjectId()
                if existing_chapitre:
                    chapitre_id = existing_chapitre["_id"]
                
                chapitres_data.append({
                    "_id": chapitre_id,
                    "titre": chapitre.get("titre", ""),
                    "introduction": chapitre.get("introduction", ""),
                    "nombre_parties": len(parties_data),
                    "ordre": ch_idx + 1,
                    "parties": parties_data,
                    "contenu_genere": chapitre.get("contenu_genere") or (existing_chapitre.get("contenu_genere") if existing_chapitre else None),
                })
            
            # Préserver l'ID du module existant ou créer un nouveau
            module_id = ObjectId()
            if existing_module:
                module_id = existing_module["_id"]
            
            modules_data.append({
                "_id": module_id,
                "titre": module.get("titre", ""),
                "nombre_chapitres": len(chapitres_data),
                "ordre": idx + 1,
                "chapitres": chapitres_data,
                "questions_qcm": module.get("questions_qcm") or (existing_module.get("questions_qcm", []) if existing_module else []),
            })
        update_doc["modules"] = modules_data
    
    update_doc["updated_at"] = datetime.utcnow()
    
    await db[FORMATIONS_COLLECTION].update_one(
        {"_id": formation_oid},
        {"$set": update_doc}
    )
    
    updated = await db[FORMATIONS_COLLECTION].find_one({"_id": formation_oid})
    formation = _formation_doc_to_public(updated)
    formation["modules"] = [_module_doc_to_public(m) for m in updated.get("modules", [])]
    formation["modules_count"] = len(updated.get("modules", []))
    
    return formation

