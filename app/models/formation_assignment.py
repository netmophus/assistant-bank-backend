from datetime import datetime
from typing import Optional, List
from bson import ObjectId

from app.core.db import get_database

FORMATIONS_ASSIGNMENTS_COLLECTION = "formation_assignments"


async def assign_formation_to_departments(formation_id: str, department_ids: List[str], org_id: str) -> dict:
    """
    Affecte une formation à des départements.
    """
    db = get_database()
    
    try:
        formation_oid = ObjectId(formation_id)
        org_oid = ObjectId(org_id)
        dept_oids = [ObjectId(did) for did in department_ids]
    except Exception:
        raise ValueError("IDs invalides.")
    
    # Vérifier que la formation existe et appartient à l'organisation
    formation = await db["formations"].find_one({
        "_id": formation_oid,
        "organization_id": org_oid
    })
    if not formation:
        raise ValueError("Formation introuvable ou n'appartient pas à votre organisation.")
    
    # Vérifier que la formation est publiée
    if formation.get("status") != "published":
        raise ValueError("Seules les formations publiées peuvent être affectées aux départements.")
    
    # Supprimer les anciennes affectations pour cette formation
    await db[FORMATIONS_ASSIGNMENTS_COLLECTION].delete_many({
        "formation_id": formation_oid
    })
    
    # Créer les nouvelles affectations
    assignments = []
    for dept_oid in dept_oids:
        assignment = {
            "formation_id": formation_oid,
            "department_id": dept_oid,
            "organization_id": org_oid,
            "assigned_at": datetime.utcnow(),
        }
        assignments.append(assignment)
    
    if assignments:
        await db[FORMATIONS_ASSIGNMENTS_COLLECTION].insert_many(assignments)
    
    return {
        "formation_id": formation_id,
        "department_ids": department_ids,
        "assigned_count": len(assignments),
    }


async def get_formations_for_department(department_id: str) -> List[dict]:
    """
    Récupère toutes les formations affectées à un département.
    Retourne uniquement les IDs des formations (pour compatibilité).
    Pour obtenir les détails complets, utilisez get_formation_by_id avec chaque ID.
    """
    db = get_database()
    
    try:
        dept_oid = ObjectId(department_id)
    except Exception:
        return []
    
    # Récupérer les affectations
    assignments = []
    async for assignment in db[FORMATIONS_ASSIGNMENTS_COLLECTION].find({"department_id": dept_oid}):
        assignments.append(assignment)
    
    # Récupérer les IDs des formations
    formation_ids = [str(a["formation_id"]) for a in assignments]
    
    # Retourner une liste simple avec les IDs pour compatibilité
    return [{"id": fid} for fid in formation_ids]


async def get_departments_for_formation(formation_id: str) -> List[str]:
    """
    Récupère les IDs des départements auxquels une formation est affectée.
    """
    db = get_database()
    
    try:
        formation_oid = ObjectId(formation_id)
    except Exception:
        return []
    
    department_ids = []
    async for assignment in db[FORMATIONS_ASSIGNMENTS_COLLECTION].find({"formation_id": formation_oid}):
        department_ids.append(str(assignment["department_id"]))
    
    return department_ids

