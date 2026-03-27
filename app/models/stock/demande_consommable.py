from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from app.core.db import get_database
from app.models.stock.consommable import get_consommable_by_id, update_stock
from app.models.user import get_user_by_id

DEMANDES_CONSOMABLES_COLLECTION = "demandes_consommables"


async def _demande_doc_to_public(doc) -> dict:
    """Convertit un document MongoDB en dictionnaire public"""
    user_id = str(doc.get("user_id", ""))
    user_name = "N/A"
    
    # Récupérer le nom de l'utilisateur (sans bloquer si ça échoue)
    if user_id:
        try:
            user = await get_user_by_id(user_id)
            if user:
                user_name = user.get("full_name", "N/A")
        except Exception as e:
            print(f"Erreur lors de la récupération du nom de l'utilisateur {user_id}: {e}")
            # On continue avec "N/A" si la récupération échoue
    
    try:
        # Convertir approbation_directeur pour sérialisation JSON
        approbation_directeur = doc.get("approbation_directeur", {})
        if approbation_directeur and isinstance(approbation_directeur, dict):
            approbation_clean = {}
            for key, value in approbation_directeur.items():
                if key == "directeur_id" and value:
                    approbation_clean[key] = str(value)
                elif key == "date" and value:
                    if isinstance(value, datetime):
                        approbation_clean[key] = value.isoformat()
                    else:
                        approbation_clean[key] = value
                else:
                    approbation_clean[key] = value
        else:
            approbation_clean = approbation_directeur

        # Convertir approbation_drh pour sérialisation JSON
        approbation_drh = doc.get("approbation_drh", {})
        if approbation_drh and isinstance(approbation_drh, dict):
            approbation_drh_clean = {}
            for key, value in approbation_drh.items():
                if key == "directeur_drh_id" and value:
                    approbation_drh_clean[key] = str(value)
                elif key == "date" and value:
                    if isinstance(value, datetime):
                        approbation_drh_clean[key] = value.isoformat()
                    else:
                        approbation_drh_clean[key] = value
                else:
                    approbation_drh_clean[key] = value
        else:
            approbation_drh_clean = approbation_drh

        # Convertir formalisation_drh pour sérialisation JSON
        formalisation_drh = doc.get("formalisation_drh", {})
        if formalisation_drh and isinstance(formalisation_drh, dict):
            formalisation_clean = {}
            for key, value in formalisation_drh.items():
                if key == "agent_drh_id" and value:
                    formalisation_clean[key] = str(value)
                elif key == "date" and value:
                    if isinstance(value, datetime):
                        formalisation_clean[key] = value.isoformat()
                    else:
                        formalisation_clean[key] = value
                else:
                    formalisation_clean[key] = value
        else:
            formalisation_clean = formalisation_drh

        # Convertir validation_sortie pour sérialisation JSON
        validation_sortie = doc.get("validation_sortie", {})
        if validation_sortie and isinstance(validation_sortie, dict):
            validation_clean = {}
            for key, value in validation_sortie.items():
                if key in ["agent_departement_id", "agent_stock_id"] and value:
                    validation_clean[key] = str(value)
                elif key in ["date_validation_departement", "date_validation_stock"] and value:
                    if isinstance(value, datetime):
                        validation_clean[key] = value.isoformat()
                    else:
                        validation_clean[key] = value
                else:
                    validation_clean[key] = value
        else:
            validation_clean = validation_sortie

        # Convertir traitement_stock pour sérialisation JSON
        traitement_stock = doc.get("traitement_stock", {})
        if traitement_stock and isinstance(traitement_stock, dict):
            traitement_clean = {}
            for key, value in traitement_stock.items():
                if key == "gestionnaire_id" and value:
                    traitement_clean[key] = str(value)
                elif key == "date" and value:
                    if isinstance(value, datetime):
                        traitement_clean[key] = value.isoformat()
                    else:
                        traitement_clean[key] = value
                else:
                    traitement_clean[key] = value
        else:
            traitement_clean = traitement_stock

        result = {
            "id": str(doc["_id"]),
            "consommable_id": str(doc.get("consommable_id", "")),
            "user_id": user_id,
            "user_name": user_name,
            "department_id": str(doc.get("department_id", "")),
            "quantite_demandee": doc.get("quantite_demandee", 0),
            "motif": doc.get("motif", ""),
            "type_selection": doc.get("type_selection", "conteneur"),
            "statut": doc.get("statut", "en_attente"),
            "approbation_directeur": approbation_clean,
            "approbation_drh": approbation_drh_clean,
            "formalisation_drh": formalisation_clean,
            "validation_sortie": validation_clean,
            "traitement_stock": traitement_clean,
            "created_at": doc.get("created_at").isoformat()
            if doc.get("created_at") and isinstance(doc.get("created_at"), datetime)
            else None,
            "updated_at": doc.get("updated_at").isoformat()
            if doc.get("updated_at") and isinstance(doc.get("updated_at"), datetime)
            else None,
        }
        return result
    except Exception as e:
        print(f"Erreur lors de la conversion de la demande en public: {e}")
        import traceback
        traceback.print_exc()
        raise


async def create_demande(demande_data: dict) -> dict:
    """
    Crée une demande de consommable.
    """
    db = get_database()

    try:
        consommable_oid = ObjectId(demande_data["consommable_id"])
        user_oid = ObjectId(demande_data["user_id"])
        dept_oid = ObjectId(demande_data["department_id"])
    except Exception:
        raise ValueError("IDs invalides.")

    # Vérifier que le consommable existe et a du stock
    consommable = await get_consommable_by_id(demande_data["consommable_id"])
    if not consommable:
        raise ValueError("Consommable introuvable.")

    if consommable["quantite_stock_conteneur"] <= 0:
        raise ValueError("Stock insuffisant pour ce consommable.")

    demande_doc = {
        "consommable_id": consommable_oid,
        "user_id": user_oid,
        "department_id": dept_oid,
        "quantite_demandee": demande_data.get("quantite_demandee", 0),
        "motif": demande_data.get("motif", ""),
        "type_selection": demande_data.get("type_selection", "conteneur"),
        "statut": "en_attente",
        "approbation_directeur": {
            "statut": "en_attente",
            "directeur_id": None,
            "date": None,
            "commentaire": None,
        },
        "approbation_drh": {
            "statut": "en_attente",
            "directeur_drh_id": None,
            "date": None,
            "commentaire": None,
        },
        "formalisation_drh": {
            "statut": "en_attente",
            "agent_drh_id": None,
            "date": None,
            "commentaire": None,
        },
        "validation_sortie": {
            "statut": "en_attente",
            "valide_par_agent_departement": False,
            "valide_par_agent_stock": False,
            "agent_departement_id": None,
            "agent_stock_id": None,
            "date_validation_departement": None,
            "date_validation_stock": None,
            "quantite_accordee": None,
            "commentaire": None,
        },
        "traitement_stock": {
            "gestionnaire_id": None,
            "date": None,
            "quantite_accordee": None,
            "commentaire": None,
        },
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    print(f"Création demande - user_id: {demande_data.get('user_id')}, department_id: {demande_data.get('department_id')} (ObjectId: {dept_oid})")
    
    result = await db[DEMANDES_CONSOMABLES_COLLECTION].insert_one(demande_doc)
    demande_doc["_id"] = result.inserted_id

    print(f"Demande créée avec ID: {result.inserted_id}, department_id: {dept_oid}")
    
    return await _demande_doc_to_public(demande_doc)


async def get_demande_by_id(demande_id: str) -> Optional[dict]:
    """Récupère une demande par son ID"""
    db = get_database()
    try:
        doc = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one(
            {"_id": ObjectId(demande_id)}
        )
        if doc:
            return await _demande_doc_to_public(doc)
        return None
    except Exception:
        return None


async def list_demandes_by_user(user_id: str) -> List[dict]:
    """Liste les demandes d'un utilisateur"""
    db = get_database()
    try:
        user_oid = ObjectId(user_id)
    except Exception:
        return []

    cursor = (
        db[DEMANDES_CONSOMABLES_COLLECTION]
        .find({"user_id": user_oid})
        .sort("created_at", -1)
    )
    demandes = []
    async for doc in cursor:
        demandes.append(await _demande_doc_to_public(doc))
    return demandes


async def list_demandes_by_department(department_id: str) -> List[dict]:
    """Liste les demandes d'un département"""
    db = get_database()
    try:
        dept_oid = ObjectId(department_id)
    except Exception:
        return []

    cursor = (
        db[DEMANDES_CONSOMABLES_COLLECTION]
        .find({"department_id": dept_oid})
        .sort("created_at", -1)
    )
    demandes = []
    async for doc in cursor:
        demandes.append(await _demande_doc_to_public(doc))
    return demandes


async def list_demandes_pending_directeur(department_id: str) -> List[dict]:
    """Liste les demandes en attente de validation par le directeur"""
    db = get_database()
    try:
        dept_oid = ObjectId(department_id)
    except Exception as e:
        print(f"Erreur conversion ObjectId department_id: {e}")
        return []

    # Rechercher les demandes avec le department_id correspondant
    # et qui sont en attente de validation par le directeur
    # On cherche les demandes qui sont en statut "en_attente" ET qui ont approbation_directeur.statut = "en_attente"
    query = {
        "department_id": dept_oid,
        "statut": "en_attente",
        "approbation_directeur.statut": "en_attente",
    }
    
    print(f"Recherche demandes directeur - department_id: {department_id} (ObjectId: {dept_oid})")
    
    # Compter d'abord toutes les demandes du département pour debug
    total_count = await db[DEMANDES_CONSOMABLES_COLLECTION].count_documents({"department_id": dept_oid})
    print(f"Total demandes dans ce département: {total_count}")
    
    # Compter les demandes en attente
    pending_count = await db[DEMANDES_CONSOMABLES_COLLECTION].count_documents({
        "department_id": dept_oid,
        "statut": "en_attente"
    })
    print(f"Demandes en statut 'en_attente': {pending_count}")
    
    # Vérifier aussi les demandes avec approbation_directeur.statut = "en_attente"
    approbation_pending_count = await db[DEMANDES_CONSOMABLES_COLLECTION].count_documents({
        "department_id": dept_oid,
        "approbation_directeur.statut": "en_attente"
    })
    print(f"Demandes avec approbation_directeur.statut='en_attente': {approbation_pending_count}")
    
    # Afficher quelques exemples de demandes pour debug
    sample_cursor = db[DEMANDES_CONSOMABLES_COLLECTION].find({"department_id": dept_oid}).limit(5)
    async for sample_doc in sample_cursor:
        print(f"Exemple demande: id={sample_doc.get('_id')}, statut={sample_doc.get('statut')}, approbation.statut={sample_doc.get('approbation_directeur', {}).get('statut')}")
    
    cursor = (
        db[DEMANDES_CONSOMABLES_COLLECTION]
        .find(query)
        .sort("created_at", 1)
    )

    demandes = []
    async for doc in cursor:
        # Vérifier que le department_id correspond bien
        doc_dept_id = str(doc.get("department_id", ""))
        doc_statut = doc.get("statut", "")
        doc_approbation_statut = doc.get("approbation_directeur", {}).get("statut", "")
        
        print(f"Demande trouvée {doc.get('_id')}: dept={doc_dept_id}, statut={doc_statut}, approbation.statut={doc_approbation_statut}")
        
        if doc_dept_id == department_id:
            demandes.append(await _demande_doc_to_public(doc))
    
    print(f"Retourné {len(demandes)} demandes pour le directeur")
    return demandes


async def list_demandes_pending_approbation_drh(org_id: str) -> List[dict]:
    """Liste les demandes approuvées par le directeur département en attente d'approbation par le directeur DRH"""
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return []

    # Récupérer les consommables de l'organisation
    from app.models.stock.consommable import list_consommables_by_org

    consommables = await list_consommables_by_org(org_id)
    consommable_ids = [ObjectId(c["id"]) for c in consommables]

    cursor = (
        db[DEMANDES_CONSOMABLES_COLLECTION]
        .find(
            {
                "consommable_id": {"$in": consommable_ids},
                "statut": "approuve_directeur",
                "approbation_directeur.statut": "approuve",
                "approbation_drh.statut": "en_attente",
            }
        )
        .sort("approbation_directeur.date", 1)
    )

    demandes = []
    async for doc in cursor:
        demandes.append(await _demande_doc_to_public(doc))
    return demandes


async def list_demandes_pending_formalisation_drh(org_id: str) -> List[dict]:
    """Liste les demandes approuvées par le directeur DRH en attente de formalisation par l'agent DRH"""
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return []

    # Récupérer les consommables de l'organisation
    from app.models.stock.consommable import list_consommables_by_org

    consommables = await list_consommables_by_org(org_id)
    consommable_ids = [ObjectId(c["id"]) for c in consommables]

    cursor = (
        db[DEMANDES_CONSOMABLES_COLLECTION]
        .find(
            {
                "consommable_id": {"$in": consommable_ids},
                "statut": "approuve_drh",
                "approbation_drh.statut": "approuve",
                "formalisation_drh.statut": "en_attente",
            }
        )
        .sort("approbation_drh.date", 1)
    )

    demandes = []
    async for doc in cursor:
        demandes.append(await _demande_doc_to_public(doc))
    return demandes


async def list_demandes_pending_validation_sortie(org_id: str) -> List[dict]:
    """Liste les demandes formalisées en attente de validation conjointe des sorties"""
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return []

    # Récupérer les consommables de l'organisation
    from app.models.stock.consommable import list_consommables_by_org

    consommables = await list_consommables_by_org(org_id)
    consommable_ids = [ObjectId(c["id"]) for c in consommables]

    cursor = (
        db[DEMANDES_CONSOMABLES_COLLECTION]
        .find(
            {
                "consommable_id": {"$in": consommable_ids},
                "statut": "formalise_drh",
                "formalisation_drh.statut": "formalise",
                "$or": [
                    {"validation_sortie.valide_par_agent_departement": False},
                    {"validation_sortie.valide_par_agent_stock": False},
                ],
            }
        )
        .sort("formalisation_drh.date", 1)
    )

    demandes = []
    async for doc in cursor:
        demandes.append(await _demande_doc_to_public(doc))
    return demandes


async def list_demandes_pending_gestionnaire(org_id: str) -> List[dict]:
    """Liste les demandes approuvées par le directeur DRH en attente de traitement (débit stock)"""
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return []

    # Récupérer les consommables de l'organisation
    from app.models.stock.consommable import list_consommables_by_org

    consommables = await list_consommables_by_org(org_id)
    consommable_ids = [ObjectId(c["id"]) for c in consommables]

    cursor = (
        db[DEMANDES_CONSOMABLES_COLLECTION]
        .find(
            {
                "consommable_id": {"$in": consommable_ids},
                "statut": "approuve_drh",
                "approbation_drh.statut": "approuve",
            }
        )
        .sort("approbation_drh.date", 1)
    )

    demandes = []
    async for doc in cursor:
        demandes.append(await _demande_doc_to_public(doc))
    return demandes


async def approve_demande_directeur(
    demande_id: str, directeur_id: str, commentaire: Optional[str] = None
) -> Optional[dict]:
    """Approuve une demande par le directeur"""
    db = get_database()
    try:
        demande_oid = ObjectId(demande_id)
        directeur_oid = ObjectId(directeur_id)
    except Exception as e:
        print(f"Erreur conversion ObjectId dans approve_demande_directeur: {e}")
        raise ValueError("IDs invalides.")

    # Vérifier que la demande existe et est en attente
    demande = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one({"_id": demande_oid})
    if not demande:
        raise ValueError("Demande introuvable.")
    
    if demande.get("statut") != "en_attente":
        raise ValueError("Cette demande a déjà été traitée.")

    result = await db[DEMANDES_CONSOMABLES_COLLECTION].update_one(
        {"_id": demande_oid},
        {
            "$set": {
                "statut": "approuve_directeur",
                "approbation_directeur": {
                    "statut": "approuve",
                    "directeur_id": directeur_oid,
                    "date": datetime.utcnow(),
                    "commentaire": commentaire,
                },
                "updated_at": datetime.utcnow(),
            }
        },
    )

    if result.modified_count == 0:
        raise ValueError("Erreur lors de la mise à jour de la demande.")

    updated_doc = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one(
        {"_id": demande_oid}
    )
    if not updated_doc:
        raise ValueError("Erreur lors de la récupération de la demande mise à jour.")
    
    try:
        return await _demande_doc_to_public(updated_doc)
    except Exception as e:
        print(f"Erreur lors de la conversion de la demande en public: {e}")
        import traceback
        traceback.print_exc()
        raise ValueError(f"Erreur lors de la conversion de la demande: {str(e)}")


async def reject_demande_directeur(
    demande_id: str, directeur_id: str, commentaire: Optional[str] = None
) -> Optional[dict]:
    """Rejette une demande par le directeur"""
    db = get_database()
    try:
        demande_oid = ObjectId(demande_id)
        directeur_oid = ObjectId(directeur_id)
    except Exception as e:
        print(f"Erreur conversion ObjectId dans reject_demande_directeur: {e}")
        raise ValueError("IDs invalides.")

    # Vérifier que la demande existe et est en attente
    demande = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one({"_id": demande_oid})
    if not demande:
        raise ValueError("Demande introuvable.")
    
    if demande.get("statut") != "en_attente":
        raise ValueError("Cette demande a déjà été traitée.")

    result = await db[DEMANDES_CONSOMABLES_COLLECTION].update_one(
        {"_id": demande_oid},
        {
            "$set": {
                "statut": "rejete_directeur",
                "approbation_directeur": {
                    "statut": "rejete",
                    "directeur_id": directeur_oid,
                    "date": datetime.utcnow(),
                    "commentaire": commentaire,
                },
                "updated_at": datetime.utcnow(),
            }
        },
    )

    if result.modified_count == 0:
        raise ValueError("Erreur lors de la mise à jour de la demande.")

    updated_doc = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one(
        {"_id": demande_oid}
    )
    if not updated_doc:
        raise ValueError("Erreur lors de la récupération de la demande mise à jour.")
    
    try:
        return await _demande_doc_to_public(updated_doc)
    except Exception as e:
        print(f"Erreur lors de la conversion de la demande en public: {e}")
        import traceback
        traceback.print_exc()
        raise ValueError(f"Erreur lors de la conversion de la demande: {str(e)}")


async def approve_demande_drh(
    demande_id: str, directeur_drh_id: str, commentaire: Optional[str] = None
) -> Optional[dict]:
    """Approuve une demande par le directeur DRH"""
    db = get_database()
    try:
        demande_oid = ObjectId(demande_id)
        directeur_drh_oid = ObjectId(directeur_drh_id)
    except Exception as e:
        print(f"Erreur conversion ObjectId dans approve_demande_drh: {e}")
        raise ValueError("IDs invalides.")

    # Vérifier que la demande existe et est approuvée par le directeur département
    demande = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one({"_id": demande_oid})
    if not demande:
        raise ValueError("Demande introuvable.")
    
    if demande.get("statut") != "approuve_directeur":
        raise ValueError("Cette demande doit d'abord être approuvée par le directeur de département.")

    result = await db[DEMANDES_CONSOMABLES_COLLECTION].update_one(
        {"_id": demande_oid},
        {
            "$set": {
                "statut": "approuve_drh",
                "approbation_drh": {
                    "statut": "approuve",
                    "directeur_drh_id": directeur_drh_oid,
                    "date": datetime.utcnow(),
                    "commentaire": commentaire,
                },
                "updated_at": datetime.utcnow(),
            }
        },
    )

    if result.modified_count == 0:
        raise ValueError("Erreur lors de la mise à jour de la demande.")

    updated_doc = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one(
        {"_id": demande_oid}
    )
    if not updated_doc:
        raise ValueError("Erreur lors de la récupération de la demande mise à jour.")
    
    try:
        return await _demande_doc_to_public(updated_doc)
    except Exception as e:
        print(f"Erreur lors de la conversion de la demande en public: {e}")
        import traceback
        traceback.print_exc()
        raise ValueError(f"Erreur lors de la conversion de la demande: {str(e)}")


async def reject_demande_drh(
    demande_id: str, directeur_drh_id: str, commentaire: Optional[str] = None
) -> Optional[dict]:
    """Rejette une demande par le directeur DRH"""
    db = get_database()
    try:
        demande_oid = ObjectId(demande_id)
        directeur_drh_oid = ObjectId(directeur_drh_id)
    except Exception as e:
        print(f"Erreur conversion ObjectId dans reject_demande_drh: {e}")
        raise ValueError("IDs invalides.")

    # Vérifier que la demande existe et est approuvée par le directeur département
    demande = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one({"_id": demande_oid})
    if not demande:
        raise ValueError("Demande introuvable.")
    
    if demande.get("statut") != "approuve_directeur":
        raise ValueError("Cette demande doit d'abord être approuvée par le directeur de département.")

    result = await db[DEMANDES_CONSOMABLES_COLLECTION].update_one(
        {"_id": demande_oid},
        {
            "$set": {
                "statut": "rejete_drh",
                "approbation_drh": {
                    "statut": "rejete",
                    "directeur_drh_id": directeur_drh_oid,
                    "date": datetime.utcnow(),
                    "commentaire": commentaire,
                },
                "updated_at": datetime.utcnow(),
            }
        },
    )

    if result.modified_count == 0:
        raise ValueError("Erreur lors de la mise à jour de la demande.")

    updated_doc = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one(
        {"_id": demande_oid}
    )
    if not updated_doc:
        raise ValueError("Erreur lors de la récupération de la demande mise à jour.")
    
    try:
        return await _demande_doc_to_public(updated_doc)
    except Exception as e:
        print(f"Erreur lors de la conversion de la demande en public: {e}")
        import traceback
        traceback.print_exc()
        raise ValueError(f"Erreur lors de la conversion de la demande: {str(e)}")


async def formaliser_demande_drh(
    demande_id: str, agent_drh_id: str, commentaire: Optional[str] = None
) -> Optional[dict]:
    """Formalise une demande approuvée par l'agent DRH"""
    db = get_database()
    try:
        demande_oid = ObjectId(demande_id)
        agent_drh_oid = ObjectId(agent_drh_id)
    except Exception:
        return None

    # Vérifier que la demande est approuvée par le directeur DRH
    demande = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one({"_id": demande_oid})
    if not demande or demande.get("statut") != "approuve_drh":
        return None

    result = await db[DEMANDES_CONSOMABLES_COLLECTION].update_one(
        {"_id": demande_oid},
        {
            "$set": {
                "statut": "formalise_drh",
                "formalisation_drh": {
                    "statut": "formalise",
                    "agent_drh_id": agent_drh_oid,
                    "date": datetime.utcnow(),
                    "commentaire": commentaire,
                },
                "updated_at": datetime.utcnow(),
            }
        },
    )

    if result.modified_count > 0:
        updated_doc = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one(
            {"_id": demande_oid}
        )
        if updated_doc:
            return await _demande_doc_to_public(updated_doc)

    return None


async def valider_sortie_agent_departement(
    demande_id: str,
    agent_departement_id: str,
    quantite_accordee: int,
    commentaire: Optional[str] = None,
) -> Optional[dict]:
    """Valide la sortie par l'agent du département"""
    db = get_database()
    try:
        demande_oid = ObjectId(demande_id)
        agent_departement_oid = ObjectId(agent_departement_id)
    except Exception:
        return None

    # Vérifier que la demande est formalisée
    demande = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one({"_id": demande_oid})
    if not demande or demande.get("statut") != "formalise_drh":
        return None

    # Mettre à jour la validation
    update_data = {
        "validation_sortie.valide_par_agent_departement": True,
        "validation_sortie.agent_departement_id": agent_departement_oid,
        "validation_sortie.date_validation_departement": datetime.utcnow(),
        "validation_sortie.quantite_accordee": quantite_accordee,
        "updated_at": datetime.utcnow(),
    }
    if commentaire:
        update_data["validation_sortie.commentaire"] = commentaire

    result = await db[DEMANDES_CONSOMABLES_COLLECTION].update_one(
        {"_id": demande_oid}, {"$set": update_data}
    )

    if result.modified_count > 0:
        # Vérifier si les deux validations sont complètes
        updated_doc = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one(
            {"_id": demande_oid}
        )
        if updated_doc:
            validation = updated_doc.get("validation_sortie", {})
            if (
                validation.get("valide_par_agent_departement")
                and validation.get("valide_par_agent_stock")
            ):
                # Les deux validations sont complètes, passer au statut valide_sortie
                await db[DEMANDES_CONSOMABLES_COLLECTION].update_one(
                    {"_id": demande_oid},
                    {
                        "$set": {
                            "statut": "valide_sortie",
                            "validation_sortie.statut": "valide",
                            "updated_at": datetime.utcnow(),
                        }
                    },
                )
                updated_doc = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one(
                    {"_id": demande_oid}
                )

            return await _demande_doc_to_public(updated_doc)

    return None


async def valider_sortie_agent_stock(
    demande_id: str,
    agent_stock_id: str,
    quantite_accordee: int,
    commentaire: Optional[str] = None,
) -> Optional[dict]:
    """Valide la sortie par l'agent stock DRH"""
    db = get_database()
    try:
        demande_oid = ObjectId(demande_id)
        agent_stock_oid = ObjectId(agent_stock_id)
    except Exception:
        return None

    # Vérifier que la demande est formalisée
    demande = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one({"_id": demande_oid})
    if not demande or demande.get("statut") != "formalise_drh":
        return None

    # Mettre à jour la validation
    update_data = {
        "validation_sortie.valide_par_agent_stock": True,
        "validation_sortie.agent_stock_id": agent_stock_oid,
        "validation_sortie.date_validation_stock": datetime.utcnow(),
        "validation_sortie.quantite_accordee": quantite_accordee,
        "updated_at": datetime.utcnow(),
    }
    if commentaire:
        update_data["validation_sortie.commentaire"] = commentaire

    result = await db[DEMANDES_CONSOMABLES_COLLECTION].update_one(
        {"_id": demande_oid}, {"$set": update_data}
    )

    if result.modified_count > 0:
        # Vérifier si les deux validations sont complètes
        updated_doc = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one(
            {"_id": demande_oid}
        )
        if updated_doc:
            validation = updated_doc.get("validation_sortie", {})
            if (
                validation.get("valide_par_agent_departement")
                and validation.get("valide_par_agent_stock")
            ):
                # Les deux validations sont complètes, passer au statut valide_sortie
                await db[DEMANDES_CONSOMABLES_COLLECTION].update_one(
                    {"_id": demande_oid},
                    {
                        "$set": {
                            "statut": "valide_sortie",
                            "validation_sortie.statut": "valide",
                            "updated_at": datetime.utcnow(),
                        }
                    },
                )
                updated_doc = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one(
                    {"_id": demande_oid}
                )

            return await _demande_doc_to_public(updated_doc)

    return None


async def traiter_demande_gestionnaire(
    demande_id: str,
    gestionnaire_id: str,
    quantite_accordee: int,
    commentaire: Optional[str] = None,
) -> Optional[dict]:
    """Traite une demande approuvée par le directeur DRH et débite le stock"""
    db = get_database()
    try:
        demande_oid = ObjectId(demande_id)
        gestionnaire_oid = ObjectId(gestionnaire_id)
    except Exception as e:
        raise ValueError("IDs invalides.")

    # Récupérer la demande
    demande = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one({"_id": demande_oid})
    if not demande:
        raise ValueError("Demande introuvable.")

    # Vérifier que la demande est approuvée par le directeur DRH
    if demande.get("statut") != "approuve_drh":
        raise ValueError("Cette demande doit d'abord être approuvée par le directeur DRH.")
    
    # Vérifier que la demande a été approuvée par le directeur DRH
    approbation_drh = demande.get("approbation_drh", {})
    if approbation_drh.get("statut") != "approuve":
        raise ValueError("Cette demande n'a pas été approuvée par le directeur DRH.")

    # Vérifier le stock disponible
    consommable = await get_consommable_by_id(str(demande["consommable_id"]))
    if not consommable:
        raise ValueError("Consommable introuvable.")

    # Déterminer la quantité à débiter en fonction du type de sélection
    type_selection = demande.get("type_selection", "conteneur")
    
    if type_selection == "unite":
        # Si la demande est en unités, convertir en conteneurs
        quantite_par_conteneur = consommable.get("quantite_par_conteneur", 1)
        if quantite_par_conteneur <= 0:
            quantite_par_conteneur = 1
        quantite_conteneurs = (quantite_accordee + quantite_par_conteneur - 1) // quantite_par_conteneur
        quantite_finale = min(quantite_conteneurs, consommable["quantite_stock_conteneur"])
    else:
        # Si la demande est en conteneurs, utiliser directement
        quantite_finale = min(quantite_accordee, consommable["quantite_stock_conteneur"])

    if quantite_finale <= 0:
        raise ValueError("Stock insuffisant pour traiter cette demande.")

    # Débiter le stock
    try:
        await update_stock(str(demande["consommable_id"]), quantite_finale, "subtract")
    except ValueError as e:
        raise ValueError(f"Erreur lors du débit du stock: {str(e)}")

    # Mettre à jour la demande
    result = await db[DEMANDES_CONSOMABLES_COLLECTION].update_one(
        {"_id": demande_oid},
        {
            "$set": {
                "statut": "traite",
                "traitement_stock": {
                    "gestionnaire_id": gestionnaire_oid,
                    "date": datetime.utcnow(),
                    "quantite_accordee": quantite_finale,
                    "commentaire": commentaire,
                },
                "updated_at": datetime.utcnow(),
            }
        },
    )

    if result.modified_count > 0:
        updated_doc = await db[DEMANDES_CONSOMABLES_COLLECTION].find_one(
            {"_id": demande_oid}
        )
        if updated_doc:
            return await _demande_doc_to_public(updated_doc)

    return None


async def get_demande_history(demande_id: str) -> List[dict]:
    """Récupère l'historique complet d'une demande"""
    demande = await get_demande_by_id(demande_id)
    if not demande:
        return []

    history = []

    # Étape 1: Création
    history.append(
        {
            "date": demande["created_at"],
            "action": "Demande créée",
            "user_id": demande["user_id"],
        }
    )

    # Étape 2: Validation directeur
    if demande.get("approbation_directeur", {}).get("date"):
        approbation = demande["approbation_directeur"]
        history.append(
            {
                "date": approbation["date"],
                "action": "Approuvée par le directeur"
                if approbation["statut"] == "approuve"
                else "Rejetée par le directeur",
                "user_id": approbation.get("directeur_id"),
                "commentaire": approbation.get("commentaire"),
            }
        )

    # Étape 3: Formalisation DRH
    if demande.get("formalisation_drh", {}).get("date"):
        formalisation = demande["formalisation_drh"]
        history.append(
            {
                "date": formalisation["date"],
                "action": "Formalisée par l'agent DRH",
                "user_id": formalisation.get("agent_drh_id"),
                "commentaire": formalisation.get("commentaire"),
            }
        )

    # Étape 4: Validation sortie par agent département
    validation = demande.get("validation_sortie", {})
    if validation.get("date_validation_departement"):
        history.append(
            {
                "date": validation["date_validation_departement"],
                "action": f"Sortie validée par l'agent du département - {validation.get('quantite_accordee', 0)} unités",
                "user_id": validation.get("agent_departement_id"),
                "commentaire": validation.get("commentaire"),
            }
        )

    # Étape 5: Validation sortie par agent stock
    if validation.get("date_validation_stock"):
        history.append(
            {
                "date": validation["date_validation_stock"],
                "action": f"Sortie validée par l'agent stock DRH - {validation.get('quantite_accordee', 0)} unités",
                "user_id": validation.get("agent_stock_id"),
                "commentaire": validation.get("commentaire"),
            }
        )

    # Étape 6: Traitement gestionnaire (débit stock)
    if demande.get("traitement_stock", {}).get("date"):
        traitement = demande["traitement_stock"]
        history.append(
            {
                "date": traitement["date"],
                "action": f"Stock débité - {traitement.get('quantite_accordee', 0)} unités",
                "user_id": traitement.get("gestionnaire_id"),
                "commentaire": traitement.get("commentaire"),
            }
        )

    return sorted(history, key=lambda x: x["date"] or "")
