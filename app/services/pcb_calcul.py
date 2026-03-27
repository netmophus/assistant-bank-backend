"""
Service de calcul des soldes de postes réglementaires et génération de rapports
"""
import os
import logging
from typing import List, Dict, Optional
from datetime import datetime
from app.models.pcb import (
    list_gl_accounts,
    list_postes_reglementaires,
    get_latest_gl_soldes,
    get_gl_account_by_code
)


logger = logging.getLogger("uvicorn.error")
_PCB_CALC_DEBUG = os.getenv("PCB_CALC_DEBUG", "").strip() in {"1", "true", "True", "yes", "YES"}

if _PCB_CALC_DEBUG:
    msg = f"[PCB_CALC] DEBUG ENABLED (PCB_CALC_DEBUG={os.getenv('PCB_CALC_DEBUG')})"
    logger.info(msg)
    print(msg)


def _dbg(msg: str) -> None:
    if _PCB_CALC_DEBUG:
        logger.info(msg)
        print(msg)


def _precedence(op: str) -> int:
    if op in ["*", "/"]:
        return 2
    return 1


def _apply_op(a: float, op: str, b: float) -> float:
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        if b == 0:
            return 0.0
        return a / b
    return a


def _eval_infix_tokens(tokens: List[object]) -> float:
    """Évalue une expression infixée (nombres + opérateurs + parenthèses)."""
    values: List[float] = []
    ops: List[str] = []

    def apply_top() -> None:
        if not ops or len(values) < 2:
            return
        op = ops.pop()
        b = values.pop()
        a = values.pop()
        values.append(_apply_op(a, op, b))

    for tok in tokens:
        if isinstance(tok, (int, float)):
            values.append(float(tok))
            continue

        if tok == "(":
            ops.append("(")
            continue
        if tok == ")":
            while ops and ops[-1] != "(":
                apply_top()
            if ops and ops[-1] == "(":
                ops.pop()
            continue

        if tok in ["+", "-", "*", "/"]:
            while ops and ops[-1] != "(" and _precedence(str(ops[-1])) >= _precedence(str(tok)):
                apply_top()
            ops.append(str(tok))

    while ops:
        if ops[-1] == "(":
            ops.pop()
            continue
        apply_top()

    return float(values[0]) if values else 0.0


async def calculer_solde_poste(
    poste: dict,
    organization_id: str,
    date_solde: Optional[datetime] = None
) -> Dict:
    """
    Calcule le solde d'un poste réglementaire en fonction des GL associés
    
    Retourne:
    {
        "solde_brut": float,  # Solde brut (peut être négatif)
        "solde_affiche": float,  # Solde affiché (toujours positif: abs(solde_brut))
        "warning_signe": bool,  # True si solde_brut < 0 (signe inversé)
        "gl_details": List[dict]  # Détails de chaque GL contribuant (inclut basis, valeur_base, contribution)
    }
    """
    gl_details = []
    solde_total_brut = 0.0
    
    # Récupérer les soldes GL les plus récents
    if date_solde:
        # Récupérer les GL à une date spécifique
        gl_accounts = await list_gl_accounts(organization_id, {"date_solde": date_solde})
    else:
        # Récupérer les soldes les plus récents
        gl_accounts = await get_latest_gl_soldes(organization_id)
    
    # Créer un dictionnaire pour accès rapide
    gl_dict = {gl["code"]: gl for gl in gl_accounts}
    
    # Traiter chaque GL associé au poste
    for gl_mapping in poste.get("gl_codes", []):
        gl_code = gl_mapping.get("code", "")
        signe = gl_mapping.get("signe", "+")
        basis = gl_mapping.get("basis", "NET")  # NET par défaut pour compatibilité
        
        if not gl_code:
            continue
        
        # Gérer les patterns
        gl_codes_to_process = []
        
        if "*" in gl_code:
            # Pattern par préfixe (ex: 411*)
            prefix = gl_code.replace("*", "")
            gl_codes_to_process = [code for code in gl_dict.keys() if code.startswith(prefix)]
        elif gl_code.startswith("Classe "):
            # Pattern par classe (ex: Classe 4)
            try:
                classe_num = int(gl_code.split()[-1])
                gl_codes_to_process = [
                    code for code, gl in gl_dict.items()
                    if gl.get("classe") == classe_num
                ]
            except:
                gl_codes_to_process = []
        elif "-" in gl_code and len(gl_code.split("-")) == 2:
            # Pattern par plage (ex: 4111-4119)
            start, end = gl_code.split("-")
            try:
                start_num = int(start.strip())
                end_num = int(end.strip())
                gl_codes_to_process = [
                    code for code in gl_dict.keys()
                    if code.isdigit() and start_num <= int(code) <= end_num
                ]
            except:
                gl_codes_to_process = []
        else:
            # Code exact - peut contenir plusieurs codes séparés par des virgules
            gl_code_clean = gl_code.strip()
            
            # Vérifier si c'est plusieurs codes séparés par des virgules
            if "," in gl_code_clean:
                codes_list = [c.strip() for c in gl_code_clean.split(",") if c.strip()]
                gl_codes_to_process = [code for code in codes_list if code in gl_dict]
            else:
                gl_codes_to_process = [gl_code_clean] if gl_code_clean in gl_dict else []
        
        # Si aucun GL trouvé, ajouter quand même dans les détails pour debug
        if not gl_codes_to_process:
            gl_details.append({
                "code": gl_code,
                "libelle": f"⚠️ GL non trouvé dans les comptes importés",
                "solde": 0,
                "signe": signe,
                "contribution": 0,
                "pattern": gl_code
            })
            continue
        
        # Calculer la contribution de chaque GL
        for code in gl_codes_to_process:
            if code in gl_dict:
                gl_account = gl_dict[code]
                solde_debit = gl_account.get("solde_debit", 0)
                solde_credit = gl_account.get("solde_credit", 0)
                # NET dépend du type de poste:
                # - Actif / Charges : Débit - Crédit
                # - Passif / Produits / Hors bilan : Crédit - Débit
                poste_type = poste.get("type")
                if poste_type in ["bilan_actif", "cr_charge"]:
                    solde_net = float(solde_debit or 0) - float(solde_credit or 0)
                else:
                    solde_net = float(solde_credit or 0) - float(solde_debit or 0)
                
                # Déterminer la valeur de base selon basis
                if basis == "DEBIT":
                    valeur_base = solde_debit
                elif basis == "CREDIT":
                    valeur_base = solde_credit
                else:  # NET (par défaut)
                    valeur_base = solde_net
                
                # Appliquer le signe
                if signe == "+":
                    contribution = valeur_base
                else:
                    contribution = -valeur_base
                
                solde_total_brut += contribution
                
                gl_details.append({
                    "code": code,
                    "libelle": gl_account.get("libelle", ""),
                    "basis": basis,
                    "valeur_base": valeur_base,
                    "solde_debit": solde_debit,
                    "solde_credit": solde_credit,
                    "solde_net": solde_net,
                    "signe": signe,
                    "contribution": contribution,
                    "pattern": gl_code if gl_code != code else None
                })
            else:
                # GL non trouvé même après pattern matching
                gl_details.append({
                    "code": code,
                    "libelle": f"⚠️ GL {code} non trouvé",
                    "basis": basis,
                    "valeur_base": 0,
                    "solde_debit": 0,
                    "solde_credit": 0,
                    "solde_net": 0,
                    "signe": signe,
                    "contribution": 0,
                    "pattern": gl_code if gl_code != code else None
                })
    
    formule = poste.get("formule")
    if formule == "net_clamp_zero":
        if _PCB_CALC_DEBUG:
            _dbg(
                f"[PCB_CALC] net_clamp_zero BEFORE poste={poste.get('code','')} ({poste.get('id','')}) brut={float(solde_total_brut or 0.0)}"
            )
        solde_total_brut = max(0.0, float(solde_total_brut or 0.0))
        if _PCB_CALC_DEBUG:
            _dbg(
                f"[PCB_CALC] net_clamp_zero AFTER poste={poste.get('code','')} ({poste.get('id','')}) brut={float(solde_total_brut or 0.0)}"
            )

    # Calculer solde_affiche (toujours positif) et warning
    solde_affiche = abs(solde_total_brut)
    warning_signe = solde_total_brut < 0
    
    return {
        "solde_brut": solde_total_brut,
        "solde_affiche": solde_affiche,
        "warning_signe": warning_signe,
        "gl_details": gl_details
    }


async def calculer_poste_hierarchique(
    poste_id: str,
    organization_id: str,
    date_solde: Optional[datetime] = None,
) -> Dict:
    """Calcule un poste et ses sous-postes (parent = somme enfants, feuille = GL).

    Retourne une structure hiérarchique:
    {
      "id": str,
      "code": str,
      "libelle": str,
      "type": str,
      "niveau": int,
      "parent_id": Optional[str],
      "ordre": int,
      "solde_brut": float,
      "solde_affiche": float,
      "warning_signe": bool,
      "gl_details": list,
      "enfants": list,
      "source": str
    }
    """
    all_postes = await list_postes_reglementaires(organization_id, {})
    postes_dict = {p["id"]: p for p in all_postes}
    if poste_id not in postes_dict:
        raise ValueError("Poste introuvable")

    postes_enfants: Dict[str, List[dict]] = {}
    for p in all_postes:
        pid = p.get("parent_id")
        if pid and pid in postes_dict:
            postes_enfants.setdefault(pid, []).append(p)

    memo: Dict[str, dict] = {}
    visiting: set = set()

    async def compute_by_id(node_id: str) -> dict:
        if node_id in memo:
            return memo[node_id]
        if node_id in visiting:
            raise ValueError("Cycle détecté dans la formule des postes")
        if node_id not in postes_dict:
            raise ValueError("Poste référencé introuvable")

        visiting.add(node_id)
        node = postes_dict[node_id]

        enfants = []
        if node_id in postes_enfants:
            for enfant in sorted(postes_enfants[node_id], key=lambda x: (x.get("ordre", 0), x.get("code", ""))):
                enfants.append(await compute_by_id(enfant["id"]))

        if enfants:
            if _PCB_CALC_DEBUG:
                _dbg(
                    f"[PCB_CALC] somme_enfants parent={node.get('code','')} ({node.get('id','')}) enfants="
                    + ", ".join(
                        f"{e.get('code','')}({e.get('id','')}) sign={e.get('contribution_signe','+')} brut={float(e.get('solde_brut',0) or 0)} affiche={float(e.get('solde_affiche',0) or 0)}"
                        for e in enfants
                    )
                )
            # Agrégation parent: solde_brut = somme signée des soldes bruts des enfants
            # en appliquant contribution_signe ("-" => soustraire l'enfant).
            solde_brut = sum(
                (-1.0 if e.get("contribution_signe") == "-" else 1.0)
                * float(e.get("solde_brut", 0) or 0)
                for e in enfants
            )
            solde_affiche = abs(solde_brut)
            warning_signe = solde_brut < 0
            if _PCB_CALC_DEBUG:
                _dbg(
                    f"[PCB_CALC] somme_enfants RESULT parent={node.get('code','')} brut={solde_brut} affiche={solde_affiche}"
                )
            result = {
                "id": node["id"],
                "code": node.get("code", ""),
                "libelle": node.get("libelle", ""),
                "type": node.get("type", ""),
                "niveau": node.get("niveau", 1),
                "parent_id": node.get("parent_id"),
                "ordre": node.get("ordre", 0),
                "contribution_signe": node.get("contribution_signe", "+"),
                "solde_brut": solde_brut,
                "solde_affiche": solde_affiche,
                "warning_signe": warning_signe,
                "gl_details": [],
                "enfants": enfants,
                "source": "somme_enfants",
            }
            memo[node_id] = result
            visiting.remove(node_id)
            return result

        # Poste racine sans enfants calculé par formule sur autres postes racines
        # - Compte de résultat: peut référencer cr_produit et cr_charge
        # - Compte d'exploitation bancaire: peut référencer cr_exploitation
        # - Bilan: peut référencer uniquement les postes du même type (actif avec actif, passif avec passif)
        if (
            not node.get("parent_id")
            and node.get("type") in ["cr_produit", "cr_charge", "cr_exploitation", "bilan_actif", "bilan_passif"]
            and node.get("calculation_mode") == "parents_formula"
        ):
            terms = node.get("parents_formula", []) or []
            allowed_ref_types = (
                ["cr_produit", "cr_charge"]
                if node.get("type") in ["cr_produit", "cr_charge"]
                else ["cr_exploitation"]
                if node.get("type") == "cr_exploitation"
                else [node.get("type")]
            )
            if _PCB_CALC_DEBUG:
                _dbg(
                    f"[PCB_CALC] parents_formula START node={node.get('code','')} ({node.get('id','')}) terms="
                    + ", ".join(
                        f"{t.get('op','?')}{t.get('poste_id','')}" for t in (terms or []) if isinstance(t, dict)
                    )
                )
            tokens: List[object] = []
            expecting_value = True
            for term in terms:
                if not isinstance(term, dict):
                    continue

                op = term.get("op")
                ref_id = term.get("poste_id")

                if op in ["(", ")"]:
                    tokens.append(op)
                    expecting_value = op == "(" or op in ["+", "-", "*", "/"]
                    continue

                if op not in ["+", "-", "*", "/"]:
                    continue

                # Opérateur seul (ex: '/', '+')
                if not ref_id:
                    tokens.append(op)
                    expecting_value = True
                    continue

                ref = postes_dict.get(ref_id)
                if not ref or ref.get("parent_id"):
                    continue
                if ref.get("type") not in allowed_ref_types:
                    continue
                ref_calc = await compute_by_id(ref_id)
                ref_solde = float(ref_calc.get("solde_brut", 0) or 0)
                if _PCB_CALC_DEBUG:
                    _dbg(
                        f"[PCB_CALC] parents_formula TERM node={node.get('code','')} op={op} ref={ref.get('code','')} ({ref_id}) ref_brut={ref_solde}"
                    )

                if expecting_value:
                    tokens.append(-ref_solde if op == "-" else ref_solde)
                else:
                    tokens.append(op)
                    tokens.append(ref_solde)
                expecting_value = False

            solde_brut = _eval_infix_tokens(tokens)
            solde_affiche = abs(solde_brut)
            warning_signe = solde_brut < 0
            if _PCB_CALC_DEBUG:
                _dbg(
                    f"[PCB_CALC] parents_formula RESULT node={node.get('code','')} brut={solde_brut} affiche={solde_affiche} warn={warning_signe}"
                )
            result = {
                "id": node["id"],
                "code": node.get("code", ""),
                "libelle": node.get("libelle", ""),
                "type": node.get("type", ""),
                "niveau": node.get("niveau", 1),
                "parent_id": node.get("parent_id"),
                "ordre": node.get("ordre", 0),
                "contribution_signe": node.get("contribution_signe", "+"),
                "solde_brut": solde_brut,
                "solde_affiche": solde_affiche,
                "warning_signe": warning_signe,
                "gl_details": [],
                "enfants": [],
                "source": "parents_formula",
            }
            memo[node_id] = result
            visiting.remove(node_id)
            return result

        # Feuille: calcul par GL
        resultat = await calculer_solde_poste(node, organization_id, date_solde)
        result = {
            "id": node["id"],
            "code": node.get("code", ""),
            "libelle": node.get("libelle", ""),
            "type": node.get("type", ""),
            "niveau": node.get("niveau", 1),
            "parent_id": node.get("parent_id"),
            "ordre": node.get("ordre", 0),
            "contribution_signe": node.get("contribution_signe", "+"),
            "solde_brut": resultat.get("solde_brut", 0),
            "solde_affiche": resultat.get("solde_affiche", 0),
            "warning_signe": resultat.get("warning_signe", False),
            "gl_details": resultat.get("gl_details", []),
            "enfants": [],
            "source": "gl_codes",
        }
        memo[node_id] = result
        visiting.remove(node_id)
        return result

    return await compute_by_id(poste_id)


async def calculer_structure_rapport(
    type_rapport: str,
    organization_id: str,
    date_solde: Optional[datetime] = None,
    postes_ids: Optional[List[str]] = None,
    section: Optional[str] = None,
) -> Dict:
    """
    Calcule la structure complète d'un rapport (bilan, hors bilan, compte de résultat)
    
    Retourne:
    {
        "postes": List[PosteCalcul],
        "totaux": Dict
    }
    """
    # Déterminer le filtre de type
    type_filter = None
    if type_rapport == "bilan_reglementaire":
        # On récupère actif et passif
        pass
    elif type_rapport == "hors_bilan":
        type_filter = {"type": "hors_bilan"}
    elif type_rapport == "compte_resultat":
        # On récupère produits et charges
        pass
    
    # Récupérer les postes
    filters = {}
    if type_filter:
        filters.update(type_filter)
    
    if type_rapport == "bilan_reglementaire":
        # Récupérer actif et/ou passif selon la section demandée
        if section == "actif":
            all_postes = await list_postes_reglementaires(organization_id, {"type": "bilan_actif"})
        elif section == "passif":
            all_postes = await list_postes_reglementaires(organization_id, {"type": "bilan_passif"})
        else:
            postes_actif = await list_postes_reglementaires(organization_id, {"type": "bilan_actif"})
            postes_passif = await list_postes_reglementaires(organization_id, {"type": "bilan_passif"})
            all_postes = postes_actif + postes_passif
    elif type_rapport == "compte_resultat":
        if section == "produits":
            all_postes = await list_postes_reglementaires(organization_id, {"type": "cr_produit"})
        elif section == "charges":
            all_postes = await list_postes_reglementaires(organization_id, {"type": "cr_charge"})
        elif section == "exploitation":
            all_postes = await list_postes_reglementaires(organization_id, {"type": "cr_exploitation"})
        else:
            postes_produits = await list_postes_reglementaires(organization_id, {"type": "cr_produit"})
            postes_charges = await list_postes_reglementaires(organization_id, {"type": "cr_charge"})
            postes_exploitation = await list_postes_reglementaires(organization_id, {"type": "cr_exploitation"})
            all_postes = postes_produits + postes_charges + postes_exploitation
    else:
        all_postes = await list_postes_reglementaires(organization_id, filters)
    
    # Filtrer par IDs si fourni
    if postes_ids:
        all_postes = [p for p in all_postes if p["id"] in postes_ids]
    
    # Construire l'arbre hiérarchique
    postes_dict = {p["id"]: p for p in all_postes}
    postes_enfants = {}  # {parent_id: [enfants]}
    postes_racine = []
    
    for poste in all_postes:
        parent_id = poste.get("parent_id")
        if parent_id and parent_id in postes_dict:
            if parent_id not in postes_enfants:
                postes_enfants[parent_id] = []
            postes_enfants[parent_id].append(poste)
        else:
            postes_racine.append(poste)

    memo: Dict[str, dict] = {}
    visiting: set = set()
    
    async def calculer_poste_avec_enfants(poste: dict) -> dict:
        """Calcule un poste et ses enfants récursivement"""
        poste_id = poste["id"]
        if poste_id in memo:
            return memo[poste_id]
        if poste_id in visiting:
            raise ValueError("Cycle détecté dans la hiérarchie des postes")

        visiting.add(poste_id)
        # Calculer d'abord tous les enfants
        enfants_calcules = []
        if poste_id in postes_enfants:
            for enfant in sorted(postes_enfants[poste_id], key=lambda x: (x.get("ordre", 0), x.get("code", ""))):
                enfant_calc = await calculer_poste_avec_enfants(enfant)
                enfants_calcules.append(enfant_calc)

        # RÈGLE: si le poste a des enfants, son solde est la somme des sous-postes (ignorer gl_codes au niveau parent)
        if enfants_calcules:
            if _PCB_CALC_DEBUG:
                _dbg(
                    f"[PCB_CALC] somme_enfants parent={poste.get('code','')} ({poste.get('id','')}) enfants="
                    + ", ".join(
                        f"{e.get('code','')}({e.get('id','')}) sign={e.get('contribution_signe','+')} brut={float(e.get('solde_brut',0) or 0)} affiche={float(e.get('solde_affiche',0) or 0)}"
                        for e in enfants_calcules
                    )
                )
            # Agrégation parent: solde_brut = somme signée des soldes bruts des enfants
            # en appliquant contribution_signe ("-" => soustraire l'enfant).
            solde_brut_enfants = sum(
                (-1.0 if e.get("contribution_signe") == "-" else 1.0)
                * float(e.get("solde_brut", 0) or 0)
                for e in enfants_calcules
            )
            solde_affiche_enfants = abs(solde_brut_enfants)
            warning_signe_enfants = solde_brut_enfants < 0
            if _PCB_CALC_DEBUG:
                _dbg(
                    f"[PCB_CALC] somme_enfants RESULT parent={poste.get('code','')} brut={solde_brut_enfants} affiche={solde_affiche_enfants}"
                )
            result = {
                "id": poste_id,
                "code": poste["code"],
                "libelle": poste["libelle"],
                "type": poste.get("type", ""),
                "niveau": poste.get("niveau", 1),
                "parent_id": poste.get("parent_id"),
                "ordre": poste.get("ordre", 0),
                "contribution_signe": poste.get("contribution_signe", "+"),
                "solde_brut": solde_brut_enfants,
                "solde_affiche": solde_affiche_enfants,
                "warning_signe": warning_signe_enfants,
                "gl_details": [],
                "enfants": enfants_calcules,
                "source": "somme_enfants",
            }
            memo[poste_id] = result
            visiting.remove(poste_id)
            return result

        # Poste racine sans enfants calculé par formule
        # - Compte de résultat: peut référencer cr_produit et cr_charge
        # - Bilan: peut référencer uniquement les postes du même type (actif avec actif, passif avec passif)
        if (
            not poste.get("parent_id")
            and poste.get("type") in ["cr_produit", "cr_charge", "cr_exploitation", "bilan_actif", "bilan_passif"]
            and poste.get("calculation_mode") == "parents_formula"
        ):
            terms = poste.get("parents_formula", []) or []
            allowed_ref_types = (
                ["cr_produit", "cr_charge"]
                if poste.get("type") in ["cr_produit", "cr_charge"]
                else ["cr_exploitation"]
                if poste.get("type") == "cr_exploitation"
                else [poste.get("type")]
            )
            tokens: List[object] = []
            expecting_value = True
            for term in terms:
                if not isinstance(term, dict):
                    continue

                op = term.get("op")
                ref_id = term.get("poste_id")

                if op in ["(", ")"]:
                    tokens.append(op)
                    expecting_value = op == "(" or op in ["+", "-", "*", "/"]
                    continue

                if op not in ["+", "-", "*", "/"]:
                    continue

                if not ref_id:
                    tokens.append(op)
                    expecting_value = True
                    continue

                ref = postes_dict.get(ref_id)
                if not ref or ref.get("parent_id"):
                    continue
                if ref.get("type") not in allowed_ref_types:
                    continue

                ref_calc = await calculer_poste_avec_enfants(ref)
                ref_solde = float(ref_calc.get("solde_brut", 0) or 0)

                if expecting_value:
                    tokens.append(-ref_solde if op == "-" else ref_solde)
                else:
                    tokens.append(op)
                    tokens.append(ref_solde)
                expecting_value = False

            solde_brut = _eval_infix_tokens(tokens)
            solde_affiche = abs(solde_brut)
            warning_signe = solde_brut < 0
            result = {
                "id": poste_id,
                "code": poste["code"],
                "libelle": poste["libelle"],
                "type": poste.get("type", ""),
                "niveau": poste.get("niveau", 1),
                "parent_id": poste.get("parent_id"),
                "ordre": poste.get("ordre", 0),
                "contribution_signe": poste.get("contribution_signe", "+"),
                "solde_brut": solde_brut,
                "solde_affiche": solde_affiche,
                "warning_signe": warning_signe,
                "gl_details": [],
                "enfants": [],
                "source": "parents_formula",
            }
            memo[poste_id] = result
            visiting.remove(poste_id)
            return result
        
        # Si le poste a des gl_codes, calculer depuis les GL
        gl_codes = poste.get("gl_codes", [])
        formule = poste.get("formule", "somme")
        
        if gl_codes and len(gl_codes) > 0:
            # Poste avec GL : calculer depuis les GL
            resultat = await calculer_solde_poste(poste, organization_id, date_solde)
            solde_brut_gl = resultat["solde_brut"]
            
            # Poste feuille (sans enfants) : solde = GL
            result = {
                "id": poste_id,
                "code": poste["code"],
                "libelle": poste["libelle"],
                "type": poste.get("type", ""),
                "niveau": poste.get("niveau", 1),
                "parent_id": poste.get("parent_id"),
                "ordre": poste.get("ordre", 0),
                "contribution_signe": poste.get("contribution_signe", "+"),
                "solde_brut": solde_brut_gl,
                "solde_affiche": resultat["solde_affiche"],
                "warning_signe": resultat["warning_signe"],
                "gl_details": resultat["gl_details"],
                "enfants": [],
                "source": "gl_codes",
            }
            memo[poste_id] = result
            visiting.remove(poste_id)
            return result
        else:
            # Poste sans gl_codes : somme des enfants (ou 0 si pas d'enfants)
            # Poste feuille sans GL et sans enfants : solde 0
            solde_brut_enfants = 0.0
            solde_affiche_enfants = 0.0
            warning_signe_enfants = False
            
            result = {
                "id": poste_id,
                "code": poste["code"],
                "libelle": poste["libelle"],
                "type": poste.get("type", ""),
                "niveau": poste.get("niveau", 1),
                "parent_id": poste.get("parent_id"),
                "ordre": poste.get("ordre", 0),
                "contribution_signe": poste.get("contribution_signe", "+"),
                "solde_brut": solde_brut_enfants,
                "solde_affiche": solde_affiche_enfants,
                "warning_signe": warning_signe_enfants,
                "gl_details": [],
                "enfants": [],
                "source": "vide"
            }
            memo[poste_id] = result
            visiting.remove(poste_id)
            return result
    
    # Calculer tous les postes racine et leurs enfants
    postes_calcules = []
    for poste_racine in sorted(postes_racine, key=lambda x: (x.get("ordre", 0), x.get("code", ""))):
        poste_calc = await calculer_poste_avec_enfants(poste_racine)
        postes_calcules.append(poste_calc)
    
    # Aplatir la structure pour compatibilité (garder aussi la structure hiérarchique)
    def aplatir_poste(poste_calc: dict, niveau: int = 0) -> list:
        """Aplatit un poste et ses enfants en liste"""
        result = [{
            "id": poste_calc.get("id"),
            "code": poste_calc["code"],
            "libelle": poste_calc["libelle"],
            "type": poste_calc.get("type", ""),  # Inclure le type pour les totaux
            "solde": poste_calc.get("solde_affiche", 0),  # Compatibilité: garder "solde" pour ancien code
            "solde_brut": poste_calc.get("solde_brut", 0),
            "solde_affiche": poste_calc.get("solde_affiche", 0),
            "warning_signe": poste_calc.get("warning_signe", False),
            "gl_details": poste_calc.get("gl_details", []),
            "niveau": niveau,
            "parent_id": poste_calc.get("parent_id"),
            "source": poste_calc.get("source", "gl_codes")
        }]
        for enfant in poste_calc.get("enfants", []):
            result.extend(aplatir_poste(enfant, niveau + 1))
        return result
    
    postes_aplatis = []
    for poste_calc in postes_calcules:
        postes_aplatis.extend(aplatir_poste(poste_calc))
    
    # Calculer les totaux (utiliser solde_affiche pour affichage)
    totaux = {}
    
    if type_rapport == "bilan_reglementaire":
        # Séparer actif et passif selon le type du poste
        postes_actif_list = [p for p in postes_aplatis if p.get("type", "").startswith("bilan_actif")]
        postes_passif_list = [p for p in postes_aplatis if p.get("type", "").startswith("bilan_passif")]
        
        # Utiliser solde_affiche (toujours positif) pour les totaux
        total_actif = sum(p.get("solde_affiche", p.get("solde", 0)) for p in postes_actif_list)
        total_passif = sum(p.get("solde_affiche", p.get("solde", 0)) for p in postes_passif_list)
        
        # Pour l'équilibre, utiliser les soldes bruts
        total_actif_brut = sum(p.get("solde_brut", 0) for p in postes_actif_list)
        total_passif_brut = sum(p.get("solde_brut", 0) for p in postes_passif_list)
        
        totaux["total_actif"] = total_actif
        totaux["total_passif"] = total_passif
        totaux["equilibre"] = abs(total_actif_brut - total_passif_brut) < 1000  # Tolérance pour arrondis (1000 XOF)
    
    elif type_rapport == "compte_resultat":
        # Séparer produits et charges selon le type du poste
        postes_produits_list = [p for p in postes_aplatis if p.get("type", "").startswith("cr_produit")]
        postes_charges_list = [p for p in postes_aplatis if p.get("type", "").startswith("cr_charge")]
        
        # Utiliser solde_affiche pour affichage
        total_produits = sum(p.get("solde_affiche", p.get("solde", 0)) for p in postes_produits_list)
        total_charges = sum(p.get("solde_affiche", p.get("solde", 0)) for p in postes_charges_list)
        
        # Pour le résultat net, utiliser les soldes bruts
        total_produits_brut = sum(p.get("solde_brut", 0) for p in postes_produits_list)
        total_charges_brut = sum(p.get("solde_brut", 0) for p in postes_charges_list)
        resultat_net_brut = total_produits_brut - total_charges_brut
        
        totaux["total_produits"] = total_produits
        totaux["total_charges"] = total_charges
        totaux["resultat_net"] = abs(resultat_net_brut)  # Afficher en positif
        totaux["resultat_net_brut"] = resultat_net_brut  # Garder le brut pour calculs
    
    return {
        "postes": postes_aplatis,  # Structure aplatie pour compatibilité
        "postes_hierarchiques": postes_calcules,  # Structure hiérarchique complète
        "totaux": totaux
    }


async def calculer_ratios_bancaires(
    structure: Dict,
    organization_id: str,
    type_rapport: str,
    use_config: bool = True
) -> Dict:
    """
    Calcule les ratios bancaires à partir de la structure du rapport
    Si use_config=True, utilise les ratios configurés, sinon calcule les ratios de base
    """
    # Si on utilise la configuration, utiliser le service dédié
    if use_config:
        try:
            from app.services.pcb_ratios_calcul import calculer_ratios_configures
            return await calculer_ratios_configures(structure, organization_id, type_rapport)
        except Exception as e:
            print(f"Erreur lors du calcul des ratios configurés, utilisation des ratios de base: {e}")
            # Fallback sur les ratios de base
    
    # Ratios de base (fallback)
    ratios = {}
    
    # Extraire les valeurs nécessaires depuis la structure
    postes_dict = {p["code"]: p["solde"] for p in structure.get("postes", [])}
    totaux = structure.get("totaux", {})
    
    if type_rapport == "bilan_reglementaire":
        total_actif = totaux.get("total_actif", 0)
        total_passif = totaux.get("total_passif", 0)
        
        # Ratio de solvabilité (Fonds propres / Actifs pondérés)
        # Approximation : utiliser le total passif comme proxy des fonds propres
        if total_actif > 0:
            # Ratio simplifié : Passif / Actif (à affiner selon la structure exacte)
            ratios["ratio_solvabilite"] = total_passif / total_actif if total_actif > 0 else 0
        
        # Ratio de liquidité (Actifs liquides / Passifs à court terme)
        # Chercher les postes de liquidité (caisse, banques, etc.)
        liquidites = 0
        for code, solde in postes_dict.items():
            if any(keyword in code.upper() for keyword in ["CAISSE", "BANQUE", "DISPONIBILITE", "1"]):
                if solde > 0:
                    liquidites += solde
        
        # Approximation des passifs à court terme
        passifs_court_terme = total_passif * 0.5  # Approximation
        if passifs_court_terme > 0:
            ratios["ratio_liquidite"] = liquidites / passifs_court_terme
        
        # Ratio d'endettement
        if total_actif > 0:
            ratios["ratio_endettement"] = total_passif / total_actif
    
    elif type_rapport == "compte_resultat":
        total_produits = totaux.get("total_produits", 0)
        total_charges = totaux.get("total_charges", 0)
        resultat_net = totaux.get("resultat_net", 0)
        
        # Marge nette
        if total_produits > 0:
            ratios["marge_nette"] = resultat_net / total_produits
        
        # Ratio d'efficacité (Coûts / Revenus)
        if total_produits > 0:
            ratios["ratio_efficacite"] = total_charges / total_produits
    
    return ratios

