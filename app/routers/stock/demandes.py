from typing import List

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.stock.demande_consommable import (
    approve_demande_directeur,
    approve_demande_drh,
    create_demande,
    formaliser_demande_drh,
    get_demande_by_id,
    get_demande_history,
    list_demandes_by_user,
    list_demandes_pending_approbation_drh,
    list_demandes_pending_directeur,
    list_demandes_pending_formalisation_drh,
    list_demandes_pending_gestionnaire,
    list_demandes_pending_validation_sortie,
    reject_demande_directeur,
    reject_demande_drh,
    traiter_demande_gestionnaire,
    valider_sortie_agent_departement,
    valider_sortie_agent_stock,
)
from app.schemas.stock.demande_consommable import (
    ApprobationDirecteur,
    DemandeConsommableCreate,
    DemandeConsommablePublic,
    FormalisationDRH,
    TraitementGestionnaire,
    ValidationSortie,
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
    import logging

    from app.models.stock.consommable import get_consommable_by_id, update_stock

    logger = logging.getLogger(__name__)
    logger.info(f"Demande reçue: {demande_in.model_dump()}")

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
        logger.info(f"Consommable récupéré: {consommable}")
        if not consommable:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Consommable introuvable.",
            )

        # Vérifier le stock selon le type de sélection (par défaut: conteneur)
        type_selection = (
            getattr(demande_in, "type_selection", "conteneur") or "conteneur"
        )

        if type_selection == "conteneur":
            stock_disponible = consommable["quantite_stock_conteneur"]
            unite_affichage = consommable.get("unite_conteneur", "conteneur")

            if stock_disponible < demande_in.quantite_demandee:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Stock insuffisant. Disponible: {stock_disponible} {unite_affichage}(s)",
                )

            # Débiter directement les conteneurs demandés
            await update_stock(
                demande_in.consommable_id, demande_in.quantite_demandee, "subtract"
            )

        elif demande_in.type_selection == "unite":
            stock_total_disponible = consommable["quantite_stock_total"]
            unite_affichage = consommable.get("unite_base", "unité")

            if stock_total_disponible < demande_in.quantite_demandee:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Stock insuffisant. Disponible: {stock_total_disponible} {unite_affichage}(s)",
                )

            # Pour les unités, on débite des conteneurs entiers
            # Si on demande 10 unités d'une boîte de 25, on débite 1 conteneur
            quantite_par_conteneur = consommable.get("quantite_par_conteneur", 1)
            # Calcul du nombre de conteneurs nécessaires (arrondi vers le haut)
            import math

            conteneurs_necessaires = math.ceil(
                demande_in.quantite_demandee / quantite_par_conteneur
            )

            # Vérifier qu'on a assez de conteneurs
            if consommable["quantite_stock_conteneur"] < conteneurs_necessaires:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Stock insuffisant en conteneurs. Besoin: {conteneurs_necessaires}, Disponible: {consommable['quantite_stock_conteneur']}",
                )

            await update_stock(
                demande_in.consommable_id, conteneurs_necessaires, "subtract"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Type de sélection invalide: {type_selection}. Utilisez 'conteneur' ou 'unite'",
            )

        # Créer une demande avec statut "traite"
        demande_data = demande_in.model_dump()
        demande_data["user_id"] = str(user_id)
        demande_data["department_id"] = str(user_dept_id)
        logger.info(f"Données de demande préparées: {demande_data}")

        demande = await create_demande(demande_data)
        logger.info(f"Demande créée: {demande}")

        # Pour les demandes directes, on les marque automatiquement comme approuvées
        # puis traitées (pour simuler le workflow complet)

        # Étape 1: Auto-approbation
        from app.models.stock.demande_consommable import approve_demande_directeur

        await approve_demande_directeur(
            demande["id"], str(user_id), "Auto-approuvé - Demande directe"
        )

        # Étape 2: Traitement automatique
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
        logger.error(
            f"Erreur dans create_demande_directe_endpoint: {str(e)}", exc_info=True
        )
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
    user_role_dept = current_user.get("role_departement")

    # Vérifier que l'utilisateur est directeur
    if not user_dept_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être assigné à un département.",
        )

    if user_role_dept != "directeur":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les directeurs de département peuvent voir les demandes à valider.",
        )

    try:
        print(f"Directeur - user_id: {current_user.get('id')}, user_dept_id: {user_dept_id}, user_role_dept: {user_role_dept}")
        demandes = await list_demandes_pending_directeur(str(user_dept_id))
        print(f"Retourné {len(demandes)} demandes pour le directeur")
        return demandes
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.get("/directeur-drh/a-approuver", response_model=List[DemandeConsommablePublic])
async def list_demandes_pending_approbation_drh_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """
    Liste les demandes approuvées par le directeur département en attente d'approbation par le directeur DRH.
    """
    user_role = current_user.get("role", "user")
    user_role_dept = current_user.get("role_departement")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est directeur DRH (directeur avec accès organisationnel)
    # Pour l'instant, on suppose que le directeur DRH a role_departement = "directeur" et peut voir toutes les demandes de l'organisation
    if user_role_dept != "directeur" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les directeurs DRH peuvent approuver les demandes.",
        )

    try:
        demandes = await list_demandes_pending_approbation_drh(str(user_org_id))
        return demandes
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.get("/drh/a-formaliser", response_model=List[DemandeConsommablePublic])
async def list_demandes_pending_formalisation_drh_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """
    Liste les demandes approuvées par le directeur DRH en attente de formalisation par l'agent DRH.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est agent DRH ou admin
    # TODO: Ajouter un rôle spécifique "agent_stock_drh" ou "agent_drh"
    if user_role not in ["admin", "agent_stock_drh"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les agents DRH peuvent formaliser les demandes.",
        )

    try:
        demandes = await list_demandes_pending_formalisation_drh(str(user_org_id))
        return demandes
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.get("/validation-sortie/a-valider", response_model=List[DemandeConsommablePublic])
async def list_demandes_pending_validation_sortie_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """
    Liste les demandes formalisées en attente de validation conjointe des sorties.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    # Accessible aux agents du département et aux agents stock DRH
    if not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être rattaché à une organisation.",
        )

    try:
        demandes = await list_demandes_pending_validation_sortie(str(user_org_id))
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
    Liste les demandes avec validation conjointe complète en attente de traitement (débit stock).
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "gestionnaire_stock"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs et les gestionnaires de stock peuvent traiter les demandes.",
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
    from app.models.user import check_user_hierarchy_permission

    user_id = current_user.get("id")
    user_dept_id = current_user.get("department_id")
    user_role_dept = current_user.get("role_departement")

    if not user_dept_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être assigné à un département.",
        )

    # Vérifier que l'utilisateur est directeur
    if user_role_dept != "directeur":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les directeurs de département peuvent approuver les demandes.",
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

        # Double vérification avec la base de données
        has_permission = await check_user_hierarchy_permission(
            str(user_id), demande["department_id"]
        )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'avez pas les permissions de directeur pour ce département.",
            )

        if demande["statut"] != "en_attente":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cette demande a déjà été traitée.",
            )

        try:
            updated = await approve_demande_directeur(
                demande_id, str(user_id), approbation.commentaire
            )
            return updated
        except ValueError as ve:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(ve),
            )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        import traceback
        print(f"Erreur dans approve_demande_endpoint: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'approbation: {str(e)}",
        )


@router.post("/{demande_id}/approuver-drh")
async def approve_demande_drh_endpoint(
    demande_id: str,
    approbation: ApprobationDirecteur,
    current_user: dict = Depends(get_current_user),
):
    """
    Approuve une demande par le directeur DRH.
    """
    user_id = current_user.get("id")
    user_role_dept = current_user.get("role_departement")
    user_org_id = current_user.get("organization_id")

    if not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être assigné à une organisation.",
        )

    # Vérifier que l'utilisateur est directeur DRH
    if user_role_dept != "directeur":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les directeurs DRH peuvent approuver les demandes.",
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
                detail="Cette demande doit d'abord être approuvée par le directeur de département.",
            )

        try:
            updated = await approve_demande_drh(
                demande_id, str(user_id), approbation.commentaire
            )
            return updated
        except ValueError as ve:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(ve),
            )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        import traceback
        print(f"Erreur dans approve_demande_drh_endpoint: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'approbation: {str(e)}",
        )


@router.post("/{demande_id}/rejeter-drh")
async def reject_demande_drh_endpoint(
    demande_id: str,
    approbation: ApprobationDirecteur,
    current_user: dict = Depends(get_current_user),
):
    """
    Rejette une demande par le directeur DRH.
    """
    user_id = current_user.get("id")
    user_role_dept = current_user.get("role_departement")
    user_org_id = current_user.get("organization_id")

    if not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être assigné à une organisation.",
        )

    # Vérifier que l'utilisateur est directeur DRH
    if user_role_dept != "directeur":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les directeurs DRH peuvent rejeter les demandes.",
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
                detail="Cette demande doit d'abord être approuvée par le directeur de département.",
            )

        try:
            updated = await reject_demande_drh(
                demande_id, str(user_id), approbation.commentaire
            )
            return updated
        except ValueError as ve:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(ve),
            )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        import traceback
        print(f"Erreur dans reject_demande_drh_endpoint: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du rejet: {str(e)}",
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
    from app.models.user import check_user_hierarchy_permission

    user_id = current_user.get("id")
    user_dept_id = current_user.get("department_id")
    user_role_dept = current_user.get("role_departement")

    if not user_dept_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être assigné à un département.",
        )

    # Vérifier que l'utilisateur est directeur
    if user_role_dept != "directeur":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les directeurs de département peuvent rejeter les demandes.",
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

        # Double vérification avec la base de données
        has_permission = await check_user_hierarchy_permission(
            str(user_id), demande["department_id"]
        )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'avez pas les permissions de directeur pour ce département.",
            )

        if demande["statut"] != "en_attente":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cette demande a déjà été traitée.",
            )

        updated = await reject_demande_directeur(
            demande_id, str(user_id), approbation.commentaire
        )

        return updated
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du rejet: {str(e)}",
        )


@router.post("/{demande_id}/formaliser")
async def formaliser_demande_endpoint(
    demande_id: str,
    formalisation: FormalisationDRH,
    current_user: dict = Depends(get_current_user),
):
    """
    Formalise une demande approuvée par l'agent DRH.
    """
    user_role = current_user.get("role", "user")
    user_id = current_user.get("id")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est agent DRH ou admin
    if user_role not in ["admin", "agent_stock_drh"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les agents DRH peuvent formaliser les demandes.",
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

        updated = await formaliser_demande_drh(
            demande_id, str(user_id), formalisation.commentaire
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la formalisation.",
            )

        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la formalisation: {str(e)}",
        )


@router.post("/{demande_id}/valider-sortie-departement")
async def valider_sortie_agent_departement_endpoint(
    demande_id: str,
    validation: ValidationSortie,
    current_user: dict = Depends(get_current_user),
):
    """
    Valide la sortie par l'agent du département.
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

        if demande["statut"] != "formalise_drh":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cette demande n'est pas encore formalisée par la DRH.",
            )

        if demande["department_id"] != str(user_dept_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez valider que les sorties de votre département.",
            )

        updated = await valider_sortie_agent_departement(
            demande_id,
            str(user_id),
            validation.quantite_accordee,
            validation.commentaire,
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la validation.",
            )

        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la validation: {str(e)}",
        )


@router.post("/{demande_id}/valider-sortie-stock")
async def valider_sortie_agent_stock_endpoint(
    demande_id: str,
    validation: ValidationSortie,
    current_user: dict = Depends(get_current_user),
):
    """
    Valide la sortie par l'agent stock DRH.
    """
    user_role = current_user.get("role", "user")
    user_id = current_user.get("id")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est agent stock DRH ou admin
    if user_role not in ["admin", "agent_stock_drh"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les agents stock DRH peuvent valider les sorties.",
        )

    try:
        demande = await get_demande_by_id(demande_id)
        if not demande:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Demande introuvable.",
            )

        if demande["statut"] != "formalise_drh":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cette demande n'est pas encore formalisée par la DRH.",
            )

        updated = await valider_sortie_agent_stock(
            demande_id,
            str(user_id),
            validation.quantite_accordee,
            validation.commentaire,
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la validation.",
            )

        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la validation: {str(e)}",
        )


@router.post("/{demande_id}/traiter")
async def traiter_demande_endpoint(
    demande_id: str,
    traitement: TraitementGestionnaire,
    current_user: dict = Depends(get_current_user),
):
    """
    Traite une demande approuvée par le directeur DRH et débite le stock (admin ou gestionnaire de stock).
    """
    user_role = current_user.get("role", "user")
    user_id = current_user.get("id")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "gestionnaire_stock"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs et les gestionnaires de stock peuvent traiter les demandes.",
        )

    try:
        demande = await get_demande_by_id(demande_id)
        if not demande:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Demande introuvable.",
            )

        # Vérifier que la demande appartient à l'organisation via le consommable
        from app.models.stock.consommable import get_consommable_by_id
        consommable = await get_consommable_by_id(demande.get("consommable_id"))
        if not consommable:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Consommable introuvable.",
            )
        
        if consommable.get("organization_id") != str(user_org_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez traiter que les demandes de votre organisation.",
            )

        if demande["statut"] != "approuve_drh":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cette demande doit d'abord être approuvée par le directeur DRH.",
            )

        # Vérifier que la demande a été approuvée par le directeur DRH
        approbation_drh = demande.get("approbation_drh", {})
        if approbation_drh.get("statut") != "approuve":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cette demande n'a pas été approuvée par le directeur DRH.",
            )

        # Utiliser la quantité demandée
        quantite_accordee = traitement.quantite_accordee

        try:
            updated = await traiter_demande_gestionnaire(
                demande_id,
                str(user_id),
                quantite_accordee,
                traitement.commentaire,
            )
            return updated
        except ValueError as ve:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(ve),
            )
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
