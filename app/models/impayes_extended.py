"""
Modèles étendus pour la gestion avancée des impayés :
- Workflow d'escalade
- Promesses de paiement
- Scoring de recouvrabilité
- Attribution portefeuille agent
- Journal d'activité
- Dashboard agence avec ranking
"""
from datetime import datetime
from typing import List, Optional, Dict
from bson import ObjectId
import logging
import uuid
from app.core.db import get_database
from app.models.impayes import (
    ARREARS_SNAPSHOTS_COLLECTION,
    OUTBOUND_MESSAGES_COLLECTION,
    SMS_HISTORY_COLLECTION,
    get_available_dates_situation,
    get_statistiques_impayes,
)

logger = logging.getLogger(__name__)

# Nouvelles collections
ESCALADE_COLLECTION = "impayes_escalade"
PROMESSES_COLLECTION = "impayes_promesses"
JOURNAL_COLLECTION = "impayes_journal"
PORTEFEUILLE_COLLECTION = "impayes_portefeuille"
SCORING_CONFIG_COLLECTION = "impayes_scoring_config"
ESCALADE_CONFIG_COLLECTION = "impayes_escalade_config"

NIVEAUX_ESCALADE_ORDER = ["relance_1", "relance_2", "mise_en_demeure", "contentieux"]

DEFAULT_ESCALADE_CONFIG = {
    # Paramètres globaux
    "escalade_auto": True,
    "notifier_gestionnaire": True,
    "autoriser_forcage_manuel": True,
    "justification_forcage_obligatoire": True,
    
    # Niveaux d'escalade
    "niveaux": [
        {
            "niveau": "relance_1",
            "label": "Première relance",
            "description": "Premier rappel amiable par SMS",
            "jours_declenchement": 7,
            "couleur": "#f59e0b",
            "actions_auto": ["sms"],
            "responsable_escalade": "Agent Recouvrement 1",
            "actif": True
        },
        {
            "niveau": "relance_2",
            "label": "Deuxième relance",
            "description": "Deuxième rappel avec avertissement",
            "jours_declenchement": 30,
            "couleur": "#f97316",
            "actions_auto": ["sms"],
            "responsable_escalade": "Agent Recouvrement 2",
            "actif": True
        },
        {
            "niveau": "mise_en_demeure",
            "label": "Mise en demeure",
            "description": "Notification formelle de mise en demeure",
            "jours_declenchement": 60,
            "couleur": "#ef4444",
            "actions_auto": ["sms", "courrier"],
            "responsable_escalade": "Superviseur Recouvrement",
            "actif": True
        },
        {
            "niveau": "contentieux",
            "label": "Contentieux",
            "description": "Transfert au service contentieux / juridique",
            "jours_declenchement": 90,
            "couleur": "#7f1d1d",
            "actions_auto": ["courrier"],
            "responsable_escalade": "Responsable Juridique",
            "actif": True
        },
    ]
}


# ===================== Escalade Config =====================

async def get_escalade_config(organization_id: str) -> dict:
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return DEFAULT_ESCALADE_CONFIG

    doc = await db[ESCALADE_CONFIG_COLLECTION].find_one({"organization_id": org_oid})
    if not doc:
        return DEFAULT_ESCALADE_CONFIG

    doc.pop("_id", None)
    doc["organization_id"] = str(doc.get("organization_id", ""))
    return doc


async def save_escalade_config(organization_id: str, config: dict) -> dict:
    db = get_database()
    org_oid = ObjectId(organization_id)

    config["organization_id"] = org_oid
    config["updated_at"] = datetime.utcnow()

    await db[ESCALADE_CONFIG_COLLECTION].update_one(
        {"organization_id": org_oid},
        {"$set": config},
        upsert=True
    )
    config["organization_id"] = organization_id
    return config


# ===================== Sync Attribution Escalade =====================

async def sync_attributions_escalade(organization_id: str) -> dict:
    """
    Parcourt tous les snapshots actifs, calcule leur niveau d'escalade
    et attribue automatiquement les dossiers aux agents configurés sur chaque niveau.
    Appelée après chaque sauvegarde de la config d'escalade.
    """
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return {"synced": 0}

    config = await get_escalade_config(organization_id)
    niveaux = config.get("niveaux", [])

    # Niveaux qui ont un agent_id configuré
    niveaux_avec_agent = {n["niveau"]: n for n in niveaux if n.get("agent_id")}
    if not niveaux_avec_agent:
        return {"synced": 0}

    # Récupérer la date de situation la plus récente
    from app.models.impayes import get_available_dates_situation, ARREARS_SNAPSHOTS_COLLECTION
    dates = await get_available_dates_situation(organization_id)
    if not dates:
        return {"synced": 0}

    snapshots = await db[ARREARS_SNAPSHOTS_COLLECTION].find({
        "organization_id": org_oid,
        "date_situation": dates[0]
    }).to_list(length=10000)

    # Récupérer les escalades manuelles forcées (ne pas les écraser)
    escalade_docs = {}
    async for doc in db[ESCALADE_COLLECTION].find({"organization_id": org_oid}):
        escalade_docs[doc.get("ref_credit", "")] = doc

    # Grouper les ref_credits par agent_id cible
    attribution_map: dict = {}  # agent_id → {agent_nom, refs[]}

    for snap in snapshots:
        ref_credit = snap.get("ref_credit", "")
        jours_retard = snap.get("jours_retard", 0)

        # Respecter le forçage manuel
        escalade_manuelle = escalade_docs.get(ref_credit)
        if escalade_manuelle and escalade_manuelle.get("niveau_force"):
            niveau_id = escalade_manuelle["niveau_force"]
        else:
            niv_info = _determine_niveau_escalade(jours_retard, config)
            niveau_id = niv_info.get("niveau", "")

        if niveau_id in niveaux_avec_agent:
            niv = niveaux_avec_agent[niveau_id]
            agent_id = niv["agent_id"]
            agent_nom = niv.get("agent_nom", "Agent")
            if agent_id not in attribution_map:
                attribution_map[agent_id] = {"agent_nom": agent_nom, "refs": []}
            attribution_map[agent_id]["refs"].append(ref_credit)

    total_synced = 0
    for agent_id, info in attribution_map.items():
        if info["refs"]:
            await attribuer_credits_agent(
                organization_id=organization_id,
                agent_id=agent_id,
                agent_nom=info["agent_nom"],
                ref_credits=info["refs"],
            )
            total_synced += len(info["refs"])

    return {"synced": total_synced, "agents": len(attribution_map)}


# ===================== Escalade Dossiers =====================

def _determine_niveau_escalade(jours_retard: int, config: dict) -> dict:
    """Détermine le niveau d'escalade en fonction des jours de retard et de la configuration"""
    # Récupérer les niveaux actifs de la configuration
    niveaux = config.get("niveaux", [])
    niveaux_actifs = [n for n in niveaux if n.get("actif", False)]
    
    if not niveaux_actifs:
        # Aucun niveau actif, retourner un niveau par défaut
        return {
            "niveau": "aucun",
            "label": "Aucun niveau",
            "couleur": "#6b7280",
            "actions_auto": [],
            "responsable_escalade": None
        }
    
    # Trier par jours de déclenchement décroissant
    sorted_niveaux = sorted(niveaux_actifs, key=lambda n: n["jours_declenchement"], reverse=True)
    
    # Trouver le premier niveau qui correspond
    for niv in sorted_niveaux:
        if jours_retard >= niv["jours_declenchement"]:
            return niv
    
    # Si aucun niveau ne correspond, retourner le plus bas niveau actif
    plus_bas_niveau = min(niveaux_actifs, key=lambda n: n["jours_declenchement"])
    return plus_bas_niveau


async def get_escalade_dossiers(
    organization_id: str,
    date_situation: Optional[str] = None,
    niveau_filtre: Optional[str] = None,
    agence_filtre: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
) -> dict:
    """Récupère les dossiers avec leur niveau d'escalade calculé"""
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return {"dossiers": [], "total": 0, "stats_niveaux": {}}

    config = await get_escalade_config(organization_id)
    # Utiliser la configuration de l'organisation, avec fallback sur défaut
    if not config or not config.get("niveaux"):
        config = DEFAULT_ESCALADE_CONFIG

    query = {"organization_id": org_oid}
    if date_situation:
        query["date_situation"] = date_situation
    else:
        dates = await get_available_dates_situation(organization_id)
        if dates:
            query["date_situation"] = dates[0]

    snapshots = await db[ARREARS_SNAPSHOTS_COLLECTION].find(query).to_list(length=10000)

    # Récupérer les escalades manuelles
    escalade_docs = {}
    cursor = db[ESCALADE_COLLECTION].find({"organization_id": org_oid})
    async for doc in cursor:
        escalade_docs[doc.get("ref_credit", "")] = doc

    # Récupérer les attributions d'agents
    portefeuille_docs = {}
    cursor_pf = db[PORTEFEUILLE_COLLECTION].find({"organization_id": org_oid})
    async for doc in cursor_pf:
        for ref in doc.get("ref_credits", []):
            portefeuille_docs[ref] = {
                "agent_id": doc.get("agent_id", ""),
                "agent_nom": doc.get("agent_nom", "")
            }

    dossiers = []
    stats_niveaux = {}

    for snap in snapshots:
        ref_credit = snap.get("ref_credit", "")
        jours_retard = snap.get("jours_retard", 0)

        # Vérifier escalade manuelle
        escalade_manuelle = escalade_docs.get(ref_credit)
        if escalade_manuelle and escalade_manuelle.get("niveau_force"):
            niv_info = next(
                (n for n in config.get("niveaux", []) if n["niveau"] == escalade_manuelle["niveau_force"]),
                _determine_niveau_escalade(jours_retard, config)
            )
        else:
            niv_info = _determine_niveau_escalade(jours_retard, config)

        niveau_actuel = niv_info["niveau"]
        niveau_label = niv_info["label"]

        # Stats par niveau
        stats_niveaux[niveau_actuel] = stats_niveaux.get(niveau_actuel, 0) + 1

        # Prochain niveau (basé sur la configuration)
        niveaux_actifs = [n for n in config.get("niveaux", []) if n.get("actif", False)]
        niveaux_tries = sorted(niveaux_actifs, key=lambda n: n["jours_declenchement"])
        
        prochaine_escalade = None
        jours_avant_prochaine = None
        current_idx = next((i for i, n in enumerate(niveaux_tries) if n["niveau"] == niveau_actuel), -1)
        
        if current_idx >= 0 and current_idx < len(niveaux_tries) - 1:
            prochain_niv = niveaux_tries[current_idx + 1]
            prochaine_escalade = prochain_niv["label"]
            jours_avant_prochaine = max(0, prochain_niv["jours_declenchement"] - jours_retard)

        agent_info = portefeuille_docs.get(ref_credit, {})

        historique = []
        if escalade_manuelle:
            historique = escalade_manuelle.get("historique", [])

        dossier = {
            "ref_credit": ref_credit,
            "nom_client": snap.get("nom_client", ""),
            "niveau_actuel": niveau_actuel,
            "niveau_label": niveau_label,
            "niveau_couleur": niv_info.get("couleur", "#6b7280"),
            "responsable_escalade": niv_info.get("responsable_escalade"),
            "actions_auto": niv_info.get("actions_auto", []),
            "date_escalade": snap.get("date_situation", ""),
            "jours_retard": jours_retard,
            "montant_impaye": snap.get("montant_total_impaye", 0),
            "agence": snap.get("agence", ""),
            "segment": snap.get("segment", ""),
            "telephone": snap.get("telephone_client", ""),
            "agent_attribue": agent_info.get("agent_id"),
            "agent_nom": agent_info.get("agent_nom"),
            "historique_escalade": historique,
            "prochaine_escalade": prochaine_escalade,
            "jours_avant_prochaine": jours_avant_prochaine,
        }

        # Appliquer filtres
        if niveau_filtre and niveau_actuel != niveau_filtre:
            continue
        if agence_filtre and snap.get("agence", "") != agence_filtre:
            continue

        dossiers.append(dossier)

    # Trier par jours_retard décroissant
    dossiers.sort(key=lambda d: d["jours_retard"], reverse=True)
    total = len(dossiers)
    dossiers_page = dossiers[skip:skip + limit]

    return {
        "dossiers": dossiers_page,
        "total": total,
        "stats_niveaux": stats_niveaux,
        "niveaux_config": config.get("niveaux", [])
    }


async def escalader_manuellement(
    organization_id: str,
    ref_credit: str,
    nouveau_niveau: str,
    commentaire: Optional[str] = None,
    user_id: Optional[str] = None,
    user_nom: Optional[str] = None
) -> dict:
    """Escalade manuelle d'un dossier"""
    db = get_database()
    org_oid = ObjectId(organization_id)

    now = datetime.utcnow()
    action_entry = {
        "niveau": nouveau_niveau,
        "date": now.isoformat(),
        "commentaire": commentaire,
        "user_id": user_id,
        "user_nom": user_nom,
        "type": "manuelle"
    }

    existing = await db[ESCALADE_COLLECTION].find_one({
        "organization_id": org_oid,
        "ref_credit": ref_credit
    })

    if existing:
        await db[ESCALADE_COLLECTION].update_one(
            {"organization_id": org_oid, "ref_credit": ref_credit},
            {
                "$set": {"niveau_force": nouveau_niveau, "updated_at": now},
                "$push": {"historique": action_entry}
            }
        )
    else:
        await db[ESCALADE_COLLECTION].insert_one({
            "_id": ObjectId(),
            "organization_id": org_oid,
            "ref_credit": ref_credit,
            "niveau_force": nouveau_niveau,
            "historique": [action_entry],
            "created_at": now,
            "updated_at": now
        })

    # Attribution automatique si le niveau a un agent_id configuré
    config = await get_escalade_config(organization_id)
    niveau_config = next(
        (n for n in config.get("niveaux", []) if n.get("niveau") == nouveau_niveau),
        None
    )
    agent_attribue_nom = None
    if niveau_config and niveau_config.get("agent_id"):
        agent_id_cible = niveau_config["agent_id"]
        agent_nom_cible = niveau_config.get("agent_nom", "Agent")
        agent_attribue_nom = agent_nom_cible
        await attribuer_credits_agent(
            organization_id=organization_id,
            agent_id=agent_id_cible,
            agent_nom=agent_nom_cible,
            ref_credits=[ref_credit],
            user_id=user_id,
            user_nom=user_nom,
        )

    # Ajouter au journal
    description_journal = f"Escalade manuelle vers {nouveau_niveau}"
    if agent_attribue_nom:
        description_journal += f" — dossier attribué à {agent_attribue_nom}"
    if commentaire:
        description_journal += f" — {commentaire}"
    await add_journal_entry(
        organization_id=organization_id,
        ref_credit=ref_credit,
        type_action="escalade",
        description=description_journal,
        user_id=user_id,
        user_nom=user_nom
    )

    return {"success": True, "ref_credit": ref_credit, "nouveau_niveau": nouveau_niveau, "agent_attribue": agent_attribue_nom}


# ===================== Promesses de Paiement =====================

def _promesse_to_public(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "promesse_id": doc.get("promesse_id", ""),
        "organization_id": str(doc.get("organization_id", "")),
        "ref_credit": doc.get("ref_credit", ""),
        "nom_client": doc.get("nom_client", ""),
        "montant_promis": doc.get("montant_promis", 0),
        "montant_recu": doc.get("montant_recu"),
        "date_promesse": doc.get("date_promesse", ""),
        "date_creation": doc.get("created_at").isoformat() if isinstance(doc.get("created_at"), datetime) else str(doc.get("created_at", "")),
        "statut": doc.get("statut", "en_attente"),
        "commentaire": doc.get("commentaire"),
        "created_by": str(doc.get("created_by", "")),
        "updated_at": doc.get("updated_at").isoformat() if isinstance(doc.get("updated_at"), datetime) else None,
    }


async def create_promesse(
    organization_id: str,
    ref_credit: str,
    nom_client: str,
    montant_promis: float,
    date_promesse: str,
    commentaire: Optional[str] = None,
    user_id: Optional[str] = None,
    user_nom: Optional[str] = None
) -> dict:
    db = get_database()
    org_oid = ObjectId(organization_id)
    now = datetime.utcnow()

    doc = {
        "_id": ObjectId(),
        "promesse_id": str(uuid.uuid4()),
        "organization_id": org_oid,
        "ref_credit": ref_credit,
        "nom_client": nom_client,
        "montant_promis": montant_promis,
        "montant_recu": None,
        "date_promesse": date_promesse,
        "statut": "en_attente",
        "commentaire": commentaire,
        "created_by": ObjectId(user_id) if user_id else None,
        "created_at": now,
        "updated_at": now,
    }

    await db[PROMESSES_COLLECTION].insert_one(doc)

    # Ajouter au journal
    await add_journal_entry(
        organization_id=organization_id,
        ref_credit=ref_credit,
        type_action="promesse",
        description=f"Promesse de paiement : {montant_promis:,.0f} FCFA pour le {date_promesse}",
        montant=montant_promis,
        user_id=user_id,
        user_nom=user_nom
    )

    return _promesse_to_public(doc)


async def get_promesses(
    organization_id: str,
    ref_credit: Optional[str] = None,
    statut: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
) -> dict:
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return {"promesses": [], "total": 0}

    query = {"organization_id": org_oid}
    if ref_credit:
        query["ref_credit"] = ref_credit
    if statut:
        query["statut"] = statut

    total = await db[PROMESSES_COLLECTION].count_documents(query)
    cursor = db[PROMESSES_COLLECTION].find(query).sort("created_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)

    return {
        "promesses": [_promesse_to_public(d) for d in docs],
        "total": total
    }


async def update_promesse_statut(
    organization_id: str,
    promesse_id: str,
    statut: str,
    montant_recu: Optional[float] = None,
    commentaire: Optional[str] = None,
    user_id: Optional[str] = None,
    user_nom: Optional[str] = None
) -> Optional[dict]:
    db = get_database()
    org_oid = ObjectId(organization_id)
    now = datetime.utcnow()

    update_data = {"statut": statut, "updated_at": now}
    if montant_recu is not None:
        update_data["montant_recu"] = montant_recu
    if commentaire:
        update_data["commentaire"] = commentaire

    result = await db[PROMESSES_COLLECTION].update_one(
        {"organization_id": org_oid, "promesse_id": promesse_id},
        {"$set": update_data}
    )

    if result.matched_count == 0:
        return None

    doc = await db[PROMESSES_COLLECTION].find_one(
        {"organization_id": org_oid, "promesse_id": promesse_id}
    )

    if doc:
        # Journal
        ref_credit = doc.get("ref_credit", "")
        desc = f"Promesse mise à jour → {statut}"
        if montant_recu:
            desc += f" (reçu: {montant_recu:,.0f} FCFA)"
        await add_journal_entry(
            organization_id=organization_id,
            ref_credit=ref_credit,
            type_action="promesse",
            description=desc,
            montant=montant_recu,
            user_id=user_id,
            user_nom=user_nom
        )
        return _promesse_to_public(doc)
    return None


async def get_promesses_stats(organization_id: str) -> dict:
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return {}

    pipeline = [
        {"$match": {"organization_id": org_oid}},
        {"$group": {
            "_id": "$statut",
            "count": {"$sum": 1},
            "montant_promis": {"$sum": "$montant_promis"},
            "montant_recu": {"$sum": {"$ifNull": ["$montant_recu", 0]}},
        }}
    ]

    cursor = db[PROMESSES_COLLECTION].aggregate(pipeline)
    stats = {"total": 0, "en_attente": 0, "tenues": 0, "non_tenues": 0, "annulees": 0,
             "montant_total_promis": 0, "montant_total_recu": 0, "taux_tenue": 0}

    async for doc in cursor:
        s = doc["_id"]
        c = doc["count"]
        stats["total"] += c
        stats["montant_total_promis"] += doc["montant_promis"]
        stats["montant_total_recu"] += doc["montant_recu"]
        if s == "en_attente":
            stats["en_attente"] = c
        elif s == "tenue":
            stats["tenues"] = c
        elif s == "non_tenue":
            stats["non_tenues"] = c
        elif s == "annulee":
            stats["annulees"] = c

    resolved = stats["tenues"] + stats["non_tenues"]
    stats["taux_tenue"] = round((stats["tenues"] / resolved * 100) if resolved > 0 else 0, 1)

    return stats


async def verifier_promesses_echues(organization_id: str) -> List[dict]:
    """Vérifie et marque les promesses en attente dont la date est dépassée"""
    db = get_database()
    org_oid = ObjectId(organization_id)
    today = datetime.utcnow().strftime("%Y-%m-%d")

    cursor = db[PROMESSES_COLLECTION].find({
        "organization_id": org_oid,
        "statut": "en_attente",
        "date_promesse": {"$lt": today}
    })

    echues = []
    async for doc in cursor:
        await db[PROMESSES_COLLECTION].update_one(
            {"_id": doc["_id"]},
            {"$set": {"statut": "non_tenue", "updated_at": datetime.utcnow()}}
        )
        echues.append(_promesse_to_public(doc))

    return echues


# ===================== Scoring de Recouvrabilité =====================

DEFAULT_SCORING_CONFIG = {
    "poids": {
        "jours_retard": 0.30, "ratio_impaye": 0.20, "garanties": 0.15,
        "joignabilite": 0.10, "historique_promesses": 0.15, "echeances_impayees": 0.10
    },
    "seuils_jours_retard": {
        "palier_1_jours": 15, "palier_1_score": 90,
        "palier_2_jours": 30, "palier_2_score": 75,
        "palier_3_jours": 60, "palier_3_score": 50,
        "palier_4_jours": 90, "palier_4_score": 30,
        "palier_5_jours": 180, "palier_5_score": 15,
        "palier_6_score": 5
    },
    "seuils_ratio_impaye": {
        "palier_1_pct": 10, "palier_1_score": 90,
        "palier_2_pct": 25, "palier_2_score": 70,
        "palier_3_pct": 50, "palier_3_score": 45,
        "palier_4_pct": 75, "palier_4_score": 20,
        "palier_5_score": 5
    },
    "seuils_echeances": {
        "palier_1_nb": 1, "palier_1_score": 90,
        "palier_2_nb": 3, "palier_2_score": 65,
        "palier_3_nb": 6, "palier_3_score": 35,
        "palier_4_score": 10
    },
    "scores_garanties": {"avec_garantie": 80, "sans_garantie": 20},
    "scores_joignabilite": {"avec_telephone": 80, "sans_telephone": 20},
    "seuils_niveaux": {
        "faible": 70, "moyen": 50, "eleve": 30,
        "recommandation_faible": "Relance amiable par SMS, forte probabilité de régularisation",
        "recommandation_moyen": "Relance téléphonique recommandée, négocier un échéancier",
        "recommandation_eleve": "Mise en demeure à envisager, visite terrain si possible",
        "recommandation_critique": "Risque de perte élevé, envisager contentieux ou passage en perte"
    }
}


async def get_scoring_config(organization_id: str) -> dict:
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return DEFAULT_SCORING_CONFIG.copy()
    doc = await db[SCORING_CONFIG_COLLECTION].find_one({"organization_id": org_oid})
    if doc:
        doc.pop("_id", None)
        doc.pop("organization_id", None)
        return doc
    return DEFAULT_SCORING_CONFIG.copy()


async def save_scoring_config(organization_id: str, config: dict) -> dict:
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        raise ValueError("organization_id invalide")
    await db[SCORING_CONFIG_COLLECTION].update_one(
        {"organization_id": org_oid},
        {"$set": {**config, "organization_id": org_oid}},
        upsert=True
    )
    return config


def _score_paliers_jours(jours: int, s: dict) -> int:
    if jours <= s["palier_1_jours"]: return s["palier_1_score"]
    if jours <= s["palier_2_jours"]: return s["palier_2_score"]
    if jours <= s["palier_3_jours"]: return s["palier_3_score"]
    if jours <= s["palier_4_jours"]: return s["palier_4_score"]
    if jours <= s["palier_5_jours"]: return s["palier_5_score"]
    return s["palier_6_score"]


def _score_paliers_ratio(ratio: float, s: dict) -> int:
    if ratio <= s["palier_1_pct"]: return s["palier_1_score"]
    if ratio <= s["palier_2_pct"]: return s["palier_2_score"]
    if ratio <= s["palier_3_pct"]: return s["palier_3_score"]
    if ratio <= s["palier_4_pct"]: return s["palier_4_score"]
    return s["palier_5_score"]


def _score_paliers_echeances(nb: int, s: dict) -> int:
    if nb <= s["palier_1_nb"]: return s["palier_1_score"]
    if nb <= s["palier_2_nb"]: return s["palier_2_score"]
    if nb <= s["palier_3_nb"]: return s["palier_3_score"]
    return s["palier_4_score"]


async def calculer_scores_recouvrabilite(
    organization_id: str,
    date_situation: Optional[str] = None
) -> List[dict]:
    """Calcule le score de recouvrabilité pour chaque dossier (configurable par organisation)"""
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return []

    cfg = await get_scoring_config(organization_id)
    poids = cfg.get("poids", DEFAULT_SCORING_CONFIG["poids"])
    s_jours = cfg.get("seuils_jours_retard", DEFAULT_SCORING_CONFIG["seuils_jours_retard"])
    s_ratio = cfg.get("seuils_ratio_impaye", DEFAULT_SCORING_CONFIG["seuils_ratio_impaye"])
    s_ech = cfg.get("seuils_echeances", DEFAULT_SCORING_CONFIG["seuils_echeances"])
    s_gar = cfg.get("scores_garanties", DEFAULT_SCORING_CONFIG["scores_garanties"])
    s_join = cfg.get("scores_joignabilite", DEFAULT_SCORING_CONFIG["scores_joignabilite"])
    s_niv = cfg.get("seuils_niveaux", DEFAULT_SCORING_CONFIG["seuils_niveaux"])

    query = {"organization_id": org_oid}
    if date_situation:
        query["date_situation"] = date_situation
    else:
        dates = await get_available_dates_situation(organization_id)
        if dates:
            query["date_situation"] = dates[0]

    snapshots = await db[ARREARS_SNAPSHOTS_COLLECTION].find(query).to_list(length=10000)

    promesses_tenues = {}
    cursor_p = db[PROMESSES_COLLECTION].find({"organization_id": org_oid, "statut": "tenue"})
    async for doc in cursor_p:
        ref = doc.get("ref_credit", "")
        promesses_tenues[ref] = promesses_tenues.get(ref, 0) + 1

    promesses_non_tenues = {}
    cursor_pn = db[PROMESSES_COLLECTION].find({"organization_id": org_oid, "statut": "non_tenue"})
    async for doc in cursor_pn:
        ref = doc.get("ref_credit", "")
        promesses_non_tenues[ref] = promesses_non_tenues.get(ref, 0) + 1

    scores = []
    for snap in snapshots:
        ref = snap.get("ref_credit", "")
        jours_retard = snap.get("jours_retard", 0)
        montant_impaye = snap.get("montant_total_impaye", 0)
        ratio = snap.get("ratio_impaye_encours", 0)
        garanties = snap.get("garanties", "")
        has_telephone = bool(snap.get("telephone_client"))
        nb_echeances = snap.get("nb_echeances_impayees", 0)
        pt = promesses_tenues.get(ref, 0)
        pnt = promesses_non_tenues.get(ref, 0)

        facteurs = {
            "jours_retard": _score_paliers_jours(jours_retard, s_jours),
            "ratio_impaye": _score_paliers_ratio(ratio, s_ratio),
            "garanties": s_gar["avec_garantie"] if (garanties and str(garanties).strip()) else s_gar["sans_garantie"],
            "joignabilite": s_join["avec_telephone"] if has_telephone else s_join["sans_telephone"],
            "historique_promesses": 50 if (pt + pnt == 0) else min(95, max(5, int(pt / (pt + pnt) * 100))),
            "echeances_impayees": _score_paliers_echeances(nb_echeances, s_ech),
        }

        score = round(
            facteurs["jours_retard"] * poids.get("jours_retard", 0.30) +
            facteurs["ratio_impaye"] * poids.get("ratio_impaye", 0.20) +
            facteurs["garanties"] * poids.get("garanties", 0.15) +
            facteurs["joignabilite"] * poids.get("joignabilite", 0.10) +
            facteurs["historique_promesses"] * poids.get("historique_promesses", 0.15) +
            facteurs["echeances_impayees"] * poids.get("echeances_impayees", 0.10),
            1
        )

        seuil_faible = s_niv.get("faible", 70)
        seuil_moyen = s_niv.get("moyen", 50)
        seuil_eleve = s_niv.get("eleve", 30)

        if score >= seuil_faible:
            niveau_risque = "faible"
            couleur = "#22c55e"
            recommandation = s_niv.get("recommandation_faible", DEFAULT_SCORING_CONFIG["seuils_niveaux"]["recommandation_faible"])
        elif score >= seuil_moyen:
            niveau_risque = "moyen"
            couleur = "#f59e0b"
            recommandation = s_niv.get("recommandation_moyen", DEFAULT_SCORING_CONFIG["seuils_niveaux"]["recommandation_moyen"])
        elif score >= seuil_eleve:
            niveau_risque = "eleve"
            couleur = "#ef4444"
            recommandation = s_niv.get("recommandation_eleve", DEFAULT_SCORING_CONFIG["seuils_niveaux"]["recommandation_eleve"])
        else:
            niveau_risque = "critique"
            couleur = "#7f1d1d"
            recommandation = s_niv.get("recommandation_critique", DEFAULT_SCORING_CONFIG["seuils_niveaux"]["recommandation_critique"])

        scores.append({
            "ref_credit": ref,
            "nom_client": snap.get("nom_client", ""),
            "score": score,
            "niveau_risque": niveau_risque,
            "couleur": couleur,
            "facteurs": facteurs,
            "recommandation": recommandation,
            "montant_impaye": montant_impaye,
            "jours_retard": jours_retard,
            "agence": snap.get("agence", ""),
            "segment": snap.get("segment", ""),
        })

    scores.sort(key=lambda s: s["score"])
    return scores


# ===================== Attribution Portefeuille Agent =====================

async def attribuer_credits_agent(
    organization_id: str,
    agent_id: str,
    agent_nom: str,
    ref_credits: List[str],
    department_id: Optional[str] = None,
    service_id: Optional[str] = None,
    user_id: Optional[str] = None,
    user_nom: Optional[str] = None
) -> dict:
    db = get_database()
    org_oid = ObjectId(organization_id)
    now = datetime.utcnow()

    # Retirer ces crédits d'autres agents
    await db[PORTEFEUILLE_COLLECTION].update_many(
        {"organization_id": org_oid},
        {"$pull": {"ref_credits": {"$in": ref_credits}}}
    )

    # Ajouter/mettre à jour le portefeuille de l'agent
    existing = await db[PORTEFEUILLE_COLLECTION].find_one({
        "organization_id": org_oid,
        "agent_id": agent_id
    })

    if existing:
        existing_refs = set(existing.get("ref_credits", []))
        existing_refs.update(ref_credits)
        update_data = {
            "ref_credits": list(existing_refs),
            "agent_nom": agent_nom,
            "updated_at": now
        }
        if department_id:
            update_data["department_id"] = department_id
        if service_id:
            update_data["service_id"] = service_id
            
        await db[PORTEFEUILLE_COLLECTION].update_one(
            {"organization_id": org_oid, "agent_id": agent_id},
            {"$set": update_data}
        )
    else:
        portfolio_data = {
            "_id": ObjectId(),
            "organization_id": org_oid,
            "agent_id": agent_id,
            "agent_nom": agent_nom,
            "ref_credits": ref_credits,
            "created_at": now,
            "updated_at": now
        }
        if department_id:
            portfolio_data["department_id"] = department_id
        if service_id:
            portfolio_data["service_id"] = service_id
            
        await db[PORTEFEUILLE_COLLECTION].insert_one(portfolio_data)

    # Journal pour chaque crédit
    for ref in ref_credits:
        await add_journal_entry(
            organization_id=organization_id,
            ref_credit=ref,
            type_action="attribution",
            description=f"Dossier attribué à {agent_nom}",
            user_id=user_id,
            user_nom=user_nom
        )

    return {"success": True, "agent_id": agent_id, "agent_nom": agent_nom, "nb_credits": len(ref_credits)}


async def get_portefeuilles_agents(
    organization_id: str,
    date_situation: Optional[str] = None,
    agent_id: Optional[str] = None
) -> List[dict]:
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return []

    # Récupérer les portefeuilles (avec filtre agent_id si fourni)
    query = {"organization_id": org_oid}
    if agent_id:
        query["agent_id"] = agent_id
    cursor = db[PORTEFEUILLE_COLLECTION].find(query)
    portefeuilles = await cursor.to_list(length=100)

    # Récupérer les snapshots pour les montants
    query_snap = {"organization_id": org_oid}
    if date_situation:
        query_snap["date_situation"] = date_situation
    else:
        dates = await get_available_dates_situation(organization_id)
        if dates:
            query_snap["date_situation"] = dates[0]

    snapshots = await db[ARREARS_SNAPSHOTS_COLLECTION].find(query_snap).to_list(length=10000)
    snap_by_ref = {s.get("ref_credit", ""): s for s in snapshots}

    # Promesses stats par agent
    promesses_all = await db[PROMESSES_COLLECTION].find({"organization_id": org_oid}).to_list(length=10000)
    promesses_by_ref = {}
    for p in promesses_all:
        ref = p.get("ref_credit", "")
        if ref not in promesses_by_ref:
            promesses_by_ref[ref] = []
        promesses_by_ref[ref].append(p)

    result = []
    for pf in portefeuilles:
        refs = pf.get("ref_credits", [])
        dossiers = []
        montant_total = 0
        promesses_en_cours = 0

        for ref in refs:
            snap = snap_by_ref.get(ref)
            if snap:
                montant = snap.get("montant_total_impaye", 0)
                montant_total += montant
                dossiers.append({
                    "ref_credit": ref,
                    "nom_client": snap.get("nom_client", ""),
                    "montant_impaye": montant,
                    "jours_retard": snap.get("jours_retard", 0),
                    "agence": snap.get("agence", ""),
                })
            # Promesses en cours
            for pm in promesses_by_ref.get(ref, []):
                if pm.get("statut") == "en_attente":
                    promesses_en_cours += 1

        result.append({
            "agent_id": pf.get("agent_id", ""),
            "agent_nom": pf.get("agent_nom", ""),
            "nombre_dossiers": len(dossiers),
            "montant_total": montant_total,
            "dossiers": dossiers,
            "promesses_en_cours": promesses_en_cours,
        })

    return result


async def desattribuer_credits(
    organization_id: str,
    agent_id: str,
    ref_credits: List[str]
) -> dict:
    db = get_database()
    org_oid = ObjectId(organization_id)

    await db[PORTEFEUILLE_COLLECTION].update_one(
        {"organization_id": org_oid, "agent_id": agent_id},
        {"$pull": {"ref_credits": {"$in": ref_credits}}}
    )

    return {"success": True, "nb_retires": len(ref_credits)}


# ===================== Journal d'Activité =====================

async def add_journal_entry(
    organization_id: str,
    ref_credit: str,
    type_action: str,
    description: str,
    montant: Optional[float] = None,
    resultat: Optional[str] = None,
    user_id: Optional[str] = None,
    user_nom: Optional[str] = None
) -> dict:
    db = get_database()
    org_oid = ObjectId(organization_id)
    now = datetime.utcnow()

    # Récupérer le nom du client
    snap = await db[ARREARS_SNAPSHOTS_COLLECTION].find_one({
        "organization_id": org_oid,
        "ref_credit": ref_credit
    })
    nom_client = snap.get("nom_client", "") if snap else ""

    doc = {
        "_id": ObjectId(),
        "action_id": str(uuid.uuid4()),
        "organization_id": org_oid,
        "ref_credit": ref_credit,
        "nom_client": nom_client,
        "type_action": type_action,
        "description": description,
        "montant": montant,
        "resultat": resultat,
        "created_by": ObjectId(user_id) if user_id else None,
        "created_by_nom": user_nom,
        "created_at": now,
    }

    await db[JOURNAL_COLLECTION].insert_one(doc)
    return _journal_to_public(doc)


def _journal_to_public(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "action_id": doc.get("action_id", ""),
        "organization_id": str(doc.get("organization_id", "")),
        "ref_credit": doc.get("ref_credit", ""),
        "nom_client": doc.get("nom_client"),
        "type_action": doc.get("type_action", ""),
        "description": doc.get("description", ""),
        "montant": doc.get("montant"),
        "resultat": doc.get("resultat"),
        "created_by": str(doc.get("created_by", "")),
        "created_by_nom": doc.get("created_by_nom"),
        "created_at": doc.get("created_at").isoformat() if isinstance(doc.get("created_at"), datetime) else str(doc.get("created_at", "")),
    }


async def get_journal(
    organization_id: str,
    ref_credit: Optional[str] = None,
    type_action: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
) -> dict:
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return {"actions": [], "total": 0}

    query = {"organization_id": org_oid}
    if ref_credit:
        query["ref_credit"] = ref_credit
    if type_action:
        query["type_action"] = type_action

    cursor = db[JOURNAL_COLLECTION].find(query).sort("created_at", -1).limit(500)
    docs = await cursor.to_list(length=500)
    actions = [_journal_to_public(d) for d in docs]

    # Inclure les SMS envoyés (outbound_messages + sms_history) si on filtre par ref_credit
    if ref_credit and not type_action:
        sms_query = {"organization_id": org_oid, "linked_credit": ref_credit}

        # SMS actuels (PENDING/SENT/FAILED)
        sms_cursor = db[OUTBOUND_MESSAGES_COLLECTION].find(sms_query).sort("created_at", -1).limit(200)
        sms_docs = await sms_cursor.to_list(length=200)

        # SMS archivés (historique)
        hist_cursor = db[SMS_HISTORY_COLLECTION].find(sms_query).sort("created_at", -1).limit(200)
        hist_docs = await hist_cursor.to_list(length=200)

        seen_ids = set()
        for sms in sms_docs + hist_docs:
            mid = sms.get("message_id", str(sms.get("_id", "")))
            if mid in seen_ids:
                continue
            seen_ids.add(mid)
            created_at = sms.get("created_at")
            actions.append({
                "id": str(sms.get("_id", "")),
                "action_id": mid,
                "organization_id": organization_id,
                "ref_credit": ref_credit,
                "nom_client": None,
                "type_action": "sms",
                "description": f"SMS envoyé au {sms.get('to', '—')} — statut : {sms.get('status', '?')}",
                "corps_sms": sms.get("body", ""),
                "statut_sms": sms.get("status", ""),
                "telephone": sms.get("to", ""),
                "montant": None,
                "resultat": "succes" if sms.get("status") == "SENT" else ("echec" if sms.get("status") == "FAILED" else "en_attente"),
                "created_by": None,
                "created_by_nom": "Système",
                "created_at": created_at.isoformat() if isinstance(created_at, datetime) else str(created_at or ""),
            })

        # Trier toutes les actions par date décroissante
        actions.sort(key=lambda a: a.get("created_at", ""), reverse=True)

    total = len(actions)
    return {
        "actions": actions[skip:skip + limit],
        "total": total
    }


# ===================== Dashboard Agence avec Ranking =====================

async def get_dashboard_agences(
    organization_id: str,
    date_situation: Optional[str] = None
) -> dict:
    """Dashboard par agence avec ranking"""
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return {"agences": [], "ranking": []}

    query = {"organization_id": org_oid}
    if date_situation:
        query["date_situation"] = date_situation
    else:
        dates = await get_available_dates_situation(organization_id)
        if dates:
            query["date_situation"] = dates[0]

    snapshots = await db[ARREARS_SNAPSHOTS_COLLECTION].find(query).to_list(length=10000)

    # Grouper par agence
    agences_data: Dict[str, dict] = {}
    for snap in snapshots:
        agence = snap.get("agence", "Inconnue")
        if agence not in agences_data:
            agences_data[agence] = {
                "agence": agence,
                "total_credits": 0,
                "montant_total_impaye": 0,
                "repartition_tranches": {},
                "jours_retard_total": 0,
            }
        ad = agences_data[agence]
        ad["total_credits"] += 1
        ad["montant_total_impaye"] += snap.get("montant_total_impaye", 0)
        ad["jours_retard_total"] += snap.get("jours_retard", 0)
        bucket = snap.get("bucket_retard", "Inconnu")
        ad["repartition_tranches"][bucket] = ad["repartition_tranches"].get(bucket, 0) + 1

    # Récupérer les promesses stats par agence
    promesses = await db[PROMESSES_COLLECTION].find({"organization_id": org_oid}).to_list(length=10000)
    # Mapping ref_credit -> agence via snapshots
    ref_to_agence = {s.get("ref_credit", ""): s.get("agence", "Inconnue") for s in snapshots}

    promesses_par_agence: Dict[str, dict] = {}
    for p in promesses:
        agence = ref_to_agence.get(p.get("ref_credit", ""), "Inconnue")
        if agence not in promesses_par_agence:
            promesses_par_agence[agence] = {"tenues": 0, "non_tenues": 0, "en_attente": 0, "montant_recu": 0}
        statut = p.get("statut", "")
        if statut == "tenue":
            promesses_par_agence[agence]["tenues"] += 1
            promesses_par_agence[agence]["montant_recu"] += p.get("montant_recu", 0) or 0
        elif statut == "non_tenue":
            promesses_par_agence[agence]["non_tenues"] += 1
        elif statut == "en_attente":
            promesses_par_agence[agence]["en_attente"] += 1

    # Calcul du score de performance par agence
    ranking = []
    for agence, data in agences_data.items():
        prom = promesses_par_agence.get(agence, {})
        tenues = prom.get("tenues", 0)
        non_tenues = prom.get("non_tenues", 0)
        montant_recouvre = prom.get("montant_recu", 0)
        montant_impaye = data["montant_total_impaye"]

        taux_recouvrement = round((montant_recouvre / montant_impaye * 100) if montant_impaye > 0 else 0, 1)

        # Score = pondération de plusieurs facteurs
        score_taux = min(taux_recouvrement, 100)
        score_promesses = (tenues / (tenues + non_tenues) * 100) if (tenues + non_tenues) > 0 else 50
        retard_moyen = data["jours_retard_total"] / data["total_credits"] if data["total_credits"] > 0 else 0
        score_retard = max(0, 100 - retard_moyen)

        score_performance = round(score_taux * 0.5 + score_promesses * 0.3 + score_retard * 0.2, 1)

        ranking.append({
            "agence": agence,
            "rang": 0,
            "total_credits": data["total_credits"],
            "montant_total_impaye": round(montant_impaye, 0),
            "montant_recouvre": round(montant_recouvre, 0),
            "taux_recouvrement": taux_recouvrement,
            "promesses_tenues": tenues,
            "promesses_non_tenues": non_tenues,
            "score_performance": score_performance,
            "repartition_tranches": data["repartition_tranches"],
        })

    # Trier par score décroissant et attribuer les rangs
    ranking.sort(key=lambda r: r["score_performance"], reverse=True)
    for i, r in enumerate(ranking):
        r["rang"] = i + 1

    return {
        "agences": list(agences_data.values()),
        "ranking": ranking,
        "total_agences": len(agences_data),
    }


# ===================== Evolution temporelle pour graphiques =====================

async def get_evolution_temporelle(
    organization_id: str,
    limit: int = 12
) -> dict:
    """Récupère les données d'évolution pour les graphiques"""
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return {"evolution_montant": [], "evolution_credits": [], "evolution_tranches": []}

    dates = await get_available_dates_situation(organization_id)
    dates = dates[:limit]
    dates.reverse()  # Ordre chronologique

    evolution_montant = []
    evolution_credits = []
    evolution_tranches = []

    for date_sit in dates:
        stats = await get_statistiques_impayes(organization_id, date_sit)
        evolution_montant.append({
            "date": date_sit,
            "montant": stats.get("total_montant_impaye", 0),
        })
        evolution_credits.append({
            "date": date_sit,
            "credits": stats.get("total_credits", 0),
        })
        evolution_tranches.append({
            "date": date_sit,
            "tranches": stats.get("repartition_tranches", {}),
        })

    return {
        "evolution_montant": evolution_montant,
        "evolution_credits": evolution_credits,
        "evolution_tranches": evolution_tranches,
    }


# ===================== Validation Configuration Escalade =====================

def _validate_escalade_config(config: dict) -> tuple[bool, list[str]]:
    """Valide une configuration d'escalade et retourne (valide, erreurs)"""
    erreurs = []
    
    # Vérifier les paramètres globaux
    parametres_globaux = ["escalade_auto", "notifier_gestionnaire", "autoriser_forcage_manuel", "justification_forcage_obligatoire"]
    for param in parametres_globaux:
        if param not in config or not isinstance(config[param], bool):
            erreurs.append(f"Le paramètre '{param}' doit être un booléen")
    
    # Vérifier les niveaux
    niveaux = config.get("niveaux", [])
    if not niveaux:
        erreurs.append("Au moins un niveau d'escalade doit être configuré")
        return False, erreurs
    
    # Vérifier qu'il y a au moins un niveau actif
    niveaux_actifs = [n for n in niveaux if n.get("actif", False)]
    if not niveaux_actifs:
        erreurs.append("Au moins un niveau doit être actif")
    
    # Vérifier les doublons de niveau
    niveaux_ids = [n.get("niveau") for n in niveaux if n.get("niveau")]
    if len(niveaux_ids) != len(set(niveaux_ids)):
        erreurs.append("Les identifiants de niveau doivent être uniques")
    
    # Vérifier l'ordre croissant des jours de déclenchement
    niveaux_tries = sorted(niveaux, key=lambda n: n.get("jours_declenchement", 0))
    for i, niveau in enumerate(niveaux_tries):
        if i > 0 and niveau.get("jours_declenchement", 0) <= niveaux_tries[i-1].get("jours_declenchement", 0):
            erreurs.append(f"Les jours de déclenchement doivent être croissants: '{niveau.get('label')}'")
    
    # Vérifier chaque niveau
    actions_autorisees = ["sms", "email", "courrier", "notification_app", "appel"]
    for niveau in niveaux:
        # Champs obligatoires
        champs_obligatoires = ["niveau", "label", "jours_declenchement", "couleur"]
        for champ in champs_obligatoires:
            if not niveau.get(champ):
                erreurs.append(f"Le champ '{champ}' est obligatoire pour le niveau '{niveau.get('label', 'sans nom')}'")
        
        # Validation des jours
        jours = niveau.get("jours_declenchement", 0)
        if not isinstance(jours, int) or jours <= 0:
            erreurs.append(f"Les jours de déclenchement doivent être un entier positif pour '{niveau.get('label', 'sans nom')}'")
        
        # Validation de la couleur
        couleur = niveau.get("couleur", "")
        if not couleur or not couleur.startswith("#") or len(couleur) != 7:
            erreurs.append(f"La couleur doit être au format hex (#RRGGBB) pour '{niveau.get('label', 'sans nom')}'")
        
        # Validation des actions
        actions = niveau.get("actions_auto", [])
        for action in actions:
            if action not in actions_autorisees:
                erreurs.append(f"L'action '{action}' n'est pas autorisée pour '{niveau.get('label', 'sans nom')}'")
    
    return len(erreurs) == 0, erreurs


async def save_escalade_config_with_validation(organization_id: str, config: dict) -> tuple[bool, dict, list[str]]:
    """Sauvegarde la configuration avec validation"""
    # Valider la configuration
    valide, erreurs = _validate_escalade_config(config)
    
    if not valide:
        return False, {}, erreurs
    
    # Si valide, sauvegarder
    try:
        result = await save_escalade_config(organization_id, config)
        return True, result, []
    except Exception as e:
        return False, {}, [f"Erreur lors de la sauvegarde: {str(e)}"]


def get_responsable_for_niveau(config: dict, niveau_id: str) -> Optional[str]:
    """Récupère le responsable pour un niveau donné"""
    niveaux = config.get("niveaux", [])
    for niveau in niveaux:
        if niveau.get("niveau") == niveau_id and niveau.get("actif", False):
            return niveau.get("responsable_escalade")
    return None


def get_actions_for_niveau(config: dict, niveau_id: str) -> List[str]:
    """Récupère les actions automatiques pour un niveau donné"""
    niveaux = config.get("niveaux", [])
    for niveau in niveaux:
        if niveau.get("niveau") == niveau_id and niveau.get("actif", False):
            return niveau.get("actions_auto", [])
    return []


def get_couleur_for_niveau(config: dict, niveau_id: str) -> str:
    """Récupère la couleur pour un niveau donné"""
    niveaux = config.get("niveaux", [])
    for niveau in niveaux:
        if niveau.get("niveau") == niveau_id and niveau.get("actif", False):
            return niveau.get("couleur", "#6b7280")
    return "#6b7280"
