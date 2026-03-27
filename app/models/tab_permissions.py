from datetime import datetime
from typing import Optional, List, Dict
from bson import ObjectId

from app.core.db import get_database
from app.schemas.tab_permissions import TabPermissionsConfig, TabPermissionRule

TAB_PERMISSIONS_COLLECTION = "tab_permissions"

# Liste des onglets disponibles - 5 modules essentiels uniquement
AVAILABLE_TABS = [
    {"id": "questions", "name": "Base de Connaissances & IA", "icon": "📚"},
    {"id": "credit", "name": "Analyse de Dossier de Crédit", "icon": "💳"},
    {"id": "pcb", "name": "PCB & Ratios", "icon": "📊"},
    {"id": "impayes", "name": "Gestion des Impayés", "icon": "💸"},
    {"id": "formations", "name": "Modules de Formation", "icon": "📚"},
]


async def get_tab_permissions(organization_id: str) -> Dict:
    """
    Récupère les permissions des onglets pour une organisation.
    MODE OPT-IN : Si un onglet n'existe pas dans la config → enabled=False (invisible).
    Un onglet apparaît seulement s'il est explicitement enabled=True.
    """
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        # Pas de config = tous les onglets désactivés (opt-in)
        return {
            "organization_id": organization_id,
            "tabs": [],
        }
    
    doc = await db[TAB_PERMISSIONS_COLLECTION].find_one({"organization_id": org_oid})
    
    if not doc:
        # Pas de config = tous les onglets désactivés (opt-in)
        return {
            "organization_id": organization_id,
            "tabs": [],
        }
    
    tabs = []
    for tab_config in doc.get("tabs", []):
        # S'assurer que les règles incluent tous les champs (rule_type, user_id, etc.)
        rules = []
        for rule in tab_config.get("rules", []):
            # Convertir ObjectId en string si nécessaire
            rule_dict = {
                "rule_type": rule.get("rule_type"),  # Inclure rule_type
                "department_id": str(rule.get("department_id")) if rule.get("department_id") else None,
                "service_id": str(rule.get("service_id")) if rule.get("service_id") else None,
                "role_departement": rule.get("role_departement"),
                "user_id": str(rule.get("user_id")) if rule.get("user_id") else None,  # Inclure user_id
            }
            rules.append(rule_dict)
        tabs.append({
            "tab_id": tab_config.get("tab_id"),
            "enabled": tab_config.get("enabled", False),  # Par défaut False (opt-in)
            "rules": rules,
        })
    
    return {
        "organization_id": organization_id,
        "tabs": tabs,
    }


def _get_default_permissions(organization_id: str) -> Dict:
    """
    MODE OPT-IN : Retourne une configuration vide (tous les onglets désactivés par défaut).
    Les onglets doivent être explicitement activés dans la configuration.
    """
    return {
        "organization_id": organization_id,
        "tabs": [],
    }


async def update_tab_permissions(organization_id: str, tab_id: str, config: Dict) -> Dict:
    """
    Met à jour les permissions d'un onglet spécifique.
    """
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        raise ValueError("organization_id invalide")
    
    # Récupérer ou créer la configuration
    existing = await db[TAB_PERMISSIONS_COLLECTION].find_one({"organization_id": org_oid})
    
    if not existing:
        # Créer une nouvelle configuration
        tabs = [
            {"tab_id": tab["id"], "enabled": True, "rules": []}
            for tab in AVAILABLE_TABS
        ]
        doc = {
            "organization_id": org_oid,
            "tabs": tabs,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        await db[TAB_PERMISSIONS_COLLECTION].insert_one(doc)
        existing = doc
    
    # Mettre à jour l'onglet spécifique
    tabs = existing.get("tabs", [])
    tab_found = False
    
    for i, tab in enumerate(tabs):
        if tab.get("tab_id") == tab_id:
            if "enabled" in config:
                tabs[i]["enabled"] = config["enabled"]
            if "rules" in config:
                # Convertir les règles en dict (inclure tous les champs)
                rules = []
                for rule in config["rules"]:
                    rules.append({
                        "rule_type": rule.get("rule_type"),  # Ajouter rule_type
                        "department_id": rule.get("department_id"),
                        "service_id": rule.get("service_id"),
                        "role_departement": rule.get("role_departement"),
                        "user_id": rule.get("user_id"),  # Ajouter user_id
                    })
                tabs[i]["rules"] = rules
            tab_found = True
            break
    
    if not tab_found:
        # Ajouter un nouvel onglet
        tabs.append({
            "tab_id": tab_id,
            "enabled": config.get("enabled", True),
            "rules": [
                {
                    "rule_type": rule.get("rule_type"),  # Ajouter rule_type
                    "department_id": rule.get("department_id"),
                    "service_id": rule.get("service_id"),
                    "role_departement": rule.get("role_departement"),
                    "user_id": rule.get("user_id"),  # Ajouter user_id
                }
                for rule in config.get("rules", [])
            ],
        })
    
    # Mettre à jour en base
    await db[TAB_PERMISSIONS_COLLECTION].update_one(
        {"organization_id": org_oid},
        {"$set": {"tabs": tabs, "updated_at": datetime.utcnow()}}
    )
    
    return await get_tab_permissions(organization_id)


async def get_user_allowed_tabs(
    organization_id: str,
    department_id: Optional[str],
    service_id: Optional[str],
    role_departement: Optional[str],
    user_id: Optional[str] = None,
    user_role: Optional[str] = None  # Ajouter user_role pour distinguer admin/user
) -> List[str]:
    """
    Détermine quels onglets sont autorisés pour un utilisateur donné.
    
    MODE OPT-IN pour les USERS uniquement :
    - Si user_role="admin" → retourner tous les onglets (pas de restriction)
    - Si user_role="user" ou None → appliquer le mode opt-in strict
    
    Logique pour les users (opt-in):
    1. Si l'onglet n'existe pas dans la config → enabled=False (invisible)
    2. Si l'onglet est désactivé (enabled=False), il n'est pas autorisé
    3. Si l'onglet est activé et n'a pas de règles → accès à tous
    4. Si l'onglet a des règles → l'utilisateur doit correspondre à au moins une règle
    """
    # Log pour debug
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[get_user_allowed_tabs] user_role={user_role} (type: {type(user_role)}), org_id={organization_id}")
    logger.info(f"[get_user_allowed_tabs] user_role == 'admin': {user_role == 'admin'}")
    logger.info(f"[get_user_allowed_tabs] user_role == 'user': {user_role == 'user'}")
    logger.info(f"[get_user_allowed_tabs] repr(user_role): {repr(user_role)}")
    
    # Vérification stricte : user_role doit être exactement "admin" (pas None, pas "user", etc.)
    is_admin = user_role is not None and str(user_role).strip().lower() == "admin"
    
    if is_admin:
        logger.info(f"[get_user_allowed_tabs] Admin détecté: application du mode opt-in (bootstrap dans endpoint)")
    else:
        logger.info(f"[get_user_allowed_tabs] User détecté (role={user_role}): application du mode opt-in strict")
    
    # MODE OPT-IN STRICT : Tous les utilisateurs (admin et user) passent par la même logique
    # La différence : les admins auront un bootstrap ajouté dans l'endpoint pour ne pas être bloqués
    permissions = await get_tab_permissions(organization_id)
    configured_tabs = permissions.get("tabs", [])
    logger.info(f"[get_user_allowed_tabs] Permissions récupérées: {len(configured_tabs)} onglets configurés")
    logger.info(f"[get_user_allowed_tabs] Détails: {[(t.get('tab_id'), t.get('enabled'), len(t.get('rules', []))) for t in configured_tabs]}")
    logger.info(f"[get_user_allowed_tabs] Détails des onglets configurés: {[t.get('tab_id') + ' (enabled=' + str(t.get('enabled')) + ', rules=' + str(len(t.get('rules', []))) + ')' for t in configured_tabs]}")
    
    # MODE OPT-IN STRICT : Si aucune configuration n'existe → allowed_tabs = [] (pas d'accès)
    # (Le bootstrap pour admin sera ajouté dans l'endpoint pour permettre la configuration)
    if not configured_tabs:
        logger.info(f"[get_user_allowed_tabs] ⚠️ Aucune configuration trouvée: allowed_tabs = [] (mode opt-in strict)")
        return []
    
    allowed_tabs = []
    
    # Parcourir uniquement les onglets configurés (pas tous les AVAILABLE_TABS)
    for tab_config in configured_tabs:
        tab_id = tab_config.get("tab_id")
        enabled = tab_config.get("enabled", False)  # Par défaut False (opt-in)
        
        logger.info(f"[get_user_allowed_tabs] Vérification onglet {tab_id}: enabled={enabled}")
        
        # MODE OPT-IN : Si l'onglet n'est pas explicitement activé, il n'est pas accessible
        if not enabled:
            logger.info(f"[get_user_allowed_tabs] Onglet {tab_id} désactivé, ignoré")
            continue
        
        rules = tab_config.get("rules", [])
        logger.info(f"[get_user_allowed_tabs] Onglet {tab_id} activé, règles: {len(rules)}")
        
        # MODE OPT-IN STRICT : Si pas de règles ET que c'est un user (pas admin),
        # l'onglet n'est PAS accessible (fail-closed)
        # Seuls les admins peuvent avoir accès sans règles explicites (via bootstrap dans l'endpoint)
        if not rules:
            if is_admin:
                logger.info(f"[get_user_allowed_tabs] ✅ Onglet {tab_id} ajouté (admin, pas de règles)")
                allowed_tabs.append(tab_id)
            else:
                logger.info(f"[get_user_allowed_tabs] ❌ Onglet {tab_id} IGNORÉ (user sans règles explicites - mode opt-in strict)")
            continue
        
        # Vérifier si l'utilisateur correspond à au moins une règle
        rule_matched = False
        for rule in rules:
            # Déterminer le type de règle (rétrocompatibilité : si absent, considérer comme SEGMENT)
            rule_type = rule.get("rule_type", "SEGMENT")
            
            if rule_type == "USER":
                # Règle USER : match uniquement si user_id correspond
                rule_user_id = rule.get("user_id")
                if rule_user_id and user_id and str(rule_user_id) == str(user_id):
                    allowed_tabs.append(tab_id)
                    rule_matched = True
                    break
                # Cette règle ne correspond pas, continuer à vérifier les autres règles
            
            elif rule_type == "SEGMENT" or rule_type is None:
                # Règle SEGMENT : appliquer la logique classique (department/service/role)
                rule_dept_id = rule.get("department_id")
                rule_service_id = rule.get("service_id")
                rule_role = rule.get("role_departement")
                
                # Vérifier le département (convertir en string pour comparaison)
                dept_match = (
                    rule_dept_id is None or
                    (department_id and str(rule_dept_id) == str(department_id))
                )
                
                if not dept_match:
                    continue
                
                # Vérifier le service (convertir en string pour comparaison)
                service_match = (
                    rule_service_id is None or
                    (service_id and str(rule_service_id) == str(service_id))
                )
                
                if not service_match:
                    continue
                
                # Vérifier le rôle
                role_match = (
                    rule_role is None or
                    (role_departement and rule_role == role_departement)
                )
                
                if role_match:
                    logger.info(f"[get_user_allowed_tabs] Onglet {tab_id} ajouté (règle SEGMENT match)")
                    allowed_tabs.append(tab_id)
                    rule_matched = True
                    break
    
    logger.info(f"[get_user_allowed_tabs] Total onglets autorisés: {len(allowed_tabs)}")
    return allowed_tabs

