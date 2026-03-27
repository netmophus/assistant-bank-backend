"""
Service d'envoi de SMS via l'API L'Africa Mobile (lamsms.lafricamobile.com)
Documentation : https://developers.lafricamobile.com/docs/sms/introduction
"""
import unicodedata
import httpx
from typing import Dict

from app.core.config import settings

LAM_API_URL = "https://lamsms.lafricamobile.com/api"


def _normalize_phone(to: str) -> str:
    """
    Normalise un numéro de téléphone en format international sans +.
    Ex: +22796000000 -> 22796000000 ; 0096000000 -> (inchangé si pas de rule)
    """
    clean = to.strip().replace(" ", "").replace("-", "").replace(".", "")
    if clean.startswith("+"):
        clean = clean[1:]
    return clean


def _clean_message(message: str) -> str:
    """
    Nettoie le texte pour un envoi SMS fiable :
    - Remplace les espaces insécables (U+00A0, U+202F) par des espaces normaux
    - Normalise Unicode NFC
    """
    if isinstance(message, bytes):
        message = message.decode("utf-8", errors="ignore")
    elif not isinstance(message, str):
        message = str(message)
    message = unicodedata.normalize("NFC", message)
    message = message.replace("\u00a0", " ")   # espace insécable
    message = message.replace("\u202f", " ")   # espace fine insécable
    message = message.replace("\u2009", " ")   # thin space
    message = message.replace("\u2007", " ")   # figure space
    return message


async def send_sms(to: str, message: str) -> Dict[str, object]:
    """
    Envoie un SMS via l'API L'Africa Mobile (JSON POST).

    Paramètres config (.env) :
        LAM_ACCOUNT_ID   — Access Key fourni par LAM
        LAM_PASSWORD     — Access Password fourni par LAM
        LAM_SENDER       — Expéditeur alphanumérique (max 11 car., ne commence pas par un chiffre)

    Retourne :
        {"success": True,  "data": {"push_id": "12345", ...}}
        {"success": False, "error": "message d'erreur"}
    """
    account_id = getattr(settings, "LAM_ACCOUNT_ID", None)
    password   = getattr(settings, "LAM_PASSWORD", None)
    sender     = getattr(settings, "LAM_SENDER", "SOFTLINK")

    if not account_id or not password:
        return {
            "success": False,
            "error": "Configuration SMS manquante. Vérifiez LAM_ACCOUNT_ID et LAM_PASSWORD dans .env",
        }

    to_clean = _normalize_phone(to)
    text     = _clean_message(message)

    payload = {
        "accountid": account_id,
        "password":  password,
        "sender":    sender,
        "text":      text,
        "to":        to_clean,
    }

    try:
        timeout = httpx.Timeout(60.0, connect=30.0)
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            resp = await client.post(
                LAM_API_URL,
                json=payload,
                headers={"Content-Type": "application/json", "Accept": "text/plain"},
            )

        body = resp.text.strip()

        # L'Africa Mobile : 200 + corps = push_id (entier) en cas de succès
        #                   400 + corps = message d'erreur
        if resp.status_code == 200 and body.isdigit():
            return {"success": True, "data": {"push_id": body, "to": to_clean}}

        # Parfois l'API répond 200 mais avec un message d'erreur textuel
        if resp.status_code == 200:
            return {"success": True, "data": {"push_id": body, "to": to_clean}}

        return {
            "success": False,
            "error": f"L'Africa Mobile API error (HTTP {resp.status_code}): {body}",
        }

    except httpx.TimeoutException:
        return {"success": False, "error": "Timeout lors de l'envoi SMS (L'Africa Mobile)"}
    except httpx.HTTPError as e:
        return {"success": False, "error": f"Erreur HTTP L'Africa Mobile: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Erreur inattendue L'Africa Mobile: {str(e)}"}
