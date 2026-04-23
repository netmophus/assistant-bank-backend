"""
Endpoint PUBLIC (pas d'auth) : soumission d'une demande d'abonnement
via le formulaire de www.miznas.co/tarifs.
"""
import logging

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.models.subscription_request import create_subscription_request
from app.schemas.subscription_request import SubscriptionRequestCreate
from app.services.email_service import (
    send_email,
    subscription_request_notification_html,
)

router = APIRouter(prefix="/subscription-requests", tags=["Public - Subscription"])

logger = logging.getLogger(__name__)


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_subscription_request(payload: SubscriptionRequestCreate):
    """
    Endpoint PUBLIC (pas d'auth) — un prospect soumet sa demande d'abonnement.

    - L'insertion en base est critique (500 si echec).
    - La notification email est best-effort (SMTP down -> log erreur, pas de raise).
    """
    # 1. Insert en base — CRITIQUE
    try:
        request = await create_subscription_request(payload.model_dump())
    except Exception as e:
        logger.error(f"[SUBSCRIPTION_REQUEST] Erreur insert: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de l'enregistrement de la demande.",
        )

    logger.info(
        f"[SUBSCRIPTION_REQUEST] Nouvelle demande id={request['id']} "
        f"email={payload.email} plan={payload.plan_requested} "
        f"country={payload.country} city={payload.city} "
        f"status={payload.professional_status}"
    )

    # 2. Notification email — NON-CRITIQUE
    notify_to = settings.SUBSCRIPTION_NOTIFY_EMAIL
    if notify_to:
        try:
            subject = (
                f"Nouvelle demande Miznas Pilot — "
                f"{payload.first_name} {payload.last_name}"
            )
            html = subscription_request_notification_html(request)
            await send_email(notify_to, subject, html)
            logger.info(
                f"[SUBSCRIPTION_REQUEST] Notification envoyee a {notify_to}"
            )
        except Exception as e:
            logger.error(
                f"[EMAIL_FAIL] Notification demande {request['id']} "
                f"non envoyee: {e}"
            )
            # On continue — pas de raise, la demande est enregistree
    else:
        logger.warning(
            "[SUBSCRIPTION_REQUEST] SUBSCRIPTION_NOTIFY_EMAIL non configure "
            "— pas de notification email envoyee."
        )

    return {
        "success": True,
        "message": "Votre demande a bien ete enregistree. Nous vous contacterons sous 24h.",
        "request_id": request["id"],
    }
