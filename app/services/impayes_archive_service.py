"""
Service pour l'archivage et la restauration des données d'impayés
"""
from typing import List, Optional, Dict
from datetime import datetime
import uuid
from bson import ObjectId
import logging

from app.core.db import get_database
from app.models.impayes import (
    ARREARS_SNAPSHOTS_COLLECTION,
    OUTBOUND_MESSAGES_COLLECTION,
    SMS_HISTORY_COLLECTION,
    get_available_dates_situation,
    get_statistiques_impayes,
)
from app.schemas.impayes_archive import (
    ArchiveMetadata,
    ArchiveCreate,
    ArchivePublic,
)

logger = logging.getLogger(__name__)

ARCHIVES_COLLECTION = "impayes_archives"
ARCHIVED_SNAPSHOTS_COLLECTION = "impayes_archived_snapshots"
ARCHIVED_MESSAGES_COLLECTION = "impayes_archived_messages"
ARCHIVED_SMS_HISTORY_COLLECTION = "impayes_archived_sms_history"


def _archive_doc_to_public(doc) -> dict:
    """Convertit un document MongoDB archive en format public"""
    return {
        "archive_id": doc.get("archive_id", ""),
        "organization_id": str(doc.get("organization_id", "")),
        "archived_by": str(doc.get("archived_by", "")),
        "archived_at": doc.get("archived_at").isoformat() if doc.get("archived_at") else None,
        "archive_name": doc.get("archive_name"),
        "archive_description": doc.get("archive_description"),
        "total_snapshots": doc.get("total_snapshots", 0),
        "total_messages": doc.get("total_messages", 0),
        "total_sms_history": doc.get("total_sms_history", 0),
        "date_situation_debut": doc.get("date_situation_debut"),
        "date_situation_fin": doc.get("date_situation_fin"),
        "dates_situation": doc.get("dates_situation", []),
        "montant_total_impaye": doc.get("montant_total_impaye", 0.0),
        "nombre_total_credits": doc.get("nombre_total_credits", 0),
        "candidats_restructuration": doc.get("candidats_restructuration", 0),
        "metadata": doc.get("metadata", {}),
    }


async def create_archive(
    organization_id: str,
    archived_by: str,
    archive_data: ArchiveCreate
) -> ArchivePublic:
    """
    Crée une archive des données actuelles d'impayés
    
    Cette fonction :
    1. Récupère tous les snapshots, messages et historique SMS actuels
    2. Les copie dans des collections d'archives avec un archive_id
    3. Crée une entrée de métadonnées dans la collection archives
    4. Retourne les métadonnées de l'archive créée
    
    Args:
        organization_id: ID de l'organisation
        archived_by: ID de l'utilisateur qui crée l'archive
        archive_data: Données de l'archive à créer
        
    Returns:
        Métadonnées de l'archive créée
    """
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
        user_oid = ObjectId(archived_by)
    except Exception as e:
        raise ValueError(f"ID invalide: {str(e)}")
    
    # Générer un ID unique pour cette archive
    archive_id = str(uuid.uuid4())
    archived_at = datetime.utcnow()
    
    logger.info(f"[ARCHIVE] Création de l'archive {archive_id} pour l'organisation {organization_id}")
    
    # Récupérer les dates de situation disponibles
    dates_situation = await get_available_dates_situation(organization_id)
    date_situation_debut = dates_situation[-1] if dates_situation else None  # Plus ancienne
    date_situation_fin = dates_situation[0] if dates_situation else None  # Plus récente
    
    # Initialiser les compteurs
    total_snapshots = 0
    total_messages = 0
    total_sms_history = 0
    montant_total_impaye = 0.0
    nombre_total_credits = 0
    candidats_restructuration = 0
    
    # 1. Archiver les snapshots
    if archive_data.include_snapshots:
        query_snapshots = {"organization_id": org_oid}
        snapshots = await db[ARREARS_SNAPSHOTS_COLLECTION].find(query_snapshots).to_list(length=None)
        
        if snapshots:
            archived_snapshots = []
            for snapshot in snapshots:
                # Ajouter l'archive_id au snapshot
                snapshot["archive_id"] = archive_id
                snapshot["archived_at"] = archived_at
                snapshot["_id"] = ObjectId()  # Nouvel ID pour l'archive
                archived_snapshots.append(snapshot)
                
                # Calculer les statistiques
                montant_total_impaye += snapshot.get("montant_total_impaye", 0)
                nombre_total_credits += 1
                if snapshot.get("candidat_restructuration", False):
                    candidats_restructuration += 1
            
            if archived_snapshots:
                await db[ARCHIVED_SNAPSHOTS_COLLECTION].insert_many(archived_snapshots)
                total_snapshots = len(archived_snapshots)
                logger.info(f"[ARCHIVE] {total_snapshots} snapshots archivés")
    
    # 2. Archiver les messages
    if archive_data.include_messages:
        query_messages = {"organization_id": org_oid}
        messages = await db[OUTBOUND_MESSAGES_COLLECTION].find(query_messages).to_list(length=None)
        
        if messages:
            archived_messages = []
            for message in messages:
                message["archive_id"] = archive_id
                message["archived_at"] = archived_at
                message["_id"] = ObjectId()
                archived_messages.append(message)
            
            if archived_messages:
                await db[ARCHIVED_MESSAGES_COLLECTION].insert_many(archived_messages)
                total_messages = len(archived_messages)
                logger.info(f"[ARCHIVE] {total_messages} messages archivés")
    
    # 3. Archiver l'historique SMS
    if archive_data.include_sms_history:
        query_sms_history = {"organization_id": org_oid}
        sms_history = await db[SMS_HISTORY_COLLECTION].find(query_sms_history).to_list(length=None)
        
        if sms_history:
            archived_sms_history = []
            for sms in sms_history:
                sms["archive_id"] = archive_id
                sms["archived_at"] = archived_at
                sms["_id"] = ObjectId()
                archived_sms_history.append(sms)
            
            if archived_sms_history:
                await db[ARCHIVED_SMS_HISTORY_COLLECTION].insert_many(archived_sms_history)
                total_sms_history = len(archived_sms_history)
                logger.info(f"[ARCHIVE] {total_sms_history} entrées d'historique SMS archivées")
    
    # 4. Créer l'entrée de métadonnées
    archive_metadata = {
        "_id": ObjectId(),
        "archive_id": archive_id,
        "organization_id": org_oid,
        "archived_by": user_oid,
        "archived_at": archived_at,
        "archive_name": archive_data.archive_name,
        "archive_description": archive_data.archive_description,
        "total_snapshots": total_snapshots,
        "total_messages": total_messages,
        "total_sms_history": total_sms_history,
        "date_situation_debut": date_situation_debut,
        "date_situation_fin": date_situation_fin,
        "dates_situation": dates_situation,
        "montant_total_impaye": montant_total_impaye,
        "nombre_total_credits": nombre_total_credits,
        "candidats_restructuration": candidats_restructuration,
        "metadata": {},
    }
    
    await db[ARCHIVES_COLLECTION].insert_one(archive_metadata)
    
    logger.info(f"[ARCHIVE] Archive {archive_id} créée avec succès")
    
    return ArchivePublic(**_archive_doc_to_public(archive_metadata))


async def list_archives(organization_id: str, limit: int = 100, skip: int = 0) -> List[ArchivePublic]:
    """
    Liste toutes les archives d'une organisation
    
    Args:
        organization_id: ID de l'organisation
        limit: Nombre maximum d'archives à retourner
        skip: Nombre d'archives à ignorer (pagination)
        
    Returns:
        Liste des archives
    """
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return []
    
    cursor = db[ARCHIVES_COLLECTION].find({"organization_id": org_oid}).sort("archived_at", -1).skip(skip).limit(limit)
    archives = await cursor.to_list(length=limit)
    
    return [ArchivePublic(**_archive_doc_to_public(arch)) for arch in archives]


async def get_archive(organization_id: str, archive_id: str) -> Optional[ArchivePublic]:
    """
    Récupère une archive spécifique
    
    Args:
        organization_id: ID de l'organisation
        archive_id: ID de l'archive
        
    Returns:
        Métadonnées de l'archive ou None si non trouvée
    """
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return None
    
    archive_doc = await db[ARCHIVES_COLLECTION].find_one({
        "archive_id": archive_id,
        "organization_id": org_oid
    })
    
    if not archive_doc:
        return None
    
    return ArchivePublic(**_archive_doc_to_public(archive_doc))


async def get_archived_snapshots(organization_id: str, archive_id: str, limit: int = 1000, skip: int = 0) -> List[dict]:
    """
    Récupère les snapshots d'une archive
    
    Args:
        organization_id: ID de l'organisation
        archive_id: ID de l'archive
        limit: Nombre maximum de snapshots à retourner
        skip: Nombre de snapshots à ignorer
        
    Returns:
        Liste des snapshots archivés
    """
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return []
    
    cursor = db[ARCHIVED_SNAPSHOTS_COLLECTION].find({
        "archive_id": archive_id,
        "organization_id": org_oid
    }).skip(skip).limit(limit)
    
    snapshots = await cursor.to_list(length=limit)
    
    # Convertir en format public (similaire à _snapshot_doc_to_public)
    from app.models.impayes import _snapshot_doc_to_public
    return [_snapshot_doc_to_public(s) for s in snapshots]


async def clear_current_data(organization_id: str, cleared_by: str) -> dict:
    """
    Vide toutes les données actuelles d'impayés (snapshots, messages, historique SMS)
    
    ATTENTION: Cette opération est irréversible. Assurez-vous d'avoir archivé les données avant.
    
    Args:
        organization_id: ID de l'organisation
        cleared_by: ID de l'utilisateur qui effectue la suppression
        
    Returns:
        Dictionnaire avec le nombre d'éléments supprimés
    """
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        raise ValueError("ID d'organisation invalide")
    
    logger.warning(f"[ARCHIVE] Suppression des données actuelles pour l'organisation {organization_id} par {cleared_by}")
    
    # Supprimer les snapshots
    result_snapshots = await db[ARREARS_SNAPSHOTS_COLLECTION].delete_many({"organization_id": org_oid})
    deleted_snapshots = result_snapshots.deleted_count
    
    # Supprimer les messages
    result_messages = await db[OUTBOUND_MESSAGES_COLLECTION].delete_many({"organization_id": org_oid})
    deleted_messages = result_messages.deleted_count
    
    # Supprimer l'historique SMS
    result_sms_history = await db[SMS_HISTORY_COLLECTION].delete_many({"organization_id": org_oid})
    deleted_sms_history = result_sms_history.deleted_count
    
    logger.info(f"[ARCHIVE] Données supprimées: {deleted_snapshots} snapshots, {deleted_messages} messages, {deleted_sms_history} SMS")
    
    return {
        "deleted_snapshots": deleted_snapshots,
        "deleted_messages": deleted_messages,
        "deleted_sms_history": deleted_sms_history,
        "cleared_at": datetime.utcnow().isoformat(),
        "cleared_by": cleared_by,
    }


async def restore_archive(
    organization_id: str,
    archive_id: str,
    restore_snapshots: bool = True,
    restore_messages: bool = True,
    restore_sms_history: bool = True,
    clear_existing: bool = False
) -> dict:
    """
    Restaure une archive (copie les données archivées vers les collections actuelles)
    
    Args:
        organization_id: ID de l'organisation
        archive_id: ID de l'archive à restaurer
        restore_snapshots: Restaurer les snapshots
        restore_messages: Restaurer les messages
        restore_sms_history: Restaurer l'historique SMS
        clear_existing: Vider les données existantes avant restauration
        
    Returns:
        Dictionnaire avec le nombre d'éléments restaurés
    """
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        raise ValueError("ID d'organisation invalide")
    
    # Vérifier que l'archive existe
    archive = await get_archive(organization_id, archive_id)
    if not archive:
        raise ValueError(f"Archive {archive_id} non trouvée")
    
    logger.info(f"[ARCHIVE] Restauration de l'archive {archive_id} pour l'organisation {organization_id}")
    
    # Vider les données existantes si demandé
    if clear_existing:
        await clear_current_data(organization_id, "system_restore")
    
    restored_snapshots = 0
    restored_messages = 0
    restored_sms_history = 0
    
    # Restaurer les snapshots
    if restore_snapshots:
        archived_snapshots = await db[ARCHIVED_SNAPSHOTS_COLLECTION].find({
            "archive_id": archive_id,
            "organization_id": org_oid
        }).to_list(length=None)
        
        if archived_snapshots:
            # Retirer les champs d'archivage et créer de nouveaux IDs
            snapshots_to_restore = []
            for snapshot in archived_snapshots:
                snapshot.pop("archive_id", None)
                snapshot.pop("archived_at", None)
                snapshot["_id"] = ObjectId()  # Nouvel ID
                snapshots_to_restore.append(snapshot)
            
            if snapshots_to_restore:
                await db[ARREARS_SNAPSHOTS_COLLECTION].insert_many(snapshots_to_restore)
                restored_snapshots = len(snapshots_to_restore)
                logger.info(f"[ARCHIVE] {restored_snapshots} snapshots restaurés")
    
    # Restaurer les messages
    if restore_messages:
        archived_messages = await db[ARCHIVED_MESSAGES_COLLECTION].find({
            "archive_id": archive_id,
            "organization_id": org_oid
        }).to_list(length=None)
        
        if archived_messages:
            messages_to_restore = []
            for message in archived_messages:
                message.pop("archive_id", None)
                message.pop("archived_at", None)
                message["_id"] = ObjectId()
                messages_to_restore.append(message)
            
            if messages_to_restore:
                await db[OUTBOUND_MESSAGES_COLLECTION].insert_many(messages_to_restore)
                restored_messages = len(messages_to_restore)
                logger.info(f"[ARCHIVE] {restored_messages} messages restaurés")
    
    # Restaurer l'historique SMS
    if restore_sms_history:
        archived_sms_history = await db[ARCHIVED_SMS_HISTORY_COLLECTION].find({
            "archive_id": archive_id,
            "organization_id": org_oid
        }).to_list(length=None)
        
        if archived_sms_history:
            sms_history_to_restore = []
            for sms in archived_sms_history:
                sms.pop("archive_id", None)
                sms.pop("archived_at", None)
                sms["_id"] = ObjectId()
                sms_history_to_restore.append(sms)
            
            if sms_history_to_restore:
                await db[SMS_HISTORY_COLLECTION].insert_many(sms_history_to_restore)
                restored_sms_history = len(sms_history_to_restore)
                logger.info(f"[ARCHIVE] {restored_sms_history} entrées d'historique SMS restaurées")
    
    logger.info(f"[ARCHIVE] Archive {archive_id} restaurée avec succès")
    
    return {
        "restored_snapshots": restored_snapshots,
        "restored_messages": restored_messages,
        "restored_sms_history": restored_sms_history,
        "restored_at": datetime.utcnow().isoformat(),
    }


