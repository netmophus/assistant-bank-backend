"""Politique d'inscription : ce qu'un appelant a le droit de demander, décidé côté serveur.

POST /auth/register est RÉSERVÉE au super administrateur authentifié (dépendance ``get_superadmin`` : 401 sans jeton
valide, 403 pour tout autre rôle). Cette politique est une seconde barrière (défense en profondeur) et valide la demande :

* le rôle « superadmin » ne peut JAMAIS être créé par l'API (script d'exploitation dédié) ;
* seuls les rôles « admin » et « user » sont créables ;
* une organisation EXISTANTE est obligatoire ;
* aucun autre champ de privilège n'est transmis : ``UserCreate`` ne porte que les champs listés ci-dessous.

L'inscription publique passe exclusivement par POST /auth/register-demo (OTP e-mail) ; les administrateurs d'organisation
créent leurs comptes par POST /auth/users/org.
"""

from __future__ import annotations

from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.schemas.user import UserCreate

CREATABLE_ROLES = frozenset({"admin", "user"})
DEFAULT_ROLE = "user"


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def is_superadmin(caller: Optional[dict]) -> bool:
    return bool(caller) and caller.get("role") == "superadmin"


def sanitize_registration(user_in: UserCreate, caller: Optional[dict]) -> UserCreate:
    """Retourne la demande autorisée (rôle normalisé), ou lève 403. Ne vérifie pas l'existence de l'organisation."""
    if not is_superadmin(caller):
        raise _error(status.HTTP_403_FORBIDDEN, "Accès réservé aux super administrateurs.")

    requested_role = (user_in.role or DEFAULT_ROLE).strip().lower()
    if requested_role == "superadmin":
        raise _error(status.HTTP_403_FORBIDDEN, "Création de compte superadministrateur interdite via l'API.")
    if requested_role not in CREATABLE_ROLES:
        raise _error(status.HTTP_403_FORBIDDEN, "Rôle non autorisé.")
    if not user_in.organization_id:
        raise _error(status.HTTP_400_BAD_REQUEST, "Une organisation est requise.")
    return user_in.model_copy(update={"role": requested_role})


async def ensure_organization_exists(db, organization_id: str) -> None:
    """400 si l'identifiant n'est pas valide ou si l'organisation n'existe pas."""
    try:
        oid = ObjectId(str(organization_id))
    except (InvalidId, TypeError):
        raise _error(status.HTTP_400_BAD_REQUEST, "Organisation invalide.")
    if await db["organizations"].find_one({"_id": oid}) is None:
        raise _error(status.HTTP_400_BAD_REQUEST, "Organisation invalide.")
