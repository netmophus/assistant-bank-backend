from datetime import datetime
from typing import List, Optional
from bson import ObjectId
import logging
import uuid
from app.core.db import get_database
from app.schemas.impayes import (
    ArrearsSnapshot,
    OutboundMessage,
    FiltresImpayes,
)

logger = logging.getLogger(__name__)

# Collections pour les archives
ARREARS_ARCHIVES_COLLECTION = "arrears_archives"
SMS_ARCHIVES_COLLECTION = "sms_archives"

# Collections fixes (évite la création d'une collection par archive)
ARREARS_ARCHIVED_SNAPSHOTS_COLLECTION = "arrears_archived_snapshots"
ARREARS_ARCHIVED_MESSAGES_COLLECTION = "sms_archived_messages"


async def create_archive_situation(
    organization_id: str,
    date_archive: str,  # Format YYYY-MM-DD
    created_by: str,
    commentaire: Optional[str] = None
) -> dict:
    """Crée une archive dans des collections fixes (archive_id) et vide les tables actuelles"""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        raise ValueError("organization_id invalide")
    
    # Valider le format de la date
    try:
        datetime.strptime(date_archive, "%Y-%m-%d")
    except ValueError:
        raise ValueError("date_archive doit être au format YYYY-MM-DD")
    
    # Vérifier s'il existe déjà des archives pour cette organisation
    existing_archives = await db[ARREARS_ARCHIVES_COLLECTION].find({
        "organization_id": org_oid
    }).to_list(length=100)
    
    # Ajouter un numéro si nécessaire (affichage)
    archive_number = len(existing_archives) + 1
    archive_display_name = f"{date_archive} (#{archive_number})" if archive_number > 1 else date_archive

    snapshots_archive_collection = ARREARS_ARCHIVED_SNAPSHOTS_COLLECTION
    messages_archive_collection = ARREARS_ARCHIVED_MESSAGES_COLLECTION

    archive_id = str(uuid.uuid4())
    archived_at = datetime.utcnow()
    
    # Récupérer TOUS les snapshots actuels
    snapshots_to_archive = await db[ARREARS_SNAPSHOTS_COLLECTION].find({
        "organization_id": org_oid
    }).to_list(length=10000)
    
    # Récupérer TOUS les messages actuels
    messages_to_archive = await db[OUTBOUND_MESSAGES_COLLECTION].find({
        "organization_id": org_oid
    }).to_list(length=10000)
    
    if not snapshots_to_archive and not messages_to_archive:
        raise ValueError("Aucune donnée à archiver")
    
    # Calculer les statistiques
    total_snapshots = len(snapshots_to_archive)
    total_messages = len(messages_to_archive)
    montant_total_impaye = sum(s.get("montant_total_impaye", 0) for s in snapshots_to_archive)
    credits_impayes = list(set(s["ref_credit"] for s in snapshots_to_archive))
    
    # Archiver vers des collections fixes (avec archive_id) puis vider les collections actives
    if snapshots_to_archive:
        for s in snapshots_to_archive:
            s["archive_id"] = archive_id
            s["archived_at"] = archived_at

        await db[snapshots_archive_collection].insert_many(snapshots_to_archive)
        # Vider la collection actuelle
        await db[ARREARS_SNAPSHOTS_COLLECTION].delete_many({
            "organization_id": org_oid
        })
    
    if messages_to_archive:
        for m in messages_to_archive:
            m["archive_id"] = archive_id
            m["archived_at"] = archived_at

        await db[messages_archive_collection].insert_many(messages_to_archive)
        # Vider la collection actuelle
        await db[OUTBOUND_MESSAGES_COLLECTION].delete_many({
            "organization_id": org_oid
        })
    
    # Créer un enregistrement de l'archive dans la collection des archives
    archive_doc = {
        "_id": ObjectId(),
        "archive_id": archive_id,
        "organization_id": org_oid,
        "date_archive": date_archive,
        "archive_display_name": archive_display_name,
        "archive_number": archive_number,
        "snapshots_collection": snapshots_archive_collection,
        "messages_collection": messages_archive_collection,
        "created_by": ObjectId(created_by),
        "created_at": datetime.utcnow(),
        "archived_at": archived_at,
        "total_snapshots": total_snapshots,
        "total_messages": total_messages,
        "montant_total_impaye": montant_total_impaye,
        "credits_impayes": credits_impayes,
        "commentaire": commentaire,
        "statut": "archivee"
    }
    
    await db[ARREARS_ARCHIVES_COLLECTION].insert_one(archive_doc)
    
    return {
        "archive_id": archive_id,
        "date_archive": date_archive,
        "archive_display_name": archive_display_name,
        "archive_number": archive_number,
        "snapshots_collection": snapshots_archive_collection,
        "messages_collection": messages_archive_collection,
        "total_snapshots": total_snapshots,
        "total_messages": total_messages,
        "montant_total_impaye": montant_total_impaye,
        "credits_archives": credits_impayes
    }


async def get_archives_by_organization(organization_id: str) -> List[dict]:
    """Récupère toutes les archives d'une organisation"""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return []
    
    cursor = db[ARREARS_ARCHIVES_COLLECTION].find(
        {"organization_id": org_oid}
    ).sort("archived_at", -1)
    
    archives = await cursor.to_list(length=100)
    
    # Convertir les ObjectId en strings
    for archive in archives:
        archive["_id"] = str(archive["_id"])
        archive["organization_id"] = str(archive["organization_id"])
        archive["created_by"] = str(archive["created_by"])
        archive["created_at"] = archive["created_at"].isoformat()
        archive["archived_at"] = archive["archived_at"].isoformat()
        
        # S'assurer que les champs nécessaires sont bien inclus
        if "credits_archives" not in archive:
            archive["credits_archives"] = []
        if "archive_display_name" not in archive:
            archive["archive_display_name"] = archive.get("date_archive", "Date inconnue")
        if "archive_number" not in archive:
            archive["archive_number"] = archive.get("archive_number", 1)
        if "snapshots_collection" not in archive:
            archive["snapshots_collection"] = "Collection inconnue"
        if "messages_collection" not in archive:
            archive["messages_collection"] = "Collection inconnue"
    
    return archives


async def initialize_new_situation(
    organization_id: str,
    new_periode_suivi: str,
    created_by: str
) -> dict:
    """Initialise une nouvelle situation (crée une période vide)"""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        raise ValueError("organization_id invalide")
    
    # Vérifier que la période n'existe pas déjà
    existing = await db[ARREARS_SNAPSHOTS_COLLECTION].find_one({
        "organization_id": org_oid,
        "periode_suivi": new_periode_suivi
    })
    
    if existing:
        return {
            "success": False,
            "message": f"La période {new_periode_suivi} existe déjà",
            "periode_suivi": new_periode_suivi
        }
    
    # La période est maintenant prête à recevoir de nouvelles données
    return {
        "success": True,
        "message": f"Nouvelle période {new_periode_suivi} initialisée avec succès",
        "periode_suivi": new_periode_suivi,
        "ready_for_import": True
    }


ARREARS_SNAPSHOTS_COLLECTION = "arrears_snapshots"
OUTBOUND_MESSAGES_COLLECTION = "outbound_messages"
SMS_HISTORY_COLLECTION = "sms_history"


def _snapshot_doc_to_public(doc) -> dict:
    """Convertit un document MongoDB snapshot en format public"""
    return {
        "id": str(doc["_id"]),
        "snapshot_id": doc.get("snapshot_id", ""),
        "organization_id": str(doc["organization_id"]),
        "date_situation": doc.get("date_situation", ""),
        "periode_suivi": doc.get("periode_suivi", ""),
        "batch_id": doc.get("batch_id", ""),
        "created_by": str(doc.get("created_by", "")),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        "ref_credit": doc.get("ref_credit", ""),
        "nom_client": doc.get("nom_client", ""),
        "telephone_client": doc.get("telephone_client"),
        "segment": doc.get("segment", ""),
        "agence": doc.get("agence", ""),
        "gestionnaire": doc.get("gestionnaire"),
        "produit": doc.get("produit", ""),
        "montant_initial": doc.get("montant_initial", 0),
        "encours_principal": doc.get("encours_principal", 0),
        "principal_impaye": doc.get("principal_impaye", 0),
        "interets_impayes": doc.get("interets_impayes", 0),
        "penalites_impayees": doc.get("penalites_impayees", 0),
        "montant_total_impaye": doc.get("montant_total_impaye", 0),
        "nb_echeances_impayees": doc.get("nb_echeances_impayees", 0),
        "jours_retard": doc.get("jours_retard", 0),
        "bucket_retard": doc.get("bucket_retard", ""),
        "ratio_impaye_encours": doc.get("ratio_impaye_encours", 0),
        "statut_reglementaire": doc.get("statut_reglementaire", ""),
        "candidat_restructuration": doc.get("candidat_restructuration", False),
        "garanties": doc.get("garanties"),
        "revenu_mensuel": str(doc.get("revenu_mensuel", "")) if doc.get("revenu_mensuel") else None,
        "commentaire": doc.get("commentaire"),
        # Champs de restructuration
        "statut_restructuration": doc.get("statut_restructuration"),
        "date_restructuration": doc.get("date_restructuration"),
        "commentaire_restructuration": doc.get("commentaire_restructuration"),
        "restructure_par": str(doc.get("restructure_par", "")) if doc.get("restructure_par") else None,
        "date_action_restructuration": doc.get("date_action_restructuration").isoformat() if doc.get("date_action_restructuration") else None,
    }


def _message_doc_to_public(doc) -> dict:
    """Convertit un document MongoDB message en format public"""
    return {
        "id": str(doc["_id"]),
        "message_id": doc.get("message_id", ""),
        "snapshot_id": doc.get("snapshot_id", ""),
        "periode_suivi": doc.get("periode_suivi", ""),
        "to": doc.get("to", ""),
        "body": doc.get("body", ""),
        "status": doc.get("status", "PENDING"),
        "linked_credit": doc.get("linked_credit", ""),
        "tranche_id": doc.get("tranche_id", ""),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        "sent_at": doc.get("sent_at").isoformat() if doc.get("sent_at") else None,
        "provider_message_id": doc.get("provider_message_id"),
        "error_message": doc.get("error_message"),
    }


async def check_existing_active_import(organization_id: str, date_situation: str) -> Optional[dict]:
    """Vérifie s'il existe déjà un import actif pour cette date"""
    db = get_database()
    
    existing_snapshots = await db[ARREARS_SNAPSHOTS_COLLECTION].find({
        "organization_id": ObjectId(organization_id),
        "date_situation": date_situation,
        "is_active": True
    }).to_list(length=1)
    
    if existing_snapshots:
        # Récupérer les informations sur l'import existant
        existing_batch_id = existing_snapshots[0].get("batch_id")
        existing_count = await db[ARREARS_SNAPSHOTS_COLLECTION].count_documents({
            "organization_id": ObjectId(organization_id),
            "date_situation": date_situation,
            "is_active": True,
            "batch_id": existing_batch_id
        })
        
        # Calculer le montant total
        total_montant = await db[ARREARS_SNAPSHOTS_COLLECTION].aggregate([
            {
                "$match": {
                    "organization_id": ObjectId(organization_id),
                    "date_situation": date_situation,
                    "is_active": True,
                    "batch_id": existing_batch_id
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_montant": {"$sum": "$montant_total_impaye"}
                }
            }
        ]).to_list(length=1)
        
        montant_total = total_montant[0]["total_montant"] if total_montant else 0
        
        return {
            "batch_id": existing_batch_id,
            "date_situation": date_situation,
            "total_credits": existing_count,
            "total_montant": montant_total,
            "created_at": existing_snapshots[0].get("created_at")
        }
    
    return None


async def deactivate_existing_import(organization_id: str, date_situation: str) -> int:
    """Désactive tous les snapshots actifs pour cette date"""
    db = get_database()
    
    result = await db[ARREARS_SNAPSHOTS_COLLECTION].update_many(
        {
            "organization_id": ObjectId(organization_id),
            "date_situation": date_situation,
            "is_active": True
        },
        {
            "$set": {"is_active": False}
        }
    )
    
    # Désactiver aussi les SMS non envoyés liés à cet ancien batch
    await db[OUTBOUND_MESSAGES_COLLECTION].update_many(
        {
            "organization_id": ObjectId(organization_id),
            "status": "PENDING"
        }
    )
    
    return result.modified_count


async def save_arrears_snapshot(snapshot: ArrearsSnapshot) -> dict:
    """Sauvegarde un snapshot d'impayés avec calcul automatique de periode_suivi et batch_id"""
    db = get_database()
    
    doc = snapshot.model_dump()
    doc["_id"] = ObjectId()
    doc["organization_id"] = ObjectId(doc["organization_id"])
    doc["created_by"] = ObjectId(doc["created_by"])
    doc["created_at"] = datetime.utcnow()
    doc["is_active"] = snapshot.is_active  # S'assurer que le champ is_active est bien sauvegardé
    
    # Calcul automatique de la période de suivi si non fournie
    if not doc.get("periode_suivi"):
        date_situation = doc.get("date_situation", "")
        if len(date_situation) >= 7:  # Format YYYY-MM-DD
            doc["periode_suivi"] = date_situation[:7]  # YYYY-MM
        else:
            raise ValueError("date_situation doit être au format YYYY-MM-DD")
    
    # Générer un batch_id unique si non fourni
    if not doc.get("batch_id"):
        import uuid
        doc["batch_id"] = f"batch_{datetime.utcnow().strftime('%Y_%m_%d')}_{str(uuid.uuid4())[:8]}"
    
    # Vérification d'unicité : (organization_id, batch_id, date_situation, ref_credit)
    existing = await db[ARREARS_SNAPSHOTS_COLLECTION].find_one({
        "organization_id": doc["organization_id"],
        "batch_id": doc["batch_id"],
        "date_situation": doc["date_situation"],
        "ref_credit": doc["ref_credit"]
    })
    
    if existing:
        # Optionnel : mettre à jour le document existant ou lever une erreur
        logging.warning(f"Snapshot déjà existant pour batch={doc['batch_id']}, date={doc['date_situation']}, ref={doc['ref_credit']}")
        return _snapshot_doc_to_public(existing)
    
    await db[ARREARS_SNAPSHOTS_COLLECTION].insert_one(doc)
    return _snapshot_doc_to_public(doc)


async def update_snapshot_restructuration(
    snapshot_id: str,
    organization_id: str,
    action: str,
    date_restructuration: Optional[str] = None,
    commentaire: Optional[str] = None,
    restructure_par: Optional[str] = None
) -> Optional[dict]:
    """
    Met à jour un snapshot avec une action de restructuration
    
    Args:
        snapshot_id: ID du snapshot (UUID)
        organization_id: ID de l'organisation
        action: Action à enregistrer ("restructure", "refuse", "douteux", "en_cours")
        date_restructuration: Date de restructuration (format YYYY-MM-DD)
        commentaire: Commentaire sur l'action
        restructure_par: ID de l'utilisateur qui a pris la décision
    
    Returns:
        Le snapshot mis à jour ou None si non trouvé
    """
    db = get_database()
    
    # Construire la requête de mise à jour
    update_data = {
        "statut_restructuration": action,
        "date_action_restructuration": datetime.utcnow(),
    }
    
    if date_restructuration:
        update_data["date_restructuration"] = date_restructuration
    
    if commentaire:
        update_data["commentaire_restructuration"] = commentaire
    
    if restructure_par:
        update_data["restructure_par"] = ObjectId(restructure_par)
    
    # Mettre à jour tous les snapshots avec ce snapshot_id pour cette organisation
    result = await db[ARREARS_SNAPSHOTS_COLLECTION].update_many(
        {
            "snapshot_id": snapshot_id,
            "organization_id": ObjectId(organization_id)
        },
        {
            "$set": update_data
        }
    )
    
    if result.matched_count == 0:
        return None
    
    # Récupérer le snapshot mis à jour
    updated_doc = await db[ARREARS_SNAPSHOTS_COLLECTION].find_one(
        {
            "snapshot_id": snapshot_id,
            "organization_id": ObjectId(organization_id)
        }
    )
    
    if updated_doc:
        return _snapshot_doc_to_public(updated_doc)
    
    return None


async def save_outbound_message(message: OutboundMessage) -> dict:
    """Sauvegarde un message SMS avec calcul automatique de periode_suivi"""
    db = get_database()
    
    doc = message.model_dump()
    doc["_id"] = ObjectId()
    doc["organization_id"] = ObjectId(doc["organization_id"])
    # snapshot_id reste une string (UUID), pas un ObjectId
    # doc["snapshot_id"] reste tel quel (string)
    doc["created_at"] = datetime.utcnow()
    
    # Calcul automatique de la période de suivi si non fournie
    if not doc.get("periode_suivi"):
        # Récupérer la période depuis le snapshot parent
        snapshot = await db[ARREARS_SNAPSHOTS_COLLECTION].find_one({
            "snapshot_id": doc["snapshot_id"],
            "organization_id": doc["organization_id"]
        })
        
        if snapshot and snapshot.get("periode_suivi"):
            doc["periode_suivi"] = snapshot["periode_suivi"]
        else:
            # Fallback : utiliser la date actuelle
            doc["periode_suivi"] = datetime.utcnow().strftime("%Y-%m")
    
    await db[OUTBOUND_MESSAGES_COLLECTION].insert_one(doc)
    return _message_doc_to_public(doc)


async def get_available_periodes_suivi(organization_id: str) -> dict:
    """Récupère les périodes de suivi disponibles et la période courante par organisation"""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return {
            "periodes": [],
            "periode_courante": datetime.utcnow().strftime("%Y-%m")
        }
    
    # Récupérer toutes les périodes distinctes pour cette organisation
    pipeline = [
        {"$match": {"organization_id": org_oid}},
        {"$group": {"_id": "$periode_suivi"}},
        {"$sort": {"_id": -1}},
        {"$project": {"_id": 0, "periode_suivi": "$_id"}}
    ]
    
    cursor = db[ARREARS_SNAPSHOTS_COLLECTION].aggregate(pipeline)
    periodes = []
    async for doc in cursor:
        if doc.get("periode_suivi"):
            periodes.append(doc["periode_suivi"])
    
    # Déterminer la période courante : dernière date_situation importée ou mois actuel
    periode_courante = datetime.utcnow().strftime("%Y-%m")  # défaut
    
    if periodes:
        # La période la plus récente est la première (tri descendant)
        periode_courante = periodes[0]
    else:
        # Vérifier s'il y a des snapshots sans periode_suivi (anciennes données)
        latest_snapshot = await db[ARREARS_SNAPSHOTS_COLLECTION].find_one(
            {"organization_id": org_oid},
            sort=[("date_situation", -1)]
        )
        
        if latest_snapshot and latest_snapshot.get("date_situation"):
            periode_courante = latest_snapshot["date_situation"][:7]
    
    return {
        "periodes": periodes,
        "periode_courante": periode_courante
    }


async def get_available_dates_situation(organization_id: str) -> List[str]:
    """Récupère la liste des dates de situation disponibles"""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return []
    
    # Récupérer toutes les dates de situation distinctes, triées par ordre décroissant
    pipeline = [
        {"$match": {"organization_id": org_oid}},
        {"$group": {"_id": "$date_situation"}},
        {"$sort": {"_id": -1}},
        {"$project": {"_id": 0, "date_situation": "$_id"}}
    ]
    
    cursor = db[ARREARS_SNAPSHOTS_COLLECTION].aggregate(pipeline)
    dates = []
    async for doc in cursor:
        if doc.get("date_situation"):
            dates.append(doc["date_situation"])
    
    return dates


async def count_snapshots_by_filters(
    organization_id: str,
    filtres: FiltresImpayes
) -> int:
    """Compte le nombre de snapshots selon les filtres"""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return 0
    
    query = {"organization_id": org_oid}
    
    if filtres.agence:
        query["agence"] = filtres.agence
    if filtres.segment:
        query["segment"] = filtres.segment
    if filtres.bucket_retard:
        query["bucket_retard"] = filtres.bucket_retard
    if filtres.statut_reglementaire:
        query["statut_reglementaire"] = filtres.statut_reglementaire
    if filtres.candidat_restructuration is not None:
        query["candidat_restructuration"] = filtres.candidat_restructuration
    if filtres.date_situation:
        query["date_situation"] = filtres.date_situation
    if filtres.periode_suivi:
        query["periode_suivi"] = filtres.periode_suivi
    
    count = await db[ARREARS_SNAPSHOTS_COLLECTION].count_documents(query)
    return count


async def get_snapshots_by_filters(
    organization_id: str,
    filtres: FiltresImpayes,
    limit: int = 100,
    skip: int = 0
) -> List[dict]:
    """Récupère les snapshots selon les filtres"""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return []
    
    query = {"organization_id": org_oid}
    
    if filtres.agence:
        query["agence"] = filtres.agence
    if filtres.segment:
        query["segment"] = filtres.segment
    if filtres.bucket_retard:
        query["bucket_retard"] = filtres.bucket_retard
    if filtres.statut_reglementaire:
        query["statut_reglementaire"] = filtres.statut_reglementaire
    if filtres.candidat_restructuration is not None:
        query["candidat_restructuration"] = filtres.candidat_restructuration
    if filtres.date_situation:
        query["date_situation"] = filtres.date_situation
    if filtres.periode_suivi:
        query["periode_suivi"] = filtres.periode_suivi
    
    cursor = db[ARREARS_SNAPSHOTS_COLLECTION].find(query).sort("created_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    
    return [_snapshot_doc_to_public(doc) for doc in docs]


async def get_statistiques_impayes(
    organization_id: str,
    date_situation: Optional[str] = None
) -> dict:
    """Calcule les statistiques des impayés"""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return {}
    
    query = {"organization_id": org_oid}
    if date_situation:
        query["date_situation"] = date_situation
    
    pipeline = [
        {"$match": query},
        {
            "$group": {
                "_id": None,
                "total_montant_impaye": {"$sum": "$montant_total_impaye"},
                "total_credits": {"$sum": 1},
                "total_encours": {"$sum": "$encours_principal"},
                "repartition_tranches": {
                    "$push": "$bucket_retard"
                },
                "repartition_segments": {
                    "$push": "$segment"
                },
                "repartition_agences": {
                    "$push": "$agence"
                },
                "repartition_produits": {
                    "$push": "$produit"
                },
                "candidats_restructuration": {
                    "$sum": {"$cond": ["$candidat_restructuration", 1, 0]}
                },
                "ratios_impaye_encours": {
                    "$push": "$ratio_impaye_encours"
                }
            }
        }
    ]
    
    result = await db[ARREARS_SNAPSHOTS_COLLECTION].aggregate(pipeline).to_list(length=1)
    
    if not result:
        return {
            "total_montant_impaye": 0,
            "total_credits": 0,
            "total_encours": 0,
            "repartition_tranches": {},
            "repartition_segments": {},
            "repartition_agences": {},
            "repartition_produits": {},
            "candidats_restructuration": 0,
            "ratio_impaye_encours_moyen": 0,
            "montant_moyen_par_credit": 0
        }
    
    data = result[0]
    
    # Compter les occurrences
    def count_occurrences(arr):
        counts = {}
        for item in arr:
            counts[item] = counts.get(item, 0) + 1
        return counts
    
    total_montant = data.get("total_montant_impaye", 0)
    total_credits = data.get("total_credits", 0)
    total_encours = data.get("total_encours", 0)
    
    # Calculer le ratio moyen comme ratio global (plus représentatif que la moyenne des ratios individuels)
    # Ratio global = (Total montant impayé / Total encours) * 100
    ratio_moyen = (total_montant / total_encours * 100) if total_encours > 0 else 0
    
    # Calculer le montant moyen par crédit
    montant_moyen = total_montant / total_credits if total_credits > 0 else 0
    
    return {
        "total_montant_impaye": total_montant,
        "total_credits": total_credits,
        "total_encours": total_encours,
        "repartition_tranches": count_occurrences(data.get("repartition_tranches", [])),
        "repartition_segments": count_occurrences(data.get("repartition_segments", [])),
        "repartition_agences": count_occurrences(data.get("repartition_agences", [])),
        "repartition_produits": count_occurrences(data.get("repartition_produits", [])),
        "candidats_restructuration": data.get("candidats_restructuration", 0),
        "ratio_impaye_encours_moyen": round(ratio_moyen, 2),
        "montant_moyen_par_credit": round(montant_moyen, 2)
    }


async def get_historique_statistiques(
    organization_id: str,
    limit: int = 12
) -> List[dict]:
    """Récupère l'historique des statistiques par date de situation (les plus récentes)"""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return []
    
    # Récupérer toutes les dates de situation distinctes
    pipeline_dates = [
        {"$match": {"organization_id": org_oid}},
        {"$group": {"_id": "$date_situation"}},
        {"$sort": {"_id": -1}},
        {"$limit": limit}
    ]
    
    cursor_dates = db[ARREARS_SNAPSHOTS_COLLECTION].aggregate(pipeline_dates)
    dates = []
    async for doc in cursor_dates:
        if doc.get("_id"):
            dates.append(doc["_id"])
    
    if not dates:
        return []
    
    # Pour chaque date, calculer les statistiques
    historique = []
    for date_sit in dates:
        stats = await get_statistiques_impayes(organization_id, date_sit)
        stats["date_situation"] = date_sit
        historique.append(stats)
    
    return historique


async def comparer_statistiques(
    organization_id: str,
    date_actuelle: str,
    date_precedente: Optional[str] = None
) -> dict:
    """Compare les statistiques entre deux dates et calcule l'évolution"""
    stats_actuelles = await get_statistiques_impayes(organization_id, date_actuelle)
    
    # Si pas de date précédente, chercher la date précédente disponible
    if not date_precedente:
        historique = await get_historique_statistiques(organization_id, limit=2)
        if len(historique) >= 2:
            # La première est la plus récente, la deuxième est la précédente
            date_precedente = historique[1].get("date_situation")
        elif len(historique) == 1:
            # Pas de date précédente disponible
            date_precedente = None
    
    if not date_precedente:
        return {
            "stats_actuelles": stats_actuelles,
            "stats_precedentes": None,
            "evolution": None,
            "tendance": "pas_de_comparaison",
            "couleur_tendance": "neutral",
            "icone_tendance": "equal"
        }
    
    stats_precedentes = await get_statistiques_impayes(organization_id, date_precedente)
    
    # Calculer l'évolution
    def calculer_evolution(actuel, precedent):
        if precedent == 0:
            return 100.0 if actuel > 0 else 0.0
        return ((actuel - precedent) / precedent) * 100
    
    def determiner_couleur_icone_evolution_avec_hex(pourcentage: float) -> dict:
        """Version avec codes hex pour comparer_statistiques - CONTRASTE MAXIMAL avec fond blanc"""
        if pourcentage is None or abs(pourcentage) < 0.1:
            # Stable : fond blanc opaque avec texte noir
            return {
                "couleur": "neutral-dark",
                "icone": "equal",
                "couleur_hex": "#000000",  # Noir pur pour contraste maximal
                "couleur_bg": "#ffffff",  # Fond blanc pur
                "avec_fond": True,
                "style_recommande": {
                    "backgroundColor": "#ffffff",
                    "color": "#000000",
                    "border": "4px solid #000000",
                    "padding": "10px 16px",
                    "borderRadius": "8px",
                    "fontWeight": "900",
                    "fontSize": "15px",
                    "display": "inline-block",
                    "boxShadow": "0 4px 8px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.5)",
                    "textShadow": "none",
                    "letterSpacing": "0.5px"
                }
            }
        
        if pourcentage < -5:
            # Baisse : fond blanc opaque avec texte noir et bordure verte épaisse
            return {
                "couleur": "success-dark",
                "icone": "arrow-down",
                "couleur_hex": "#000000",  # Noir pur pour contraste maximal
                "couleur_bg": "#ffffff",  # Fond blanc pur
                "avec_fond": True,
                "style_recommande": {
                    "backgroundColor": "#ffffff",
                    "color": "#000000",
                    "border": "4px solid #0d5132",  # Bordure verte épaisse
                    "padding": "10px 16px",
                    "borderRadius": "8px",
                    "fontWeight": "900",
                    "fontSize": "15px",
                    "display": "inline-block",
                    "boxShadow": "0 4px 8px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.5)",
                    "textShadow": "none",
                    "letterSpacing": "0.5px"
                }
            }
        elif pourcentage > 5:
            # Hausse : fond blanc opaque avec texte noir et bordure rouge épaisse
            return {
                "couleur": "danger-dark",
                "icone": "arrow-up",
                "couleur_hex": "#000000",  # Noir pur pour contraste maximal
                "couleur_bg": "#ffffff",  # Fond blanc pur
                "avec_fond": True,
                "style_recommande": {
                    "backgroundColor": "#ffffff",
                    "color": "#000000",
                    "border": "4px solid #8b0000",  # Bordure rouge épaisse
                    "padding": "10px 16px",
                    "borderRadius": "8px",
                    "fontWeight": "900",
                    "fontSize": "15px",
                    "display": "inline-block",
                    "boxShadow": "0 4px 8px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.5)",
                    "textShadow": "none",
                    "letterSpacing": "0.5px"
                }
            }
        else:
            # Variation faible : fond blanc opaque avec texte noir et bordure orange épaisse
            return {
                "couleur": "warning-dark",
                "icone": "equal",
                "couleur_hex": "#000000",  # Noir pur pour contraste maximal
                "couleur_bg": "#ffffff",  # Fond blanc pur
                "avec_fond": True,
                "style_recommande": {
                    "backgroundColor": "#ffffff",
                    "color": "#000000",
                    "border": "4px solid #8b6914",  # Bordure orange épaisse
                    "padding": "10px 16px",
                    "borderRadius": "8px",
                    "fontWeight": "900",
                    "fontSize": "15px",
                    "display": "inline-block",
                    "boxShadow": "0 4px 8px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.5)",
                    "textShadow": "none",
                    "letterSpacing": "0.5px"
                }
            }
    
    def determiner_couleur_icone_evolution(pourcentage: float) -> tuple:
        """
        Détermine la couleur et l'icône selon la variation
        Utilise des couleurs très contrastées et visibles
        Pour les impayés : baisse = succès (vert foncé), hausse = danger (rouge foncé)
        """
        if pourcentage is None or abs(pourcentage) < 0.1:
            return "neutral-dark", "equal"  # Gris foncé pour stable - très visible
        
        if pourcentage < -5:
            return "success-dark", "arrow-down"  # Baisse importante = vert foncé très visible
        elif pourcentage > 5:
            return "danger-dark", "arrow-up"  # Hausse importante = rouge foncé très visible
        else:
            return "warning-dark", "equal"  # Variation faible = orange foncé
    
    evolution = {
        "montant_impaye": {
            "valeur": stats_actuelles["total_montant_impaye"] - stats_precedentes["total_montant_impaye"],
            "pourcentage": calculer_evolution(
                stats_actuelles["total_montant_impaye"],
                stats_precedentes["total_montant_impaye"]
            )
        },
        "nombre_credits": {
            "valeur": stats_actuelles["total_credits"] - stats_precedentes["total_credits"],
            "pourcentage": calculer_evolution(
                stats_actuelles["total_credits"],
                stats_precedentes["total_credits"]
            )
        },
        "candidats_restructuration": {
            "valeur": stats_actuelles["candidats_restructuration"] - stats_precedentes["candidats_restructuration"],
            "pourcentage": calculer_evolution(
                stats_actuelles["candidats_restructuration"],
                stats_precedentes["candidats_restructuration"]
            )
        },
        "ratio_moyen": {
            "valeur": stats_actuelles.get("ratio_impaye_encours_moyen", 0) - stats_precedentes.get("ratio_impaye_encours_moyen", 0),
            "pourcentage": calculer_evolution(
                stats_actuelles.get("ratio_impaye_encours_moyen", 0),
                stats_precedentes.get("ratio_impaye_encours_moyen", 0)
            )
        }
    }
    
    # Ajouter couleurs et icônes aux indicateurs d'évolution avec codes hex et styles
    for key, indicateur in evolution.items():
        pourcentage = indicateur.get("pourcentage", 0)
        couleur_info = determiner_couleur_icone_evolution_avec_hex(pourcentage)
        indicateur["couleur"] = couleur_info["couleur"]
        indicateur["icone"] = couleur_info["icone"]
        indicateur["couleur_hex"] = couleur_info["couleur_hex"]
        indicateur["couleur_bg"] = couleur_info["couleur_bg"]
        indicateur["avec_fond"] = couleur_info["avec_fond"]
        indicateur["style_recommande"] = couleur_info["style_recommande"]
    
    # Déterminer la tendance globale
    tendance = "stable"
    # Déterminer couleur et icône pour la tendance globale avec codes hex
    pourcentage_montant = evolution["montant_impaye"]["pourcentage"]
    tendance_info = determiner_couleur_icone_evolution_avec_hex(pourcentage_montant)
    
    if pourcentage_montant > 5:
        tendance = "hausse"
    elif pourcentage_montant < -5:
        tendance = "baisse"
    else:
        tendance = "stable"
    
    couleur_tendance = tendance_info["couleur"]
    icone_tendance = tendance_info["icone"]
    
    return {
        "stats_actuelles": stats_actuelles,
        "stats_precedentes": stats_precedentes,
        "date_precedente": date_precedente,
        "evolution": evolution,
        "tendance": tendance,
        "couleur_tendance": couleur_tendance,
        "icone_tendance": icone_tendance
    }


async def get_pending_messages(organization_id: str) -> List[dict]:
    """Récupère les messages SMS en attente"""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        print(f"[DEBUG] get_pending_messages: organization_id invalide: {organization_id}")
        return []
    
    query = {
        "organization_id": org_oid,
        "status": "PENDING"
    }
    
    print(f"[DEBUG] get_pending_messages: recherche avec query: {query}")
    
    cursor = db[OUTBOUND_MESSAGES_COLLECTION].find(query).sort("created_at", 1)
    
    docs = await cursor.to_list(length=1000)
    print(f"[DEBUG] get_pending_messages: {len(docs)} messages trouvés")
    
    return [_message_doc_to_public(doc) for doc in docs]


async def count_all_messages(
    organization_id: str,
    status: Optional[str] = None
) -> int:
    """Compte le nombre total de messages SMS avec filtres optionnels"""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return 0
    
    query = {"organization_id": org_oid}
    if status:
        query["status"] = status
    
    count = await db[OUTBOUND_MESSAGES_COLLECTION].count_documents(query)
    return count


async def get_all_messages(
    organization_id: str,
    status: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
) -> List[dict]:
    """Récupère tous les messages SMS avec filtres optionnels"""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return []
    
    query = {"organization_id": org_oid}
    if status:
        query["status"] = status
    
    cursor = db[OUTBOUND_MESSAGES_COLLECTION].find(query).sort("created_at", -1).skip(skip).limit(limit)
    
    docs = await cursor.to_list(length=limit)
    return [_message_doc_to_public(doc) for doc in docs]


async def update_message_status(
    message_id: str,
    status: str,
    provider_message_id: Optional[str] = None,
    error_message: Optional[str] = None
):
    """Met à jour le statut d'un message"""
    db = get_database()
    
    sent_at = datetime.utcnow() if status == "SENT" else None
    
    update_data = {
        "status": status,
        "sent_at": sent_at
    }
    
    if provider_message_id:
        update_data["provider_message_id"] = provider_message_id
    if error_message:
        update_data["error_message"] = error_message
    
    await db[OUTBOUND_MESSAGES_COLLECTION].update_one(
        {"message_id": message_id},
        {"$set": update_data}
    )
    
    # Si le message est envoyé, créer une copie dans l'historique
    if status == "SENT":
        # Récupérer le message mis à jour
        updated_message = await db[OUTBOUND_MESSAGES_COLLECTION].find_one({"message_id": message_id})
        if updated_message:
            # Vérifier si l'historique n'existe pas déjà pour ce message
            existing_history = await db[SMS_HISTORY_COLLECTION].find_one({"message_id": message_id})
            if not existing_history:
                history_doc = updated_message.copy()
                history_doc["_id"] = ObjectId()
                history_doc["archived_at"] = datetime.utcnow()
                await db[SMS_HISTORY_COLLECTION].insert_one(history_doc)


async def delete_message(message_id: str, organization_id: str) -> bool:
    """Supprime un message SMS (ne supprime pas les SMS envoyés de outbound_messages, mais peut supprimer de l'historique)"""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return False
    
    # Vérifier si le message est envoyé - ne pas le supprimer de outbound_messages
    message = await db[OUTBOUND_MESSAGES_COLLECTION].find_one({
        "message_id": message_id,
        "organization_id": org_oid
    })
    
    if message and message.get("status") == "SENT":
        # Ne pas supprimer les SMS envoyés de outbound_messages, mais supprimer de l'historique si demandé
        # Supprimer de l'historique
        await db[SMS_HISTORY_COLLECTION].delete_one({
            "message_id": message_id,
            "organization_id": org_oid
        })
        return False
    
    result = await db[OUTBOUND_MESSAGES_COLLECTION].delete_one({
        "message_id": message_id,
        "organization_id": org_oid
    })
    
    return result.deleted_count > 0


async def delete_message_from_history(message_id: str, organization_id: str) -> bool:
    """Supprime un message SMS de l'historique uniquement"""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return False
    
    result = await db[SMS_HISTORY_COLLECTION].delete_one({
        "message_id": message_id,
        "organization_id": org_oid
    })
    
    return result.deleted_count > 0


async def delete_messages_from_history_bulk(message_ids: List[str], organization_id: str) -> int:
    """Supprime plusieurs messages SMS de l'historique"""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return 0
    
    result = await db[SMS_HISTORY_COLLECTION].delete_many({
        "message_id": {"$in": message_ids},
        "organization_id": org_oid
    })
    
    return result.deleted_count


async def delete_situation_by_date_situation(organization_id: str, date_situation: str) -> dict:
    """Supprime une situation importée (snapshots + SMS liés) pour une date_situation donnée"""
    db = get_database()

    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return {"snapshots_deleted": 0, "messages_deleted": 0, "history_deleted": 0}

    if not date_situation:
        return {"snapshots_deleted": 0, "messages_deleted": 0, "history_deleted": 0}

    # Récupérer les snapshot_id de cette date pour supprimer les SMS liés
    snapshot_ids = await db[ARREARS_SNAPSHOTS_COLLECTION].distinct(
        "snapshot_id",
        {"organization_id": org_oid, "date_situation": date_situation}
    )
    snapshot_ids = [sid for sid in snapshot_ids if sid]

    # Supprimer les snapshots
    snapshots_result = await db[ARREARS_SNAPSHOTS_COLLECTION].delete_many({
        "organization_id": org_oid,
        "date_situation": date_situation
    })

    messages_deleted = 0
    history_deleted = 0
    if snapshot_ids:
        messages_result = await db[OUTBOUND_MESSAGES_COLLECTION].delete_many({
            "organization_id": org_oid,
            "snapshot_id": {"$in": snapshot_ids}
        })
        messages_deleted = messages_result.deleted_count

        history_result = await db[SMS_HISTORY_COLLECTION].delete_many({
            "organization_id": org_oid,
            "snapshot_id": {"$in": snapshot_ids}
        })
        history_deleted = history_result.deleted_count

    return {
        "snapshots_deleted": snapshots_result.deleted_count,
        "messages_deleted": messages_deleted,
        "history_deleted": history_deleted,
    }


async def delete_all_messages_by_status(organization_id: str, status: Optional[str] = None) -> int:
    """Supprime tous les messages SMS selon le statut (ou tous si status=None)"""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return 0
    
    query = {"organization_id": org_oid}

    # Cas spécial: suppression totale (tous statuts) pour permettre une régénération complète
    if status == "ALL":
        outbound_result = await db[OUTBOUND_MESSAGES_COLLECTION].delete_many(query)
        history_result = await db[SMS_HISTORY_COLLECTION].delete_many(query)
        return outbound_result.deleted_count + history_result.deleted_count
    
    # Ne supprimer que les messages non envoyés (PENDING ou FAILED)
    # Les messages SENT ne doivent pas être supprimés de outbound_messages
    if status:
        if status == "SENT":
            # Pour les messages envoyés, on ne supprime que de l'historique
            result = await db[SMS_HISTORY_COLLECTION].delete_many({
                "organization_id": org_oid,
                "status": status
            })
            return result.deleted_count
        else:
            query["status"] = status
    else:
        # Si aucun statut spécifié, supprimer tous les messages non envoyés
        query["status"] = {"$in": ["PENDING", "FAILED"]}
    
    # Supprimer les messages de outbound_messages
    result = await db[OUTBOUND_MESSAGES_COLLECTION].delete_many(query)
    
    # Supprimer aussi de l'historique si nécessaire
    if status and status != "SENT":
        await db[SMS_HISTORY_COLLECTION].delete_many({
            "organization_id": org_oid,
            "status": status
        })
    
    return result.deleted_count


async def get_snapshots_by_filters(
    organization_id: str,
    filtres: dict,
    limit: int = 100,
    skip: int = 0,
    periode_suivi: Optional[str] = None  # Nouveau paramètre optionnel
) -> dict:
    """Récupère les snapshots actifs uniquement"""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return {"snapshots": [], "total": 0}
    
    # Construire la query avec le filtre is_active = True
    query = {
        "organization_id": org_oid,
        "is_active": True  # Uniquement les snapshots actifs
    }
    
    # Appliquer les filtres supplémentaires
    if filtres.date_situation:
        query["date_situation"] = filtres.date_situation
    if filtres.agence:
        query["agence"] = filtres.agence
    if filtres.segment:
        query["segment"] = filtres.segment
    if filtres.bucket_retard:
        query["bucket_retard"] = filtres.bucket_retard
    if filtres.candidat_restructuration is not None:
        query["candidat_restructuration"] = filtres.candidat_restructuration
    
    # Exécuter la requête sur la bonne collection
    cursor = db[ARREARS_SNAPSHOTS_COLLECTION].find(query).sort("created_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    snapshots = [_snapshot_doc_to_public(doc) for doc in docs]
    
    # Compter le total
    total = await db[ARREARS_SNAPSHOTS_COLLECTION].count_documents(query)
    
    return {
        "snapshots": snapshots,
        "total": total
    }


async def get_sms_history(
    organization_id: str,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
) -> List[dict]:
    """Récupère les SMS de l'historique avec filtres"""
    db = get_database()
    
    # Protection contre les valeurs None
    if limit is None:
        limit = 100
    if skip is None:
        skip = 0
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return []
    
    query = {"organization_id": org_oid}
    if status:
        query["status"] = status
    
    # Filtrer par date si fourni
    if start_date or end_date:
        date_query = {}
        if start_date:
            try:
                date_query["$gte"] = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            except:
                pass
        if end_date:
            try:
                date_query["$lte"] = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            except:
                pass
        if date_query:
            query["sent_at"] = date_query
    
    cursor = db[SMS_HISTORY_COLLECTION].find(query).sort("sent_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [_message_doc_to_public(doc) for doc in docs]


async def get_sms_history_count(organization_id: str) -> int:
    """Compte le nombre total de SMS dans l'historique"""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return 0
    
    query = {"organization_id": org_oid}
    
    try:
        total = await db[SMS_HISTORY_COLLECTION].count_documents(query)
        return total
    except Exception:
        return 0


async def comparer_situations_snapshots(
    organization_id: str,
    date_actuelle: str,
    date_precedente: Optional[str] = None
) -> dict:
    """
    Compare deux situations de snapshots basée sur ref_credit (logique métier)
    
    Cette fonction compare les snapshots actifs de deux dates de situation différentes
    en utilisant ref_credit comme clé de comparaison métier.
    
    Args:
        organization_id: ID de l'organisation
        date_actuelle: Date de situation actuelle (YYYY-MM-DD)
        date_precedente: Date de situation précédente (YYYY-MM-DD), si None cherche automatiquement
        
    Returns:
        dict: Résultat de comparaison avec les catégories métier
    """
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return {"error": "Organization ID invalide"}
    
    # Si pas de date précédente, chercher la date précédente disponible
    if not date_precedente:
        dates_disponibles = await get_available_dates_situation(org_oid)
        dates_triees = sorted([d for d in dates_disponibles if d < date_actuelle], reverse=True)
        if not dates_triees:
            return {
                "date_actuelle": date_actuelle,
                "date_precedente": None,
                "message": "Aucune date précédente disponible pour la comparaison",
                "resultats": {}
            }
        date_precedente = dates_triees[0]
    
    # Récupérer les snapshots actifs pour chaque date
    query_actuelle = {
        "organization_id": org_oid,
        "date_situation": date_actuelle,
        "is_active": True
    }
    
    query_precedente = {
        "organization_id": org_oid,
        "date_situation": date_precedente,
        "is_active": True
    }
    
    # Exécuter les requêtes en parallèle
    cursor_actuel = db[ARREARS_SNAPSHOTS_COLLECTION].find(query_actuelle)
    cursor_precedent = db[ARREARS_SNAPSHOTS_COLLECTION].find(query_precedente)
    
    snapshots_actuels = await cursor_actuel.to_list(length=None)
    snapshots_precedents = await cursor_precedent.to_list(length=None)
    
    # Créer des dictionnaires indexés par ref_credit pour lookup rapide
    dict_actuels = {snap["ref_credit"]: snap for snap in snapshots_actuels}
    dict_precedents = {snap["ref_credit"]: snap for snap in snapshots_precedents}
    
    # Initialiser les catégories de résultat
    resultats = {
        "regularises_totalement": [],      # Cas 1: présent avant, absent maintenant
        "regularises_partiellement": [],   # Cas 2: présent aux deux, baisse montant
        "stables": [],                     # Cas 3: présent aux deux, montant identique
        "aggrades": [],                    # Cas 4: présent aux deux, hausse montant
        "nouveaux_impayes": [],            # Cas 5: absent avant, présent maintenant
        "statistiques": {
            "total_actuel": len(snapshots_actuels),
            "total_precedent": len(snapshots_precedents),
            "montant_total_actuel": sum(snap.get("montant_total_impaye", 0) for snap in snapshots_actuels),
            "montant_total_precedent": sum(snap.get("montant_total_impaye", 0) for snap in snapshots_precedents),
        }
    }
    
    # Analyser chaque ref_credit
    tous_ref_credits = set(dict_actuels.keys()) | set(dict_precedents.keys())
    
    for ref_credit in tous_ref_credits:
        snap_actuel = dict_actuels.get(ref_credit)
        snap_precedent = dict_precedents.get(ref_credit)
        
        montant_actuel = snap_actuel.get("montant_total_impaye", 0) if snap_actuel else 0
        montant_precedent = snap_precedent.get("montant_total_impaye", 0) if snap_precedent else 0
        
        # Cas 1: Régularisé totalement (présent avant, absent maintenant)
        if snap_precedent and not snap_actuel:
            resultats["regularises_totalement"].append({
                "ref_credit": ref_credit,
                "montant_initial": montant_precedent,
                "montant_recupere": montant_precedent,
                "client": snap_precedent.get("client", ""),
                "agence": snap_precedent.get("agence", ""),
                "date_precedente": date_precedente
            })
        
        # Cas 5: Nouvel impayé (absent avant, présent maintenant)
        elif snap_actuel and not snap_precedent:
            resultats["nouveaux_impayes"].append({
                "ref_credit": ref_credit,
                "montant_impaye": montant_actuel,
                "client": snap_actuel.get("client", ""),
                "agence": snap_actuel.get("agence", ""),
                "jours_retard": snap_actuel.get("jours_retard", 0),
                "date_actuelle": date_actuelle
            })
        
        # Cas 2, 3, 4: Présent aux deux dates
        elif snap_actuel and snap_precedent:
            difference = montant_actuel - montant_precedent
            
            # Cas 2: Régularisé partiellement (baisse)
            if difference < 0:
                resultats["regularises_partiellement"].append({
                    "ref_credit": ref_credit,
                    "montant_precedent": montant_precedent,
                    "montant_actuel": montant_actuel,
                    "montant_recupere": -difference,  # positif
                    "pourcentage_recupere": (-difference / montant_precedent * 100) if montant_precedent > 0 else 0,
                    "client": snap_actuel.get("client", ""),
                    "agence": snap_actuel.get("agence", ""),
                    "evolution": "amelioration"
                })
            
            # Cas 3: Stable (montant identique ou variation faible < 1%)
            elif abs(difference) < (montant_precedent * 0.01):  # moins de 1% de variation
                resultats["stables"].append({
                    "ref_credit": ref_credit,
                    "montant": montant_actuel,
                    "difference": difference,
                    "client": snap_actuel.get("client", ""),
                    "agence": snap_actuel.get("agence", ""),
                    "jours_retard_precedent": snap_precedent.get("jours_retard", 0),
                    "jours_retard_actuel": snap_actuel.get("jours_retard", 0),
                    "evolution": "stable"
                })
            
            # Cas 4: Aggravé (hausse)
            else:
                resultats["aggrades"].append({
                    "ref_credit": ref_credit,
                    "montant_precedent": montant_precedent,
                    "montant_actuel": montant_actuel,
                    "montant_aggravation": difference,
                    "pourcentage_aggravation": (difference / montant_precedent * 100) if montant_precedent > 0 else 0,
                    "client": snap_actuel.get("client", ""),
                    "agence": snap_actuel.get("agence", ""),
                    "jours_retard_precedent": snap_precedent.get("jours_retard", 0),
                    "jours_retard_actuel": snap_actuel.get("jours_retard", 0),
                    "evolution": "aggravation"
                })
    
    # Calculer les statistiques finales
    stats = resultats["statistiques"]
    stats.update({
        "regularises_totalement": {
            "count": len(resultats["regularises_totalement"]),
            "montant_total_recupere": sum(item["montant_recupere"] for item in resultats["regularises_totalement"])
        },
        "regularises_partiellement": {
            "count": len(resultats["regularises_partiellement"]),
            "montant_total_recupere": sum(item["montant_recupere"] for item in resultats["regularises_partiellement"])
        },
        "stables": {
            "count": len(resultats["stables"]),
            "montant_total": sum(item["montant"] for item in resultats["stables"])
        },
        "aggrades": {
            "count": len(resultats["aggrades"]),
            "montant_total_aggravation": sum(item["montant_aggravation"] for item in resultats["aggrades"])
        },
        "nouveaux_impayes": {
            "count": len(resultats["nouveaux_impayes"]),
            "montant_total_nouveaux": sum(item["montant_impaye"] for item in resultats["nouveaux_impayes"])
        }
    })
    
    # Calculer le montant total récupéré
    montant_total_recupere = (
        stats["regularises_totalement"]["montant_total_recupere"] + 
        stats["regularises_partiellement"]["montant_total_recupere"]
    )
    
    stats["montant_total_recupere"] = montant_total_recupere
    stats["taux_recouvrement"] = (montant_total_recupere / stats["montant_total_precedent"] * 100) if stats["montant_total_precedent"] > 0 else 0
    
    # Calculer le bilan consolidé
    bilan = {
        "references": {
            "avant": stats["total_precedent"],
            "apres": stats["total_actuel"],
            "nouvelles": stats["nouveaux_impayes"]["count"],
            "disparues": stats["regularises_totalement"]["count"],
            "stables": stats["stables"]["count"],
            "evoluees": stats["regularises_partiellement"]["count"] + stats["aggrades"]["count"]
        },
        "montants": {
            "avant": stats["montant_total_precedent"],
            "apres": stats["montant_total_actuel"],
            "nouveaux": stats["nouveaux_impayes"]["montant_total_nouveaux"],
            "recuperes": stats["montant_total_recupere"],
            "aggraves": stats["aggrades"]["montant_total_aggravation"]
        },
        "taux": {
            "recouvrement": stats["taux_recouvrement"],
            "renouvellement_references": (stats["nouveaux_impayes"]["count"] / stats["total_actuel"] * 100) if stats["total_actuel"] > 0 else 0,
            "stabilite": (stats["stables"]["count"] / stats["total_precedent"] * 100) if stats["total_precedent"] > 0 else 0
        }
    }
    
    return {
        "date_actuelle": date_actuelle,
        "date_precedente": date_precedente,
        "resultats": resultats,
        "bilan": bilan,
        "periode_analyse": f"{date_precedente} → {date_actuelle}",
        "timestamp": datetime.utcnow().isoformat()
    }

async def detecter_regularisations_automatiques(
    organization_id: str,
    date_situation_debut: Optional[str] = None,
    date_situation_fin: Optional[str] = None
) -> List[dict]:
    """
    Détecte automatiquement les régularisations en comparant les snapshots entre différentes dates de situation.
    
    Logique :
    - Pour chaque crédit dans un snapshot à une date donnée
    - Chercher le même crédit dans un snapshot plus récent
    - Si le crédit n'existe plus OU si le montant_total_impaye a diminué → régularisation détectée
    """
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return []
    
    # Récupérer toutes les dates de situation disponibles, triées
    pipeline_dates = [
        {"$match": {"organization_id": org_oid}},
        {"$group": {"_id": "$date_situation"}},
        {"$sort": {"_id": 1}}  # Tri croissant pour comparer chronologiquement
    ]
    
    cursor_dates = db[ARREARS_SNAPSHOTS_COLLECTION].aggregate(pipeline_dates)
    dates_situation = []
    async for doc in cursor_dates:
        if doc.get("_id"):
            dates_situation.append(doc["_id"])
    
    logger.info(f"[REGULARISATIONS] Dates de situation trouvées: {dates_situation}")
    
    if len(dates_situation) < 2:
        # Pas assez de dates pour comparer
        logger.warning(f"[REGULARISATIONS] Pas assez de dates pour comparer ({len(dates_situation)} dates)")
        return []
    
    # Filtrer les dates si demandé
    if date_situation_debut:
        dates_situation = [d for d in dates_situation if d >= date_situation_debut]
    if date_situation_fin:
        dates_situation = [d for d in dates_situation if d <= date_situation_fin]
    
    logger.info(f"[REGULARISATIONS] Dates de situation après filtrage: {dates_situation}")
    
    if len(dates_situation) < 2:
        logger.warning(f"[REGULARISATIONS] Pas assez de dates après filtrage ({len(dates_situation)} dates)")
        return []
    
    regularisations_detectees = []
    
    # Comparer chaque date avec la suivante
    for i in range(len(dates_situation) - 1):
        date_actuelle = dates_situation[i]
        date_suivante = dates_situation[i + 1]
        
        # Récupérer les snapshots de la date actuelle
        snapshots_actuels = await db[ARREARS_SNAPSHOTS_COLLECTION].find({
            "organization_id": org_oid,
            "date_situation": date_actuelle
        }).to_list(length=10000)
        
        # Récupérer les snapshots de la date suivante
        snapshots_suivants = await db[ARREARS_SNAPSHOTS_COLLECTION].find({
            "organization_id": org_oid,
            "date_situation": date_suivante
        }).to_list(length=10000)
        
        logger.info(f"[REGULARISATIONS] Comparaison {date_actuelle} -> {date_suivante}: {len(snapshots_actuels)} snapshots actuels, {len(snapshots_suivants)} snapshots suivants")
        
        # Créer un mapping ref_credit -> snapshot pour la date suivante
        ref_credit_to_snapshot_suivant = {}
        for snap in snapshots_suivants:
            ref_credit = snap.get("ref_credit", "")
            if ref_credit:
                ref_credit_to_snapshot_suivant[ref_credit] = snap
        
        # Pour chaque snapshot actuel, vérifier s'il y a régularisation
        for snap_actuel in snapshots_actuels:
            ref_credit = snap_actuel.get("ref_credit", "")
            montant_impaye_actuel = snap_actuel.get("montant_total_impaye", 0)
            
            if not ref_credit or montant_impaye_actuel <= 0:
                continue
            
            # Vérifier si le crédit existe dans le snapshot suivant
            if ref_credit not in ref_credit_to_snapshot_suivant:
                # Le crédit n'existe plus → régularisation complète détectée
                logger.info(f"[REGULARISATIONS] Régularisation complète détectée: {ref_credit} - {montant_impaye_actuel} FCFA")
                date_creation = snap_actuel.get("created_at")
                if isinstance(date_creation, str):
                    try:
                        date_creation = datetime.fromisoformat(date_creation.replace("Z", "+00:00"))
                    except:
                        date_creation = datetime.utcnow()
                elif not isinstance(date_creation, datetime):
                    date_creation = datetime.utcnow()
                
                regularisations_detectees.append({
                    "ref_credit": ref_credit,
                    "snapshot_id": snap_actuel.get("snapshot_id", ""),
                    "montant_recupere": montant_impaye_actuel,
                    "date_regularisation": date_suivante,  # Date du snapshot suivant
                    "date_snapshot_initial": date_actuelle,
                    "date_snapshot_final": date_suivante,
                    "type": "complete"  # Régularisation complète
                })
            else:
                # Le crédit existe toujours, vérifier si le montant a diminué
                snap_suivant = ref_credit_to_snapshot_suivant[ref_credit]
                montant_impaye_suivant = snap_suivant.get("montant_total_impaye", 0)
                
                if montant_impaye_suivant < montant_impaye_actuel:
                    # Le montant a diminué → régularisation partielle détectée
                    montant_recupere = montant_impaye_actuel - montant_impaye_suivant
                    logger.info(f"[REGULARISATIONS] Régularisation partielle détectée: {ref_credit} - {montant_impaye_actuel} -> {montant_impaye_suivant} FCFA (récupéré: {montant_recupere} FCFA)")
                    
                    date_creation = snap_actuel.get("created_at")
                    if isinstance(date_creation, str):
                        try:
                            date_creation = datetime.fromisoformat(date_creation.replace("Z", "+00:00"))
                        except:
                            date_creation = datetime.utcnow()
                    elif not isinstance(date_creation, datetime):
                        date_creation = datetime.utcnow()
                    
                    regularisations_detectees.append({
                        "ref_credit": ref_credit,
                        "snapshot_id": snap_actuel.get("snapshot_id", ""),
                        "montant_recupere": montant_recupere,
                        "date_regularisation": date_suivante,
                        "date_snapshot_initial": date_actuelle,
                        "date_snapshot_final": date_suivante,
                        "type": "partielle"  # Régularisation partielle
                    })
    
    return regularisations_detectees


# ===================== Indicateurs de Performance =====================

async def calculer_indicateurs_recouvrement(
    organization_id: str,
    date_debut: Optional[str] = None,
    date_fin: Optional[str] = None,
    date_situation: Optional[str] = None
) -> dict:
    """
    Calcule les indicateurs de performance de recouvrement en comparant automatiquement les snapshots.
    
    Les régularisations sont détectées automatiquement en comparant les snapshots entre différentes dates de situation :
    - Si un crédit disparaît d'un snapshot à l'autre → régularisation complète
    - Si le montant impayé diminue → régularisation partielle
    
    Indicateurs calculés:
    - Taux de recouvrement (montant récupéré / montant impayé)
    - Délai moyen de recouvrement (jours)
    - Taux de réponse aux SMS (après envoi)
    - Efficacité par tranche de retard
    - Taux de régularisation après SMS
    """
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return {}
    
    # 1. Détecter les régularisations automatiquement en comparant les snapshots
    # IMPORTANT: On ignore date_situation pour la détection car on doit comparer entre différentes dates
    regularisations = await detecter_regularisations_automatiques(
        organization_id=organization_id,
        date_situation_debut=date_debut,
        date_situation_fin=date_fin
    )
    
    logger.info(f"[INDICATEURS] Régularisations détectées: {len(regularisations)}")
    for reg in regularisations[:5]:  # Afficher les 5 premières
        logger.info(f"[INDICATEURS] - {reg.get('ref_credit')}: {reg.get('montant_recupere')} FCFA ({reg.get('type')})")
    
    # 2. Récupérer les snapshots d'impayés pour la période analysée
    # Si date_situation est fourni, on l'utilise pour filtrer les snapshots initiaux
    # Sinon, on prend tous les snapshots pour calculer le montant total impayé
    query_snapshots = {"organization_id": org_oid}
    if date_situation:
        # Si on filtre par date_situation, on prend cette date comme référence
        query_snapshots["date_situation"] = date_situation
    elif date_debut or date_fin:
        # Sinon, on peut filtrer par plage de dates de situation
        if date_debut:
            query_snapshots["date_situation"] = {"$gte": date_debut}
        if date_fin:
            if "date_situation" in query_snapshots and isinstance(query_snapshots["date_situation"], dict):
                query_snapshots["date_situation"]["$lte"] = date_fin
            else:
                query_snapshots["date_situation"] = {"$lte": date_fin}
    
    snapshots = await db[ARREARS_SNAPSHOTS_COLLECTION].find(query_snapshots).to_list(length=10000)
    print(f"[DEBUG] Snapshots trouvés: {len(snapshots)}")
    
    if not snapshots:
        return {
            "taux_recouvrement": 0.0,
            "montant_total_impaye": 0.0,
            "montant_total_recupere": 0.0,
            "delai_moyen_recouvrement": None,
            "nombre_regularisations": 0,
            "taux_reponse_sms": 0.0,
            "nombre_sms_envoyes": 0,
            "nombre_reponses_sms": 0,
            "efficacite_par_tranche": {},
            "taux_regularisation_apres_sms": 0.0,
            "nombre_regularisations_apres_sms": 0,
            "nombre_sms_avec_regularisation": 0,
            "date_debut": date_debut,
            "date_fin": date_fin
        }
    
    # Créer un mapping ref_credit -> snapshot pour les calculs
    ref_credit_to_snapshot = {}
    for snap in snapshots:
        ref_credit = snap.get("ref_credit", "")
        if ref_credit:
            # Prendre le snapshot le plus récent pour chaque ref_credit
            if ref_credit not in ref_credit_to_snapshot:
                ref_credit_to_snapshot[ref_credit] = snap
            else:
                current_date = snap.get("created_at", "")
                existing_date = ref_credit_to_snapshot[ref_credit].get("created_at", "")
                if current_date > existing_date:
                    ref_credit_to_snapshot[ref_credit] = snap
    
    # Créer un mapping ref_credit -> régularisations
    regularisations_by_ref_credit = {}
    for reg in regularisations:
        ref_credit = reg.get("ref_credit", "")
        if ref_credit:
            if ref_credit not in regularisations_by_ref_credit:
                regularisations_by_ref_credit[ref_credit] = []
            regularisations_by_ref_credit[ref_credit].append(reg)
    
    # 3. Récupérer les SMS envoyés
    query_sms = {"organization_id": org_oid, "status": "SENT"}
    if date_debut or date_fin:
        date_query = {}
        if date_debut:
            try:
                date_query["$gte"] = datetime.fromisoformat(date_debut.replace("Z", "+00:00"))
            except:
                pass
        if date_fin:
            try:
                date_query["$lte"] = datetime.fromisoformat(date_fin.replace("Z", "+00:00"))
            except:
                pass
        if date_query:
            query_sms["sent_at"] = date_query
    
    sms_envoyes = await db[SMS_HISTORY_COLLECTION].find(query_sms).to_list(length=10000)
    
    # Créer un mapping ref_credit -> SMS (via linked_credit)
    sms_by_ref_credit = {}
    for sms in sms_envoyes:
        ref_credit = sms.get("linked_credit", "")
        if ref_credit:
            if ref_credit not in sms_by_ref_credit:
                sms_by_ref_credit[ref_credit] = []
            sms_by_ref_credit[ref_credit].append(sms)
    
    # 4. Calculer les indicateurs
    
    # Montants totaux
    # Pour le montant total impayé, on prend tous les snapshots de la première date de situation disponible
    # (ou tous les snapshots si pas de filtre par date_situation)
    if date_situation:
        # Si on filtre par date_situation, on utilise les snapshots de cette date
        montant_total_impaye = sum(s.get("montant_total_impaye", 0) for s in snapshots)
    else:
        # Sinon, on prend tous les snapshots de toutes les dates pour avoir le total
        # Mais pour être cohérent, on prend les snapshots de la première date de situation
        all_snapshots = await db[ARREARS_SNAPSHOTS_COLLECTION].find({"organization_id": org_oid}).to_list(length=10000)
        # Grouper par date_situation et prendre la première date
        snapshots_by_date = {}
        for snap in all_snapshots:
            date_sit = snap.get("date_situation", "")
            if date_sit:
                if date_sit not in snapshots_by_date:
                    snapshots_by_date[date_sit] = []
                snapshots_by_date[date_sit].append(snap)
        
        if snapshots_by_date:
            # Prendre la première date (la plus ancienne)
            first_date = sorted(snapshots_by_date.keys())[0]
            snapshots_first_date = snapshots_by_date[first_date]
            montant_total_impaye = sum(s.get("montant_total_impaye", 0) for s in snapshots_first_date)
            logger.info(f"[INDICATEURS] Montant total impayé calculé sur {len(snapshots_first_date)} snapshots de la date {first_date}")
        else:
            montant_total_impaye = sum(s.get("montant_total_impaye", 0) for s in snapshots)
    
    montant_total_recupere = sum(reg.get("montant_recupere", 0) for reg in regularisations)
    logger.info(f"[INDICATEURS] Montant total impayé: {montant_total_impaye} FCFA")
    logger.info(f"[INDICATEURS] Montant total récupéré: {montant_total_recupere} FCFA")
    logger.info(f"[INDICATEURS] Snapshots trouvés: {len(snapshots)}")
    
    # Taux de recouvrement
    taux_recouvrement = (montant_total_recupere / montant_total_impaye * 100) if montant_total_impaye > 0 else 0.0
    
    # Délai moyen de recouvrement
    delais_recouvrement = []
    for reg in regularisations:
        date_snapshot_initial = reg.get("date_snapshot_initial", "")
        date_regularisation = reg.get("date_regularisation", "")
        
        if date_snapshot_initial and date_regularisation:
            # Parser les dates (format YYYY-MM-DD)
            try:
                if isinstance(date_snapshot_initial, str):
                    date_init = datetime.strptime(date_snapshot_initial, "%Y-%m-%d")
                else:
                    continue
                
                if isinstance(date_regularisation, str):
                    date_reg = datetime.strptime(date_regularisation, "%Y-%m-%d")
                else:
                    continue
                
                delai = (date_reg - date_init).days
                if delai >= 0:
                    delais_recouvrement.append(delai)
            except:
                continue
    
    delai_moyen_recouvrement = sum(delais_recouvrement) / len(delais_recouvrement) if delais_recouvrement else None
    
    # Taux de réponse aux SMS
    nombre_sms_envoyes = len(sms_envoyes)
    nombre_reponses_sms = 0
    
    # Pour chaque SMS, vérifier s'il y a eu une régularisation après
    for sms in sms_envoyes:
        ref_credit = sms.get("linked_credit", "")
        sent_at = sms.get("sent_at")
        
        if ref_credit and sent_at:
            if isinstance(sent_at, str):
                try:
                    sent_at = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
                except:
                    continue
            elif not isinstance(sent_at, datetime):
                continue
            
            # Vérifier s'il y a une régularisation après l'envoi du SMS
            if ref_credit in regularisations_by_ref_credit:
                for reg in regularisations_by_ref_credit[ref_credit]:
                    date_reg_str = reg.get("date_regularisation", "")
                    if date_reg_str:
                        try:
                            date_reg = datetime.strptime(date_reg_str, "%Y-%m-%d")
                            if date_reg >= sent_at:
                                nombre_reponses_sms += 1
                                break
                        except:
                            continue
    
    taux_reponse_sms = (nombre_reponses_sms / nombre_sms_envoyes * 100) if nombre_sms_envoyes > 0 else 0.0
    
    # Efficacité par tranche de retard
    efficacite_par_tranche = {}
    tranches_credits = {}
    
    # Grouper les crédits par tranche (basé sur les snapshots initiaux)
    for reg in regularisations:
        ref_credit = reg.get("ref_credit", "")
        if ref_credit in ref_credit_to_snapshot:
            snapshot = ref_credit_to_snapshot[ref_credit]
            tranche = snapshot.get("bucket_retard", "Non défini")
            
            if tranche not in tranches_credits:
                tranches_credits[tranche] = {
                    "montant_impaye": 0.0,
                    "montant_recupere": 0.0,
                    "nombre": 0
                }
            
            # Utiliser le montant du snapshot initial
            montant_impaye_initial = snapshot.get("montant_total_impaye", 0)
            tranches_credits[tranche]["montant_impaye"] += montant_impaye_initial
            tranches_credits[tranche]["montant_recupere"] += reg.get("montant_recupere", 0)
            tranches_credits[tranche]["nombre"] += 1
    
    # Calculer l'efficacité par tranche
    for tranche, data in tranches_credits.items():
        montant_impaye = data["montant_impaye"]
        montant_recupere = data["montant_recupere"]
        taux = (montant_recupere / montant_impaye * 100) if montant_impaye > 0 else 0.0
        efficacite_par_tranche[tranche] = {
            "taux_recouvrement": round(taux, 2),
            "nombre": data["nombre"],
            "montant_impaye": round(montant_impaye, 2),
            "montant_recupere": round(montant_recupere, 2)
        }
    
    # Taux de régularisation après SMS
    nombre_regularisations_apres_sms = 0
    nombre_sms_avec_regularisation = 0
    
    for sms in sms_envoyes:
        ref_credit = sms.get("linked_credit", "")
        sent_at = sms.get("sent_at")
        
        if ref_credit and sent_at:
            if isinstance(sent_at, str):
                try:
                    sent_at = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
                except:
                    continue
            elif not isinstance(sent_at, datetime):
                continue
            
            # Vérifier s'il y a une régularisation après l'envoi du SMS
            if ref_credit in regularisations_by_ref_credit:
                for reg in regularisations_by_ref_credit[ref_credit]:
                    date_reg_str = reg.get("date_regularisation", "")
                    if date_reg_str:
                        try:
                            date_reg = datetime.strptime(date_reg_str, "%Y-%m-%d")
                            if date_reg >= sent_at:
                                nombre_regularisations_apres_sms += 1
                                nombre_sms_avec_regularisation += 1
                                break
                        except:
                            continue
    
    taux_regularisation_apres_sms = (nombre_sms_avec_regularisation / nombre_sms_envoyes * 100) if nombre_sms_envoyes > 0 else 0.0
    
    return {
        "taux_recouvrement": round(taux_recouvrement, 2),
        "montant_total_impaye": round(montant_total_impaye, 2),
        "montant_total_recupere": round(montant_total_recupere, 2),
        "delai_moyen_recouvrement": round(delai_moyen_recouvrement, 2) if delai_moyen_recouvrement is not None else None,
        "nombre_regularisations": len(regularisations),
        "taux_reponse_sms": round(taux_reponse_sms, 2),
        "nombre_sms_envoyes": nombre_sms_envoyes,
        "nombre_reponses_sms": nombre_reponses_sms,
        "efficacite_par_tranche": efficacite_par_tranche,
        "taux_regularisation_apres_sms": round(taux_regularisation_apres_sms, 2),
        "nombre_regularisations_apres_sms": nombre_regularisations_apres_sms,
        "nombre_sms_avec_regularisation": nombre_sms_avec_regularisation,
        "date_debut": date_debut,
        "date_fin": date_fin
    }


# ===================== Tableau de bord détaillé =====================

async def get_dashboard_detaille(
    organization_id: str,
    date_situation: Optional[str] = None
) -> dict:
    """
    Calcule un tableau de bord très détaillé avec toutes les métriques possibles
    """
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return {}
    
    # Récupérer les dates disponibles
    dates_disponibles = await get_available_dates_situation(organization_id)
    date_actuelle = date_situation or (dates_disponibles[0] if dates_disponibles else None)
    date_precedente = dates_disponibles[1] if len(dates_disponibles) >= 2 else None
    
    # Récupérer les snapshots ACTIFS pour la date actuelle
    query = {
        "organization_id": org_oid,
        "is_active": True  # Uniquement les snapshots actifs
    }
    if date_actuelle:
        query["date_situation"] = date_actuelle
    
    snapshots = await db[ARREARS_SNAPSHOTS_COLLECTION].find(query).to_list(length=10000)
    
    if not snapshots:
        return {
            "date_situation_actuelle": date_actuelle,
            "date_situation_precedente": date_precedente,
            "nombre_dates_disponibles": len(dates_disponibles),
            "kpis": {
                "total_montant_impaye": 0.0,
                "total_credits": 0,
                "total_encours": 0.0,
                "montant_moyen_par_credit": 0.0,
                "ratio_impaye_encours_moyen": 0.0,
                "candidats_restructuration": 0,
                "taux_impayes": 0.0,
            },
            "repartition_tranches": {},
            "repartition_segments": {},
            "repartition_agences": {},
            "repartition_gestionnaires": {},
            "repartition_produits": {},
            "top_10_credits_par_montant": [],
            "top_10_credits_par_jours_retard": [],
            "top_10_credits_par_ratio": [],
            "statistiques_sms": None,
            "indicateurs_recouvrement": None,
        }
    
    # ========== Calcul des KPIs ==========
    total_montant_impaye = sum(s.get("montant_total_impaye", 0) for s in snapshots)
    total_credits = len(snapshots)
    total_encours = sum(s.get("encours_principal", 0) for s in snapshots)
    montant_moyen = total_montant_impaye / total_credits if total_credits > 0 else 0
    
    # Calculer le ratio moyen comme ratio global (plus représentatif que la moyenne des ratios individuels)
    # Ratio global = (Total montant impayé / Total encours) * 100
    ratio_moyen = (total_montant_impaye / total_encours * 100) if total_encours > 0 else 0
    
    candidats_restruct = sum(1 for s in snapshots if s.get("candidat_restructuration", False))
    taux_impayes = (total_montant_impaye / total_encours * 100) if total_encours > 0 else 0
    
    kpis = {
        "total_montant_impaye": round(total_montant_impaye, 2),
        "total_credits": total_credits,
        "total_encours": round(total_encours, 2),
        "montant_moyen_par_credit": round(montant_moyen, 2),
        "ratio_impaye_encours_moyen": round(ratio_moyen, 2),
        "candidats_restructuration": candidats_restruct,
        "taux_impayes": round(taux_impayes, 2),
    }
    
    # ========== Évolution ==========
    evolution = None
    tendance = "pas_de_comparaison"
    couleur_tendance = "neutral"
    icone_tendance = "equal"
    comparaisons_paralleles = []
    
    def determiner_couleur_icone_avec_hex(pourcentage: float, inverse: bool = False) -> dict:
        """
        Détermine la couleur, l'icône et les codes hexadécimaux selon la variation
        Utilise un CONTRASTE MAXIMAL : fond blanc/très clair avec texte très foncé
        pour une lisibilité parfaite
        
        inverse=True : baisse = succès (vert foncé), hausse = danger (rouge foncé) - pour les impayés
        inverse=False : hausse = succès (vert foncé), baisse = danger (rouge foncé) - pour les recouvrements
        """
        if pourcentage is None or abs(pourcentage) < 0.1:
            # Stable : fond blanc opaque avec texte noir et bordure épaisse
            return {
                "couleur": "neutral-dark",
                "icone": "equal",
                "couleur_hex": "#000000",  # Noir pur pour contraste maximal
                "couleur_bg": "#ffffff",  # Fond blanc pur
                "avec_fond": True,
                "style_recommande": {
                    "backgroundColor": "#ffffff",
                    "color": "#000000",
                    "border": "4px solid #000000",
                    "padding": "10px 16px",
                    "borderRadius": "8px",
                    "fontWeight": "900",
                    "fontSize": "15px",
                    "display": "inline-block",
                    "boxShadow": "0 4px 8px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.5)",
                    "textShadow": "none",
                    "letterSpacing": "0.5px"
                }
            }
        
        if inverse:
            # Pour les impayés : baisse = bon (vert foncé), hausse = mauvais (rouge foncé)
            if pourcentage < -5:
                # Baisse : fond blanc opaque avec texte noir et bordure verte épaisse
                return {
                    "couleur": "success-dark",
                    "icone": "arrow-down",
                    "couleur_hex": "#000000",  # Noir pur pour contraste maximal
                    "couleur_bg": "#ffffff",  # Fond blanc pur
                    "avec_fond": True,
                    "style_recommande": {
                        "backgroundColor": "#ffffff",
                        "color": "#000000",
                        "border": "4px solid #0d5132",  # Bordure verte épaisse
                        "padding": "10px 16px",
                        "borderRadius": "8px",
                        "fontWeight": "900",
                        "fontSize": "15px",
                        "display": "inline-block",
                        "boxShadow": "0 4px 8px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.5)",
                        "textShadow": "none",
                        "letterSpacing": "0.5px"
                    }
                }
            elif pourcentage > 5:
                # Hausse : fond blanc opaque avec texte noir et bordure rouge épaisse
                return {
                    "couleur": "danger-dark",
                    "icone": "arrow-up",
                    "couleur_hex": "#000000",  # Noir pur pour contraste maximal
                    "couleur_bg": "#ffffff",  # Fond blanc pur
                    "avec_fond": True,
                    "style_recommande": {
                        "backgroundColor": "#ffffff",
                        "color": "#000000",
                        "border": "4px solid #8b0000",  # Bordure rouge épaisse
                        "padding": "10px 16px",
                        "borderRadius": "8px",
                        "fontWeight": "900",
                        "fontSize": "15px",
                        "display": "inline-block",
                        "boxShadow": "0 4px 8px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.5)",
                        "textShadow": "none",
                        "letterSpacing": "0.5px"
                    }
                }
            else:
                # Variation faible : fond blanc opaque avec texte noir et bordure orange épaisse
                return {
                    "couleur": "warning-dark",
                    "icone": "equal",
                    "couleur_hex": "#000000",  # Noir pur pour contraste maximal
                    "couleur_bg": "#ffffff",  # Fond blanc pur
                    "avec_fond": True,
                    "style_recommande": {
                        "backgroundColor": "#ffffff",
                        "color": "#000000",
                        "border": "4px solid #8b6914",  # Bordure orange épaisse
                        "padding": "10px 16px",
                        "borderRadius": "8px",
                        "fontWeight": "900",
                        "fontSize": "15px",
                        "display": "inline-block",
                        "boxShadow": "0 4px 8px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.5)",
                        "textShadow": "none",
                        "letterSpacing": "0.5px"
                    }
                }
        else:
            # Pour les recouvrements : hausse = bon (vert foncé), baisse = mauvais (rouge foncé)
            if pourcentage > 5:
                return {
                    "couleur": "success-dark",
                    "icone": "arrow-up",
                    "couleur_hex": "#0d5132",
                    "couleur_bg": "#ffffff",
                    "avec_fond": True,
                    "style_recommande": {
                        "backgroundColor": "#ffffff",
                        "color": "#0d5132",
                        "border": "3px solid #0d5132",
                        "padding": "8px 14px",
                        "borderRadius": "6px",
                        "fontWeight": "bold",
                        "fontSize": "14px",
                        "display": "inline-block",
                        "boxShadow": "0 2px 4px rgba(13,81,50,0.2)"
                    }
                }
            elif pourcentage < -5:
                return {
                    "couleur": "danger-dark",
                    "icone": "arrow-down",
                    "couleur_hex": "#8b0000",
                    "couleur_bg": "#ffffff",
                    "avec_fond": True,
                    "style_recommande": {
                        "backgroundColor": "#ffffff",
                        "color": "#8b0000",
                        "border": "3px solid #8b0000",
                        "padding": "8px 14px",
                        "borderRadius": "6px",
                        "fontWeight": "bold",
                        "fontSize": "14px",
                        "display": "inline-block",
                        "boxShadow": "0 2px 4px rgba(139,0,0,0.2)"
                    }
                }
            else:
                return {
                    "couleur": "warning-dark",
                    "icone": "equal",
                    "couleur_hex": "#8b6914",
                    "couleur_bg": "#ffffff",
                    "avec_fond": True,
                    "style_recommande": {
                        "backgroundColor": "#ffffff",
                        "color": "#8b6914",
                        "border": "3px solid #8b6914",
                        "padding": "8px 14px",
                        "borderRadius": "6px",
                        "fontWeight": "bold",
                        "fontSize": "14px",
                        "display": "inline-block",
                        "boxShadow": "0 2px 4px rgba(139,105,20,0.2)"
                    }
                }
    
    def determiner_couleur_icone(pourcentage: float, inverse: bool = False) -> tuple:
        """Version simplifiée pour compatibilité"""
        result = determiner_couleur_icone_avec_hex(pourcentage, inverse)
        return result["couleur"], result["icone"]
    
    if date_precedente:
        evolution_data = await comparer_statistiques(organization_id, date_actuelle, date_precedente)
        evolution = evolution_data.get("evolution")
        tendance = evolution_data.get("tendance", "stable")
        
        # Déterminer couleur et icône pour la tendance globale
        if evolution:
            pourcentage_montant = evolution.get("montant_impaye", {}).get("pourcentage", 0)
            couleur_tendance, icone_tendance = determiner_couleur_icone(pourcentage_montant, inverse=True)
            
            # Ajouter couleurs et icônes aux indicateurs d'évolution avec codes hex et styles
            for key, indicateur in evolution.items():
                if isinstance(indicateur, dict) and "pourcentage" in indicateur:
                    pourcentage = indicateur.get("pourcentage", 0)
                    couleur_info = determiner_couleur_icone_avec_hex(pourcentage, inverse=True)
                    indicateur["couleur"] = couleur_info["couleur"]
                    indicateur["icone"] = couleur_info["icone"]
                    indicateur["couleur_hex"] = couleur_info["couleur_hex"]
                    indicateur["couleur_bg"] = couleur_info["couleur_bg"]
                    indicateur["avec_fond"] = couleur_info["avec_fond"]
                    indicateur["style_recommande"] = couleur_info["style_recommande"]
        
        # Créer les comparaisons en parallèle
        stats_actuelles = evolution_data.get("stats_actuelles", {})
        stats_precedentes = evolution_data.get("stats_precedentes", {})
        
        if stats_actuelles and stats_precedentes:
            comparaisons_paralleles = [
                {
                    "indicateur": "montant_impaye",
                    "libelle": "Montant total impayé",
                    "valeur_actuelle": stats_actuelles.get("total_montant_impaye", 0),
                    "valeur_precedente": stats_precedentes.get("total_montant_impaye", 0),
                    "difference": stats_actuelles.get("total_montant_impaye", 0) - stats_precedentes.get("total_montant_impaye", 0),
                    "pourcentage": evolution.get("montant_impaye", {}).get("pourcentage", 0) if evolution else 0,
                    "couleur": "",
                    "icone": "",
                },
                {
                    "indicateur": "nombre_credits",
                    "libelle": "Nombre de crédits impayés",
                    "valeur_actuelle": stats_actuelles.get("total_credits", 0),
                    "valeur_precedente": stats_precedentes.get("total_credits", 0),
                    "difference": stats_actuelles.get("total_credits", 0) - stats_precedentes.get("total_credits", 0),
                    "pourcentage": evolution.get("nombre_credits", {}).get("pourcentage", 0) if evolution else 0,
                    "couleur": "",
                    "icone": "",
                },
                {
                    "indicateur": "candidats_restructuration",
                    "libelle": "Candidats à restructuration",
                    "valeur_actuelle": stats_actuelles.get("candidats_restructuration", 0),
                    "valeur_precedente": stats_precedentes.get("candidats_restructuration", 0),
                    "difference": stats_actuelles.get("candidats_restructuration", 0) - stats_precedentes.get("candidats_restructuration", 0),
                    "pourcentage": evolution.get("candidats_restructuration", {}).get("pourcentage", 0) if evolution else 0,
                    "couleur": "",
                    "icone": "",
                },
                {
                    "indicateur": "ratio_moyen",
                    "libelle": "Ratio impayé/encours moyen (%)",
                    "valeur_actuelle": stats_actuelles.get("ratio_impaye_encours_moyen", 0),
                    "valeur_precedente": stats_precedentes.get("ratio_impaye_encours_moyen", 0),
                    "difference": stats_actuelles.get("ratio_impaye_encours_moyen", 0) - stats_precedentes.get("ratio_impaye_encours_moyen", 0),
                    "pourcentage": evolution.get("ratio_moyen", {}).get("pourcentage", 0) if evolution else 0,
                    "couleur": "",
                    "icone": "",
                },
            ]
            
            # Ajouter couleurs et icônes aux comparaisons avec codes hex et styles
            for comp in comparaisons_paralleles:
                pourcentage = comp.get("pourcentage", 0)
                couleur_info = determiner_couleur_icone_avec_hex(pourcentage, inverse=True)
                comp["couleur"] = couleur_info["couleur"]
                comp["icone"] = couleur_info["icone"]
                comp["couleur_hex"] = couleur_info["couleur_hex"]
                comp["couleur_bg"] = couleur_info["couleur_bg"]
                comp["avec_fond"] = couleur_info["avec_fond"]
                comp["style_recommande"] = couleur_info["style_recommande"]
    
    # ========== Répartitions détaillées ==========
    def calculer_repartition_detaillee(snapshots, champ):
        """Calcule une répartition détaillée pour un champ donné"""
        repartition = {}
        total_montant = sum(s.get("montant_total_impaye", 0) for s in snapshots)
        
        for snapshot in snapshots:
            valeur = snapshot.get(champ, "Non défini")
            if valeur not in repartition:
                repartition[valeur] = {
                    "nombre": 0,
                    "montant_total": 0.0,
                    "montant_moyen": 0.0,
                }
            
            repartition[valeur]["nombre"] += 1
            repartition[valeur]["montant_total"] += snapshot.get("montant_total_impaye", 0)
        
        # Calculer les pourcentages
        for valeur, data in repartition.items():
            data["pourcentage_nombre"] = round((data["nombre"] / total_credits * 100) if total_credits > 0 else 0, 2)
            data["pourcentage_montant"] = round((data["montant_total"] / total_montant * 100) if total_montant > 0 else 0, 2)
            data["montant_moyen"] = round(data["montant_total"] / data["nombre"] if data["nombre"] > 0 else 0, 2)
        
        return repartition
    
    repartition_tranches = calculer_repartition_detaillee(snapshots, "bucket_retard")
    repartition_segments = calculer_repartition_detaillee(snapshots, "segment")
    repartition_agences = calculer_repartition_detaillee(snapshots, "agence")
    repartition_gestionnaires = calculer_repartition_detaillee(snapshots, "gestionnaire")
    repartition_produits = calculer_repartition_detaillee(snapshots, "produit")
    repartition_statuts = calculer_repartition_detaillee(snapshots, "statut_interne")
    
    # ========== Top crédits ==========
    def creer_top_credit(snapshot):
        return {
            "ref_credit": snapshot.get("ref_credit", ""),
            "nom_client": snapshot.get("nom_client", ""),
            "montant_total_impaye": snapshot.get("montant_total_impaye", 0),
            "jours_retard": snapshot.get("jours_retard", 0),
            "bucket_retard": snapshot.get("bucket_retard", ""),
            "agence": snapshot.get("agence", ""),
            "segment": snapshot.get("segment", ""),
        }
    
    top_10_credits_par_montant = sorted(
        [creer_top_credit(s) for s in snapshots],
        key=lambda x: x["montant_total_impaye"],
        reverse=True
    )[:10]
    
    top_10_credits_par_jours_retard = sorted(
        [creer_top_credit(s) for s in snapshots],
        key=lambda x: x["jours_retard"],
        reverse=True
    )[:10]
    
    # Top crédits par ratio (avec ratio dans la clé de tri)
    credits_avec_ratio = []
    for s in snapshots:
        credit = creer_top_credit(s)
        credit["ratio_impaye_encours"] = s.get("ratio_impaye_encours", 0)
        if credit["ratio_impaye_encours"] > 0:
            credits_avec_ratio.append(credit)
    
    top_10_credits_par_ratio = sorted(
        credits_avec_ratio,
        key=lambda x: x.get("ratio_impaye_encours", 0),
        reverse=True
    )[:10]
    
    # ========== Évolution temporelle ==========
    historique = await get_historique_statistiques(organization_id, limit=12)
    
    evolution_montant = [
        {
            "date_situation": h.get("date_situation", ""),
            "valeur": h.get("total_montant_impaye", 0),
            "variation": None
        }
        for h in historique
    ]
    
    # Calculer les variations
    for i in range(1, len(evolution_montant)):
        prev = evolution_montant[i-1]["valeur"]
        curr = evolution_montant[i]["valeur"]
        if prev > 0:
            evolution_montant[i]["variation"] = round(((curr - prev) / prev) * 100, 2)
    
    evolution_nombre_credits = [
        {
            "date_situation": h.get("date_situation", ""),
            "valeur": h.get("total_credits", 0),
            "variation": None
        }
        for h in historique
    ]
    
    for i in range(1, len(evolution_nombre_credits)):
        prev = evolution_nombre_credits[i-1]["valeur"]
        curr = evolution_nombre_credits[i]["valeur"]
        if prev > 0:
            evolution_nombre_credits[i]["variation"] = round(((curr - prev) / prev) * 100, 2)
    
    evolution_candidats_restructuration = [
        {
            "date_situation": h.get("date_situation", ""),
            "valeur": h.get("candidats_restructuration", 0),
            "variation": None
        }
        for h in historique
    ]
    
    for i in range(1, len(evolution_candidats_restructuration)):
        prev = evolution_candidats_restructuration[i-1]["valeur"]
        curr = evolution_candidats_restructuration[i]["valeur"]
        if prev > 0:
            evolution_candidats_restructuration[i]["variation"] = round(((curr - prev) / prev) * 100, 2)
    
    # ========== Indicateurs de recouvrement ==========
    indicateurs_recouvrement = None
    if len(dates_disponibles) >= 2:
        try:
            indicateurs = await calculer_indicateurs_recouvrement(organization_id)
            indicateurs_recouvrement = indicateurs
        except Exception as e:
            logger.error(f"Erreur calcul indicateurs recouvrement: {str(e)}")
    
    # ========== Statistiques SMS ==========
    sms_envoyes = await db[SMS_HISTORY_COLLECTION].find({"organization_id": org_oid}).to_list(length=10000)
    sms_pending = await get_pending_messages(organization_id)
    sms_all = await get_all_messages(organization_id, limit=10000)
    
    total_sms_envoyes = len(sms_envoyes)
    total_sms_pending = len(sms_pending)
    total_sms_echoues = sum(1 for s in sms_all if s.get("status") == "FAILED")
    taux_succes_sms = (total_sms_envoyes / (total_sms_envoyes + total_sms_echoues) * 100) if (total_sms_envoyes + total_sms_echoues) > 0 else 0
    
    # Crédits avec SMS
    ref_credits_avec_sms = {s.get("linked_credit") for s in sms_all if s.get("linked_credit")}
    credits_avec_sms = [s for s in snapshots if s.get("ref_credit") in ref_credits_avec_sms]
    montant_impaye_couvert = sum(s.get("montant_total_impaye", 0) for s in credits_avec_sms)
    
    # Répartition SMS par tranche
    repartition_sms_par_tranche = {}
    for sms in sms_all:
        snapshot = next((s for s in snapshots if s.get("ref_credit") == sms.get("linked_credit")), None)
        if snapshot:
            tranche = snapshot.get("bucket_retard", "Non défini")
            if tranche not in repartition_sms_par_tranche:
                repartition_sms_par_tranche[tranche] = {"envoyes": 0, "en_attente": 0, "echoues": 0}
            
            status = sms.get("status", "PENDING")
            if status == "SENT":
                repartition_sms_par_tranche[tranche]["envoyes"] += 1
            elif status == "PENDING":
                repartition_sms_par_tranche[tranche]["en_attente"] += 1
            elif status == "FAILED":
                repartition_sms_par_tranche[tranche]["echoues"] += 1
    
    statistiques_sms = {
        "total_envoyes": total_sms_envoyes,
        "total_en_attente": total_sms_pending,
        "total_echoues": total_sms_echoues,
        "taux_succes": round(taux_succes_sms, 2),
        "montant_impaye_couvert": round(montant_impaye_couvert, 2),
        "nombre_credits_avec_sms": len(credits_avec_sms),
        "nombre_credits_sans_sms": total_credits - len(credits_avec_sms),
        "repartition_par_tranche": repartition_sms_par_tranche,
    }
    
    # ========== Analyses approfondies ==========
    credits_avec_garanties = [s for s in snapshots if s.get("garanties")]
    montant_avec_garanties = sum(s.get("montant_total_impaye", 0) for s in credits_avec_garanties)
    credits_sans_garanties = total_credits - len(credits_avec_garanties)
    montant_sans_garanties = total_montant_impaye - montant_avec_garanties
    
    credits_avec_telephone = [s for s in snapshots if s.get("telephone_client")]
    credits_sans_telephone = total_credits - len(credits_avec_telephone)
    
    duree_moyenne_retard = sum(s.get("jours_retard", 0) for s in snapshots) / total_credits if total_credits > 0 else 0
    echeances_impayees_moyennes = sum(s.get("nb_echeances_impayees", 0) for s in snapshots) / total_credits if total_credits > 0 else 0
    
    total_penalites = sum(s.get("penalites_impayees", 0) for s in snapshots)
    total_interets = sum(s.get("interets_impayes", 0) for s in snapshots)
    taux_penalites = (total_penalites / total_montant_impaye * 100) if total_montant_impaye > 0 else 0
    taux_interets = (total_interets / total_montant_impaye * 100) if total_montant_impaye > 0 else 0
    
    analyses = {
        "credits_avec_garanties": len(credits_avec_garanties),
        "montant_avec_garanties": round(montant_avec_garanties, 2),
        "credits_sans_garanties": credits_sans_garanties,
        "montant_sans_garanties": round(montant_sans_garanties, 2),
        "credits_avec_telephone": len(credits_avec_telephone),
        "credits_sans_telephone": credits_sans_telephone,
        "duree_moyenne_retard": round(duree_moyenne_retard, 1),
        "echeances_impayees_moyennes": round(echeances_impayees_moyennes, 2),
        "taux_penalites": round(taux_penalites, 2),
        "taux_interets": round(taux_interets, 2),
    }
    
    # ========== Alertes et risques ==========
    alertes = []
    
    # Alerte : Crédits sans téléphone
    if credits_sans_telephone > 0:
        montant_sans_tel = sum(s.get("montant_total_impaye", 0) for s in snapshots if not s.get("telephone_client"))
        alertes.append({
            "type": "attention",
            "titre": f"{credits_sans_telephone} crédit(s) sans numéro de téléphone",
            "description": f"Impossible d'envoyer des SMS pour {credits_sans_telephone} crédit(s) représentant {montant_sans_tel:,.0f} FCFA",
            "nombre_credits_concernes": credits_sans_telephone,
            "montant_concerme": round(montant_sans_tel, 2),
            "action_recommandee": "Mettre à jour les numéros de téléphone dans le fichier d'import",
        })
    
    # Alerte : Candidats à restructuration
    if candidats_restruct > 0:
        montant_candidats = sum(s.get("montant_total_impaye", 0) for s in snapshots if s.get("candidat_restructuration", False))
        alertes.append({
            "type": "critique",
            "titre": f"{candidats_restruct} candidat(s) à restructuration",
            "description": f"{candidats_restruct} crédit(s) nécessitent une restructuration, représentant {montant_candidats:,.0f} FCFA",
            "nombre_credits_concernes": candidats_restruct,
            "montant_concerme": round(montant_candidats, 2),
            "action_recommandee": "Examiner les candidats à restructuration et prendre des décisions",
        })
    
    # Alerte : Crédits en zone critique
    credits_critiques = [s for s in snapshots if "critique" in s.get("bucket_retard", "").lower() or "douteux" in s.get("bucket_retard", "").lower()]
    if credits_critiques:
        montant_critique = sum(s.get("montant_total_impaye", 0) for s in credits_critiques)
        alertes.append({
            "type": "critique",
            "titre": f"{len(credits_critiques)} crédit(s) en zone critique",
            "description": f"{len(credits_critiques)} crédit(s) sont en zone critique ou douteux, représentant {montant_critique:,.0f} FCFA",
            "nombre_credits_concernes": len(credits_critiques),
            "montant_concerme": round(montant_critique, 2),
            "action_recommandee": "Action urgente requise pour ces crédits",
        })
    
    # Alerte : SMS en attente
    if total_sms_pending > 0:
        alertes.append({
            "type": "info",
            "titre": f"{total_sms_pending} SMS en attente d'envoi",
            "description": f"{total_sms_pending} message(s) SMS sont prêts à être envoyés",
            "nombre_credits_concernes": total_sms_pending,
            "montant_concerme": 0,
            "action_recommandee": "Envoyer les SMS en attente via l'endpoint /impayes/messages/send",
        })
    
    # ========== Concentrations ==========
    # Top 5 agences
    agences_triees = sorted(repartition_agences.items(), key=lambda x: x[1]["montant_total"], reverse=True)[:5]
    top_5_agences = {agence: round((data["montant_total"] / total_montant_impaye * 100) if total_montant_impaye > 0 else 0, 2) for agence, data in agences_triees}
    
    # Top 5 segments
    segments_tries = sorted(repartition_segments.items(), key=lambda x: x[1]["montant_total"], reverse=True)[:5]
    top_5_segments = {segment: round((data["montant_total"] / total_montant_impaye * 100) if total_montant_impaye > 0 else 0, 2) for segment, data in segments_tries}
    
    # Top 5 produits
    produits_tries = sorted(repartition_produits.items(), key=lambda x: x[1]["montant_total"], reverse=True)[:5]
    top_5_produits = {produit: round((data["montant_total"] / total_montant_impaye * 100) if total_montant_impaye > 0 else 0, 2) for produit, data in produits_tries}
    
    concentrations = {
        "top_5_agences": top_5_agences,
        "top_5_segments": top_5_segments,
        "top_5_produits": top_5_produits,
    }
    
    # ========== Qualité des données ==========
    taux_completude_telephone = (len(credits_avec_telephone) / total_credits * 100) if total_credits > 0 else 0
    taux_completude_garanties = (len(credits_avec_garanties) / total_credits * 100) if total_credits > 0 else 0
    
    qualite_donnees = {
        "credits_avec_telephone": len(credits_avec_telephone),
        "credits_sans_telephone": credits_sans_telephone,
        "taux_completude_telephone": round(taux_completude_telephone, 2),
        "credits_avec_garanties": len(credits_avec_garanties),
        "taux_completude_garanties": round(taux_completude_garanties, 2),
    }
    
    return {
        "date_situation_actuelle": date_actuelle,
        "date_situation_precedente": date_precedente,
        "nombre_dates_disponibles": len(dates_disponibles),
        "kpis": kpis,
        "evolution": evolution,
        "tendance": tendance,
        "couleur_tendance": couleur_tendance,
        "icone_tendance": icone_tendance,
        "comparaisons_paralleles": comparaisons_paralleles,
        "repartition_tranches": repartition_tranches,
        "repartition_segments": repartition_segments,
        "repartition_agences": repartition_agences,
        "repartition_gestionnaires": repartition_gestionnaires,
        "repartition_produits": repartition_produits,
        "repartition_statuts": repartition_statuts,
        "top_10_credits_par_montant": top_10_credits_par_montant,
        "top_10_credits_par_jours_retard": top_10_credits_par_jours_retard,
        "top_10_credits_par_ratio": top_10_credits_par_ratio,
        "evolution_montant": evolution_montant,
        "evolution_nombre_credits": evolution_nombre_credits,
        "evolution_candidats_restructuration": evolution_candidats_restructuration,
        "indicateurs_recouvrement": indicateurs_recouvrement,
        "statistiques_sms": statistiques_sms,
        "analyses": analyses,
        "alertes": alertes,
        "concentrations": concentrations,
        "qualite_donnees": qualite_donnees,
    }

