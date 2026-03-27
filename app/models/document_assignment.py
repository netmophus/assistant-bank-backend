from datetime import datetime
from typing import Optional, List
from bson import ObjectId

from app.core.db import get_database

DOCUMENTS_ASSIGNMENTS_COLLECTION = "document_department_assignments"


async def assign_document_to_departments(document_id: str, department_ids: List[str], org_id: str) -> bool:
    """
    Affecte un document ORG à plusieurs départements.
    Valide que le document et tous les départements appartiennent à la même organisation.
    """
    db = get_database()
    try:
        document_oid = ObjectId(document_id)
        org_oid = ObjectId(org_id)
        dept_oids = [ObjectId(dept_id) for dept_id in department_ids]
    except Exception:
        return False
    
    # Vérifier que le document existe, appartient à l'organisation et est de scope ORG
    document_doc = await db["documents"].find_one({
        "_id": document_oid,
        "organization_id": org_oid,
        "scope": "ORG"
    })
    if not document_doc:
        raise ValueError("Document introuvable, n'appartient pas à votre organisation, ou n'est pas un document ORG.")
    
    # Vérifier que tous les départements appartiennent à la même organisation
    for dept_oid in dept_oids:
        dept_doc = await db["departments"].find_one({
            "_id": dept_oid,
            "organization_id": org_oid
        })
        if not dept_doc:
            raise ValueError(f"Département {str(dept_oid)} introuvable ou n'appartient pas à votre organisation.")
    
    # Supprimer les anciennes affectations
    await db[DOCUMENTS_ASSIGNMENTS_COLLECTION].delete_many({"document_id": document_oid})
    
    # Créer les nouvelles affectations
    assignments = [
        {
            "document_id": document_oid,
            "department_id": dept_oid,
            "created_at": datetime.utcnow(),
        }
        for dept_oid in dept_oids
    ]
    
    if assignments:
        await db[DOCUMENTS_ASSIGNMENTS_COLLECTION].insert_many(assignments)
    
    return True


async def get_departments_for_document(document_id: str) -> List[dict]:
    """Récupère les départements assignés à un document"""
    db = get_database()
    try:
        document_oid = ObjectId(document_id)
    except Exception:
        return []
    
    cursor = db[DOCUMENTS_ASSIGNMENTS_COLLECTION].find({"document_id": document_oid})
    assignments = []
    async for doc in cursor:
        # Récupérer les informations du département
        dept_doc = await db["departments"].find_one({"_id": doc["department_id"]})
        if dept_doc:
            assignments.append({
                "id": str(doc["department_id"]),
                "department_id": str(doc["department_id"]),
                "name": dept_doc.get("name", ""),
                "code": dept_doc.get("code", ""),
            })
        else:
            assignments.append({
                "id": str(doc["department_id"]),
                "department_id": str(doc["department_id"]),
                "name": "",
                "code": "",
            })
    return assignments


async def get_documents_for_department(department_id: str, organization_id: Optional[str] = None) -> List[dict]:
    """
    Récupère les documents ORG assignés à un département.
    Si organization_id est fourni, filtre également par organisation.
    """
    db = get_database()
    try:
        dept_oid = ObjectId(department_id)
    except Exception:
        return []
    
    # Récupérer les IDs des documents assignés
    cursor = db[DOCUMENTS_ASSIGNMENTS_COLLECTION].find({"department_id": dept_oid})
    document_ids = []
    async for doc in cursor:
        document_ids.append(doc["document_id"])
    
    if not document_ids:
        return []
    
    # Construire la requête pour récupérer les documents
    query = {
        "_id": {"$in": document_ids},
        "scope": "ORG"
    }
    
    # Filtrer par organisation si fourni
    if organization_id:
        try:
            org_oid = ObjectId(organization_id)
            query["organization_id"] = org_oid
        except Exception:
            pass
    
    # Récupérer les documents
    from app.models.documents import _document_doc_to_public
    cursor = db["documents"].find(query).sort("upload_date", -1)
    documents = []
    async for doc in cursor:
        document = _document_doc_to_public(doc)
        # Ajouter les départements assignés
        dept_assignments = await get_departments_for_document(str(doc["_id"]))
        document["departments"] = dept_assignments
        documents.append(document)
    
    return documents

