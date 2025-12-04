from typing import List

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.stock.demande_consommable import (
    approve_demande_directeur,
    create_demande,
    get_demande_by_id,
    get_demande_history,
    list_demandes_by_user,
    list_demandes_pending_directeur,
    list_demandes_pending_gestionnaire,
    reject_demande_directeur,
    traiter_demande_gestionnaire,
)
from app.schemas.stock.demande_consommable import (
    ApprobationDirecteur,
    DemandeConsommableCreate,
    DemandeConsommablePublic,
    TraitementGestionnaire,
)

router = APIRouter(
    prefix="/stock/demandes",
    tags=["stock-demandes"],
)


@router.post("", response_model=DemandeConsommablePublic)
async def create_demande_endpoint(
    demande_in: DemandeConsommableCreate, current_user: dict = Depends(get_current_user)
):
    """
    Crée une demande de consommable.
    """
    user_id = current_user.get("id")
    user_dept_id = current_user.get("department_id")

    if not user_id or not user_dept_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informations utilisateur incomplètes.",
        )

    try:
        demande_data = demande_in.model_dump()
        demande_data["user_id"] = str(user_id)
        demande_data["department_id"] = str(user_dept_id)

        demande = await create_demande(demande_data)
        return demande
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la création: {str(e)}",
        )


@router.post("/direct", response_model=DemandeConsommablePublic)
async def create_demande_directe_endpoint(
    demande_in: DemandeConsommableCreate, current_user: dict = Depends(get_current_user)
):
    """
    Crée une demande directe qui débite immédiatement le stock (pour tests/démo).
    """
    from app.models.stock.consommable import get_consommable_by_id, update_stock

    user_id = current_user.get("id")
    user_dept_id = current_user.get("department_id")

    if not user_id or not user_dept_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informations utilisateur incomplètes.",
        )

    try:
        # Vérifier le stock disponible
        consommable = await get_consommable_by_id(demande_in.consommable_id)
        if not consommable:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Consommable introuvable.",
            )

        if consommable["quantite_stock"] < demande_in.quantite_demandee:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Stock insuffisant. Disponible: {consommable['quantite_stock']} {consommable['unite']}",
            )

        # Débiter le stock immédiatement
        await update_stock(
            demande_in.consommable_id, demande_in.quantite_demandee, "subtract"
        )

        # Créer une demande avec statut "traite"
        demande_data = demande_in.model_dump()
        demande_data["user_id"] = str(user_id)
        demande_data["department_id"] = str(user_dept_id)

        demande = await create_demande(demande_data)

        # Marquer comme traitée directement
        from app.models.stock.demande_consommable import traiter_demande_gestionnaire

        await traiter_demande_gestionnaire(
            demande["id"],
            str(user_id),
            demande_in.quantite_demandee,
            "Demande directe - stock débité automatiquement",
        )

        return demande
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la création: {str(e)}",
        )


@router.get("/user/mes-demandes", response_model=List[DemandeConsommablePublic])
async def list_user_demandes_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Liste les demandes de l'utilisateur connecté.
    """
    user_id = current_user.get("id")

    if not user_id:
        return []

    try:
        demandes = await list_demandes_by_user(str(user_id))
        return demandes
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.get("/directeur/a-valider", response_model=List[DemandeConsommablePublic])
async def list_demandes_pending_directeur_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """
    Liste les demandes en attente de validation par le directeur.
    """
    user_role = current_user.get("role", "user")
    user_dept_id = current_user.get("department_id")

    # Vérifier que l'utilisateur est directeur (on peut ajouter une vérification plus stricte)
    if not user_dept_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être assigné à un département.",
        )

    try:
        demandes = await list_demandes_pending_directeur(str(user_dept_id))
        return demandes
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.get("/gestionnaire/a-traiter", response_model=List[DemandeConsommablePublic])
async def list_demandes_pending_gestionnaire_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """
    Liste les demandes approuvées en attente de traitement par le gestionnaire.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    # Pour l'instant, on considère que l'admin peut être gestionnaire
    # On peut ajouter un rôle spécifique "gestionnaire_stock" plus tard
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent traiter les demandes.",
        )

    try:
        demandes = await list_demandes_pending_gestionnaire(str(user_org_id))
        return demandes
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.get("/{demande_id}", response_model=DemandeConsommablePublic)
async def get_demande_endpoint(
    demande_id: str, current_user: dict = Depends(get_current_user)
):
    """
    Récupère une demande par son ID.
    """
    try:
        demande = await get_demande_by_id(demande_id)
        if not demande:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Demande introuvable.",
            )

        # Vérifier les permissions
        user_id = current_user.get("id")
        user_role = current_user.get("role", "user")
        user_dept_id = current_user.get("department_id")

        # L'utilisateur peut voir sa propre demande
        # Le directeur peut voir les demandes de son département
        # L'admin peut voir toutes les demandes
        has_access = (
            demande["user_id"] == str(user_id)
            or (user_role == "admin")
            or (demande["department_id"] == str(user_dept_id))
        )

        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'avez pas accès à cette demande.",
            )

        return demande
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.post("/{demande_id}/approuver")
async def approve_demande_endpoint(
    demande_id: str,
    approbation: ApprobationDirecteur,
    current_user: dict = Depends(get_current_user),
):
    """
    Approuve une demande par le directeur.
    """
    user_id = current_user.get("id")
    user_dept_id = current_user.get("department_id")

    if not user_dept_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être assigné à un département.",
        )

    try:
        demande = await get_demande_by_id(demande_id)
        if not demande:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Demande introuvable.",
            )

        if demande["department_id"] != str(user_dept_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez approuver que les demandes de votre département.",
            )

        if demande["statut"] != "en_attente":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cette demande a déjà été traitée.",
            )

        updated = await approve_demande_directeur(
            demande_id, str(user_id), approbation.commentaire
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de l'approbation.",
            )

        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'approbation: {str(e)}",
        )


@router.post("/{demande_id}/rejeter")
async def reject_demande_endpoint(
    demande_id: str,
    approbation: ApprobationDirecteur,
    current_user: dict = Depends(get_current_user),
):
    """
    Rejette une demande par le directeur.
    """
    user_id = current_user.get("id")
    user_dept_id = current_user.get("department_id")

    if not user_dept_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être assigné à un département.",
        )

    try:
        demande = await get_demande_by_id(demande_id)
        if not demande:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Demande introuvable.",
            )

        if demande["department_id"] != str(user_dept_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez rejeter que les demandes de votre département.",
            )

        if demande["statut"] != "en_attente":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cette demande a déjà été traitée.",
            )

        updated = await reject_demande_directeur(
            demande_id, str(user_id), approbation.commentaire
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors du rejet.",
            )

        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du rejet: {str(e)}",
        )


@router.post("/{demande_id}/traiter")
async def traiter_demande_endpoint(
    demande_id: str,
    traitement: TraitementGestionnaire,
    current_user: dict = Depends(get_current_user),
):
    """
    Traite une demande approuvée par le gestionnaire de stock.
    """
    user_role = current_user.get("role", "user")
    user_id = current_user.get("id")

    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent traiter les demandes.",
        )

    try:
        demande = await get_demande_by_id(demande_id)
        if not demande:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Demande introuvable.",
            )

        if demande["statut"] != "approuve_directeur":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cette demande n'est pas encore approuvée par le directeur.",
            )

        updated = await traiter_demande_gestionnaire(
            demande_id,
            str(user_id),
            traitement.quantite_accordee,
            traitement.commentaire,
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors du traitement.",
            )

        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du traitement: {str(e)}",
        )


@router.get("/{demande_id}/history")
async def get_demande_history_endpoint(
    demande_id: str, current_user: dict = Depends(get_current_user)
):
    """
    Récupère l'historique complet d'une demande.
    """
    try:
        demande = await get_demande_by_id(demande_id)
        if not demande:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Demande introuvable.",
            )

        # Vérifier les permissions (même logique que get_demande)
        user_id = current_user.get("id")
        user_role = current_user.get("role", "user")
        user_dept_id = current_user.get("department_id")

        has_access = (
            demande["user_id"] == str(user_id)
            or (user_role == "admin")
            or (demande["department_id"] == str(user_dept_id))
        )

        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'avez pas accès à cette demande.",
            )

        history = await get_demande_history(demande_id)
        return {"history": history}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )
