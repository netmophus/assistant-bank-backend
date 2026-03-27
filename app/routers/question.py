from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.question import (
    check_user_quota,
    create_question,
    get_user_quota_stats,
    list_org_questions,
    list_user_questions,
)
from app.schemas.question import QuestionCreate, QuestionPublic, QuestionStats

router = APIRouter(
    prefix="/questions",
    tags=["questions"],
)


@router.post("", response_model=QuestionPublic)
async def ask_question(
    question_data: QuestionCreate, current_user: dict = Depends(get_current_user)
):
    """
    Pose une question à l'IA.
    Vérifie le quota mensuel (60 questions/mois).
    """
    user_id = str(current_user.get("id"))

    # Vérifier le quota avant de créer la question
    can_ask, stats = await check_user_quota(user_id)
    if not can_ask:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Quota mensuel dépassé. Vous avez utilisé {stats['questions_asked']}/{stats['quota_limit']} questions ce mois-ci.",
        )

    try:
        question = await create_question(
            user_id, question_data.question, question_data.context
        )
        return question
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/my-questions", response_model=list[QuestionPublic])
async def get_my_questions(
    limit: int = 50, current_user: dict = Depends(get_current_user)
):
    """
    Liste les questions de l'utilisateur connecté.
    """
    user_id = current_user["id"]
    questions = await list_user_questions(user_id, limit)
    return questions


@router.get("/quota", response_model=QuestionStats)
async def get_quota_stats(current_user: dict = Depends(get_current_user)):
    """
    Récupère les statistiques de quota de l'utilisateur connecté.
    """
    user_id = current_user["id"]
    stats = await get_user_quota_stats(user_id)
    return QuestionStats(**stats)


@router.get("/org", response_model=list[QuestionPublic])
async def get_org_questions(
    limit: int = 100, current_user: dict = Depends(get_current_user)
):
    """
    Liste toutes les questions de l'organisation (réservé aux admins d'organisation).
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent voir toutes les questions.",
        )

    questions = await list_org_questions(str(user_org_id), limit)
    return questions
