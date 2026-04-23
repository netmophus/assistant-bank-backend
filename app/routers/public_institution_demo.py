"""
Endpoint PUBLIC (pas d'auth) : soumission d'une demande de demonstration B2B
via le formulaire de www.miznas.co/tarifs (section institutions).
"""
import logging

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.models.institution_demo_request import create_institution_demo_request
from app.schemas.institution_demo_request import InstitutionDemoCreate
from app.services.email_service import (
    send_email,
    institution_demo_notification_html,
)

router = APIRouter(prefix="/institution-demos", tags=["Public - Institution Demo"])

logger = logging.getLogger(__name__)


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_institution_demo(payload: InstitutionDemoCreate):
    """
    Endpoint PUBLIC (pas d'auth) — un prospect institutionnel demande une demo.

    - L'insertion en base est critique (500 si echec).
    - La notification email est best-effort (SMTP down -> log erreur, pas de raise).
    """
    try:
        request = await create_institution_demo_request(payload.model_dump())
    except Exception as e:
        logger.error(
            f"[INSTITUTION_DEMO] Erreur insert: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de l'enregistrement de la demande.",
        )

    logger.info(
        f"[INSTITUTION_DEMO] Nouvelle demande id={request['id']} "
        f"institution={payload.institution_name} type={payload.institution_type} "
        f"contact={payload.first_name} {payload.last_name} ({payload.function}) "
        f"email={payload.email} country={payload.country} "
        f"modules={payload.modules_interest} users={payload.estimated_users}"
    )

    notify_to = settings.SUBSCRIPTION_NOTIFY_EMAIL
    if notify_to:
        try:
            subject = (
                f"Nouvelle demande institution Miznas Pilot — "
                f"{payload.institution_name}"
            )
            html = institution_demo_notification_html(request)
            await send_email(notify_to, subject, html)
            logger.info(
                f"[INSTITUTION_DEMO] Notification envoyee a {notify_to}"
            )
        except Exception as e:
            logger.error(
                f"[EMAIL_FAIL] Notification institution demo {request['id']} "
                f"non envoyee: {e}",
                exc_info=True,
            )
    else:
        logger.warning(
            "[INSTITUTION_DEMO] SUBSCRIPTION_NOTIFY_EMAIL non configure "
            "— pas de notification email envoyee."
        )

    return {
        "success": True,
        "message": (
            "Votre demande a bien ete enregistree. "
            "Notre equipe vous contactera sous 48h pour planifier la demonstration."
        ),
        "request_id": request["id"],
    }
