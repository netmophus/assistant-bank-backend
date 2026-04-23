"""
Modele OTP pour verification email des inscriptions DEMO.

Stocke un hash SHA-256 du code a 6 chiffres (pas bcrypt : TTL court + volume
potentiellement eleve). Un TTL index Mongo purge automatiquement les docs
expires apres 10 minutes.
"""
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Tuple

from app.core.db import get_database


EMAIL_OTPS_COLLECTION = "email_otps"
OTP_LENGTH = 6
OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60


class OtpVerificationError(Exception):
    """Erreurs de verification OTP. L'attribut `code` identifie le cas."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_code() -> str:
    return f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"


async def ensure_otp_indexes() -> None:
    """Index unique sur email + TTL index sur expires_at (auto-purge)."""
    db = get_database()
    col = db[EMAIL_OTPS_COLLECTION]
    await col.create_index("email", unique=True)
    # expireAfterSeconds=0 : Mongo supprime le doc a la date exacte d'expires_at
    await col.create_index("expires_at", expireAfterSeconds=0)


async def create_or_replace_otp(email: str) -> str:
    """
    Genere un nouveau code OTP, remplace tout code existant pour cet email,
    et retourne le code en clair (a envoyer par email, jamais stocke en clair).
    """
    db = get_database()
    col = db[EMAIL_OTPS_COLLECTION]

    code = _generate_code()
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)

    await col.replace_one(
        {"email": email},
        {
            "email": email,
            "code_hash": _hash_otp(code),
            "created_at": now,
            "expires_at": expires_at,
            "attempts": 0,
            "last_sent_at": now,
        },
        upsert=True,
    )
    return code


async def can_resend_otp(email: str) -> Tuple[bool, int]:
    """
    Retourne (autorise, secondes_restantes). Si aucun OTP n'existe encore pour
    cet email, on autorise l'envoi (cooldown_remaining = 0).
    """
    db = get_database()
    col = db[EMAIL_OTPS_COLLECTION]
    doc = await col.find_one({"email": email})
    if not doc:
        return True, 0

    last_sent_at = doc.get("last_sent_at") or doc.get("created_at")
    if not last_sent_at:
        return True, 0

    elapsed = (datetime.utcnow() - last_sent_at).total_seconds()
    remaining = int(OTP_RESEND_COOLDOWN_SECONDS - elapsed)
    if remaining <= 0:
        return True, 0
    return False, remaining


async def update_resend_timestamp(email: str) -> None:
    """Met a jour last_sent_at (apres un renvoi reussi)."""
    db = get_database()
    col = db[EMAIL_OTPS_COLLECTION]
    await col.update_one(
        {"email": email},
        {"$set": {"last_sent_at": datetime.utcnow()}},
    )


async def verify_otp(email: str, code: str) -> bool:
    """
    Verifie le code OTP. Incremente le compteur d'essais et supprime le doc
    sur succes ou epuisement. Leve OtpVerificationError avec .code parmi :
    NOT_FOUND, EXPIRED, MAX_ATTEMPTS_REACHED, INVALID_CODE.
    """
    db = get_database()
    col = db[EMAIL_OTPS_COLLECTION]
    doc = await col.find_one({"email": email})

    if not doc:
        raise OtpVerificationError(
            "NOT_FOUND",
            "Aucun code actif pour cet email. Demandez un nouveau code.",
        )

    if doc["expires_at"] < datetime.utcnow():
        await col.delete_one({"email": email})
        raise OtpVerificationError(
            "EXPIRED",
            "Code expire. Demandez un nouveau code.",
        )

    if doc.get("attempts", 0) >= OTP_MAX_ATTEMPTS:
        await col.delete_one({"email": email})
        raise OtpVerificationError(
            "MAX_ATTEMPTS_REACHED",
            "Trop d'essais incorrects. Demandez un nouveau code.",
        )

    if _hash_otp(code) != doc["code_hash"]:
        await col.update_one({"email": email}, {"$inc": {"attempts": 1}})
        raise OtpVerificationError(
            "INVALID_CODE",
            "Code incorrect.",
        )

    # Succes : on supprime le doc pour empecher toute reutilisation
    await col.delete_one({"email": email})
    return True
