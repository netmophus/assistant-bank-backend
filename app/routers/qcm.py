from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.qcm_response import (
    get_user_qcm_responses,
    get_user_qcm_stats,
    submit_qcm_response,
)
from app.schemas.qcm_response import (
    QCMModuleStats,
    QCMResponseCreate,
    QCMResponsePublic,
)

router = APIRouter(
    prefix="/qcm",
    tags=["qcm"],
)


@router.post("/submit", response_model=QCMResponsePublic)
async def submit_qcm_answer(
    response_data: QCMResponseCreate, current_user: dict = Depends(get_current_user)
):
    """
    Soumet une réponse QCM et retourne le feedback (correct/incorrect avec explication).
    """
    user_id = current_user["id"]

    try:
        response = await submit_qcm_response(
            user_id=user_id,
            formation_id=response_data.formation_id,
            module_id=response_data.module_id,
            question_index=response_data.question_index,
            selected_answer=response_data.selected_answer,
        )
        return response
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la soumission de la réponse: {str(e)}",
        )


@router.get(
    "/responses/{formation_id}/{module_id}", response_model=list[QCMResponsePublic]
)
async def get_my_qcm_responses(
    formation_id: str, module_id: str, current_user: dict = Depends(get_current_user)
):
    """
    Récupère toutes les réponses QCM de l'utilisateur pour un module donné.
    """
    user_id = current_user["id"]

    try:
        responses = await get_user_qcm_responses(user_id, formation_id, module_id)
        return responses
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des réponses: {str(e)}",
        )


@router.get("/stats/{formation_id}/{module_id}", response_model=QCMModuleStats)
async def get_my_qcm_stats(
    formation_id: str, module_id: str, current_user: dict = Depends(get_current_user)
):
    """
    Récupère les statistiques QCM de l'utilisateur pour un module donné.
    """
    user_id = current_user["id"]

    try:
        stats = await get_user_qcm_stats(user_id, formation_id, module_id)
        return QCMModuleStats(**stats)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des statistiques: {str(e)}",
        )
