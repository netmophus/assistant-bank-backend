"""Service de calcul des ratios de gestion (formules personnalisées).

On évalue des expressions avec + - * / et parenthèses.
Les opérandes sont des codes de postes (ex: CNSC-CESN-PCD) ou des nombres.

Important: les codes peuvent contenir des '-' donc on ne peut pas faire un simple split.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


logger = logging.getLogger("uvicorn.error")
_RATIOS_GESTION_DEBUG = os.getenv("PCB_RATIOS_GESTION_DEBUG", "").strip() in {"1", "true", "True", "yes", "YES"}


@dataclass(frozen=True)
class RatioGestionComputed:
    code: str
    libelle: str
    description: Optional[str]
    formule: str
    unite: str
    n_1: Optional[float]
    realisation_reference: Optional[float]
    realisation_cloture: Optional[float]
    evolution: Optional[float]
    evolution_pct: Optional[float]


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


def _match_longest_code(s: str, i: int, codes_sorted: List[str]) -> Optional[Tuple[str, int]]:
    # Match codes regardless of the current char; codes may start with letters/numbers.
    for code in codes_sorted:
        if s.startswith(code, i):
            return code, i + len(code)
    return None


def _extract_codes_used(formule: str, codes_sorted: List[str]) -> List[str]:
    """Extrait les codes de postes réellement rencontrés dans la formule.

    On fait un scan proche de l'évaluateur, pour gérer les codes contenant '-' sans ambiguïté.
    """
    used: List[str] = []
    used_set = set()
    i = 0
    s = formule

    while i < len(s):
        c = s[i]
        if c.isspace() or c in ["+", "-", "*", "/", "(", ")"]:
            i += 1
            continue

        num = _read_number(s, i)
        if num is not None:
            _, j = num
            i = j
            continue

        match = _match_longest_code(s, i, codes_sorted)
        if match is not None:
            code, j = match
            if code not in used_set:
                used_set.add(code)
                used.append(code)
            i = j
            continue

        # Caractère/jeton inconnu: on avance d'un char pour éviter de boucler
        i += 1

    return used


def _read_number(s: str, i: int) -> Optional[Tuple[float, int]]:
    j = i
    has_digit = False
    has_dot = False

    while j < len(s):
        c = s[j]
        if c.isdigit():
            has_digit = True
            j += 1
            continue
        if c == "." and not has_dot:
            has_dot = True
            j += 1
            continue
        break

    if not has_digit:
        return None

    try:
        return float(s[i:j]), j
    except Exception:
        return None


def eval_formula_with_codes(formule: str, values_by_code: Dict[str, float]) -> Optional[float]:
    """Évalue une formule avec un dictionnaire code->valeur.

    Retourne None si la formule est invalide.
    """
    if not formule or not isinstance(formule, str):
        return None

    # Normalisation minimale: certains utilisateurs saisissent "////" au lieu de "/".
    # On réduit les séquences de '/' à un seul caractère pour éviter l'invalidation du parsing.
    formule = formule.strip()
    while "//" in formule:
        formule = formule.replace("//", "/")

    # Préparer les codes triés par longueur (match le plus long d'abord)
    codes_sorted = sorted(values_by_code.keys(), key=len, reverse=True)

    ops: List[str] = []
    vals: List[float] = []

    i = 0
    s = formule

    def apply_top() -> None:
        if len(vals) < 2 or not ops:
            return
        b = vals.pop()
        a = vals.pop()
        op = ops.pop()
        vals.append(_apply_op(a, op, b))

    while i < len(s):
        c = s[i]

        if c.isspace():
            i += 1
            continue

        if c in ["+", "-", "*", "/"]:
            # Gérer le moins unaire (ex: -A ou -(A+B)) -> transformer en 0 - expr
            if c == "-":
                prev = s[i - 1] if i > 0 else ""
                if i == 0 or prev in ["(", "+", "-", "*", "/"]:
                    vals.append(0.0)

            while ops and ops[-1] != "(" and _precedence(ops[-1]) >= _precedence(c):
                apply_top()
            ops.append(c)
            i += 1
            continue

        if c == "(":
            ops.append(c)
            i += 1
            continue

        if c == ")":
            while ops and ops[-1] != "(":
                apply_top()
            if not ops or ops[-1] != "(":
                return None
            ops.pop()  # pop '('
            i += 1
            continue

        num = _read_number(s, i)
        if num is not None:
            value, j = num
            vals.append(value)
            i = j
            continue

        match = _match_longest_code(s, i, codes_sorted)
        if match is not None:
            code, j = match
            vals.append(float(values_by_code.get(code, 0.0) or 0.0))
            i = j
            continue

        # Token inconnu
        return None

    while ops:
        if ops[-1] == "(":
            return None
        apply_top()

    if len(vals) != 1:
        return None

    try:
        return float(vals[0])
    except Exception:
        return None


def compute_ratios_gestion(
    ratio_lines: List[dict],
    values_cloture_by_code: Dict[str, float],
    values_n1_by_code: Dict[str, Optional[float]],
    values_real_by_code: Dict[str, Optional[float]],
) -> List[dict]:
    """Calcule toutes les lignes de ratios de gestion.

    Retourne une liste de dicts sérialisables.
    """
    results: List[dict] = []

    # Tri des codes pour le matching "plus long d'abord" (pour gérer les codes qui se préfixent)
    codes_sorted = sorted(values_cloture_by_code.keys(), key=len, reverse=True)

    # dictionnaires pour l'évaluation (None -> 0)
    env_cloture = {k: float(v or 0.0) for k, v in values_cloture_by_code.items()}
    env_n1 = {k: float(v or 0.0) for k, v in values_n1_by_code.items()}
    env_real = {k: float(v or 0.0) for k, v in values_real_by_code.items()}

    for r in ratio_lines:
        formule = (r.get("formule") or "").strip()

        used_codes = _extract_codes_used(formule, codes_sorted)
        if _RATIOS_GESTION_DEBUG:
            # Log des valeurs utilisées (N-1 / Réalisation / Clôture)
            parts = []
            for code in used_codes:
                parts.append(
                    f"{code}: n1={env_n1.get(code, 0.0)} real={env_real.get(code, 0.0)} cloture={env_cloture.get(code, 0.0)}"
                )
            logger.info(
                "[RATIOS_GESTION] code=%s formule=%s used={%s}",
                r.get("code"),
                formule,
                "; ".join(parts),
            )

        v_n1 = eval_formula_with_codes(formule, env_n1)
        v_real = eval_formula_with_codes(formule, env_real)
        v_cloture = eval_formula_with_codes(formule, env_cloture)

        evolution = None
        evolution_pct = None
        if v_cloture is not None and v_real is not None:
            evolution = v_cloture - v_real
            if v_real != 0:
                evolution_pct = ((v_cloture / v_real) - 1) * 100

        results.append(
            {
                "code": r.get("code", ""),
                "libelle": r.get("libelle", ""),
                "description": r.get("description"),
                "formule": formule,
                "unite": r.get("unite", "%"),
                "n_1": v_n1,
                "realisation_reference": v_real,
                "realisation_cloture": v_cloture,
                "evolution": evolution,
                "evolution_pct": evolution_pct,
                "ordre_affichage": r.get("ordre_affichage", 1),
            }
        )

    results.sort(key=lambda x: (x.get("ordre_affichage") or 1, x.get("code") or ""))
    return results
