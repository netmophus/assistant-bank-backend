"""Routes FastAPI: Formations.

Ce routeur regroupe toute l'API "formation".

Vue d'ensemble du flux:
- Admin org:
  - CRUD (create/list/get/update)
  - Sauvegarde en brouillon (status=draft)
  - Publication (status=published) avec options IA:
    - `auto_generate_content`: génère `contenu_genere` pour les chapitres
    - `auto_generate_qcm`: génère `questions_qcm` au niveau module
  - Affectation des formations publiées aux départements

- Utilisateur:
  - Accès aux formations publiées assignées à son département (ou org)
  - Endpoints "lecture" / génération ponctuelle (contenu chapitre/partie, suggestions)
"""

from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.db import get_database
from app.core.deps import get_current_user
from app.models.formation import (
    create_formation,
    get_formation_by_id,
    list_formations_by_org,
    update_formation,
)
from app.models.formation_assignment import (
    assign_formation_to_departments,
    get_departments_for_formation,
    get_formations_for_department,
)
from app.schemas.formation import (
    FormationCreate,
    FormationDepartmentAssignment,
    FormationPublic,
    FormationUpdate,
)
from app.services.ai_service import (
    generate_chapitre_content,
    generate_chapter_question_suggestions,
    generate_partie_content,
    generate_qcm_questions,
)

router = APIRouter(
    prefix="/formations",
    tags=["formations"],
)


# -----------------------------------------------------------------------------
# Admin (organisation): CRUD formation
# -----------------------------------------------------------------------------


@router.post("", response_model=FormationPublic)
async def create_formation_endpoint(
    formation_in: FormationCreate, current_user: dict = Depends(get_current_user)
):
    """
    Crée une formation pour l'organisation de l'admin connecté.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est un admin d'organisation
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent créer des formations.",
        )

    # Multi-org: on ne fait pas confiance au client. L'organisation est déduite du token.
    # Si le client envoie un organization_id différent, on refuse.
    if formation_in.organization_id and formation_in.organization_id != str(user_org_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez créer des formations que pour votre propre organisation.",
        )

    try:
        formation_data = formation_in.model_dump()
        formation_data["organization_id"] = str(user_org_id)
        formation = await create_formation(formation_data, str(user_org_id))
        return formation
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("", response_model=list[FormationPublic])
async def get_formations(current_user: dict = Depends(get_current_user)):
    """
    Liste les formations de l'organisation de l'admin connecté.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est un admin d'organisation
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent voir les formations.",
        )

    formations = await list_formations_by_org(str(user_org_id))
    return formations


@router.get("/{formation_id}", response_model=FormationPublic)
async def get_formation(
    formation_id: str, current_user: dict = Depends(get_current_user)
):
    """
    Récupère une formation complète par son ID.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est un admin d'organisation
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent voir les formations.",
        )

    formation = await get_formation_by_id(formation_id)
    if not formation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Formation introuvable.",
        )

    # Vérifier que la formation appartient à l'organisation
    if formation["organization_id"] != str(user_org_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cette formation n'appartient pas à votre organisation.",
        )

    return formation


@router.put("/{formation_id}", response_model=FormationPublic)
async def update_formation_endpoint(
    formation_id: str,
    formation_update: FormationUpdate,
    current_user: dict = Depends(get_current_user),
):
    """
    Met à jour une formation.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent modifier les formations.",
        )

    try:
        update_data = formation_update.model_dump(exclude_unset=True)
        formation = await update_formation(formation_id, update_data, str(user_org_id))
        return formation
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# -----------------------------------------------------------------------------
# Utilisateur: accès aux formations (publiées) de son organisation/département
# -----------------------------------------------------------------------------

@router.get("/user/my-formations", response_model=list[FormationPublic])
async def get_my_formations(current_user: dict = Depends(get_current_user)):
    """
    Liste les formations disponibles pour l'utilisateur connecté.
    Retourne uniquement les formations publiées et assignées à son département.
    """
    from app.models.formation_assignment import get_formations_for_department

    user_org_id = current_user.get("organization_id")
    user_dept_id = current_user.get("department_id")

    if not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être associé à une organisation pour voir les formations.",
        )

    # Si l'utilisateur a un département, récupérer les formations assignées à ce département
    if user_dept_id:
        # Récupérer les IDs des formations assignées au département ET de l'organisation
        assigned_formations = await get_formations_for_department(str(user_dept_id), str(user_org_id))
        formation_ids = [f["id"] for f in assigned_formations]

        if not formation_ids:
            formations = await list_formations_by_org(str(user_org_id))
            published_formations = [f for f in formations if f.get("status") == "published"]
            return published_formations

        # Récupérer les formations complètes avec tous leurs détails (modules, chapitres, contenu généré, QCM)
        formations = []
        for formation_info in assigned_formations:
            formation_id = formation_info.get("id")
            if formation_id:
                formation = await get_formation_by_id(formation_id)
                if formation and formation.get("status") == "published":
                    formations.append(formation)

        return formations
    else:
        # Si l'utilisateur n'a pas de département, retourner toutes les formations publiées de l'organisation
        formations = await list_formations_by_org(str(user_org_id))
        published_formations = [f for f in formations if f.get("status") == "published"]
        return published_formations


# -----------------------------------------------------------------------------
# Admin: publication + génération IA optionnelle (contenu / QCM)
# -----------------------------------------------------------------------------

@router.post("/{formation_id}/publish", response_model=FormationPublic)
async def publish_formation(
    formation_id: str,
    auto_generate_content: bool = Query(
        False, description="Générer automatiquement le contenu des chapitres avec l'IA"
    ),
    auto_generate_qcm: bool = Query(
        False, description="Générer automatiquement les QCM des modules avec l'IA"
    ),
    current_user: dict = Depends(get_current_user),
):
    """
    Publie une formation (change le statut de draft à published).
    Optionnellement, génère automatiquement le contenu des chapitres et les QCM avec l'IA.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent publier les formations.",
        )

    try:
        # Récupérer la formation avant publication
        formation = await get_formation_by_id(formation_id)
        if not formation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Formation introuvable.",
            )

        # Générer automatiquement le contenu si demandé
        if auto_generate_content:
            db = get_database()
            formation_oid = ObjectId(formation_id)

            for module in formation.get("modules", []):
                for chapitre in module.get("chapitres", []):
                    # Générer le contenu seulement si pas déjà généré
                    if not chapitre.get("contenu_genere"):
                        try:
                            parties = chapitre.get("parties", [])
                            if parties and any(p.get("contenu") for p in parties):
                                generated_content = await generate_chapitre_content(
                                    introduction=chapitre.get("introduction", ""),
                                    parties=parties,
                                    formation_titre=formation.get("titre", ""),
                                    module_titre=module.get("titre", ""),
                                    chapitre_titre=chapitre.get("titre", ""),
                                )

                                # Mettre à jour dans la base de données
                                formation_doc = await db["formations"].find_one(
                                    {"_id": formation_oid}
                                )
                                if formation_doc:
                                    modules = formation_doc.get("modules", [])
                                    for m in modules:
                                        if str(m["_id"]) == module["id"]:
                                            chapitres = m.get("chapitres", [])
                                            for ch in chapitres:
                                                if str(ch["_id"]) == chapitre["id"]:
                                                    ch["contenu_genere"] = (
                                                        generated_content
                                                    )
                                                    break
                                            m["chapitres"] = chapitres
                                            break

                                    await db["formations"].update_one(
                                        {"_id": formation_oid},
                                        {"$set": {"modules": modules}},
                                    )
                        except Exception as e:
                            print(
                                f"Erreur lors de la génération du contenu pour le chapitre {chapitre.get('id')}: {e}"
                            )
                            # Continuer avec les autres chapitres même en cas d'erreur

        # Générer automatiquement les QCM si demandé
        if auto_generate_qcm:
            db = get_database()
            formation_oid = ObjectId(formation_id)

            for module in formation.get("modules", []):
                # Générer les QCM seulement si pas déjà générés
                if (
                    not module.get("questions_qcm")
                    or len(module.get("questions_qcm", [])) == 0
                ):
                    try:
                        chapitres = module.get("chapitres", [])
                        if chapitres:
                            questions = await generate_qcm_questions(
                                module_titre=module.get("titre", ""),
                                chapitres=chapitres,
                                nombre_questions=5,
                            )

                            # Mettre à jour dans la base de données
                            formation_doc = await db["formations"].find_one(
                                {"_id": formation_oid}
                            )
                            if formation_doc:
                                modules = formation_doc.get("modules", [])
                                for m in modules:
                                    if str(m["_id"]) == module["id"]:
                                        m["questions_qcm"] = questions
                                        break

                                await db["formations"].update_one(
                                    {"_id": formation_oid},
                                    {"$set": {"modules": modules}},
                                )
                    except Exception as e:
                        print(
                            f"Erreur lors de la génération des QCM pour le module {module.get('id')}: {e}"
                        )
                        # Continuer avec les autres modules même en cas d'erreur

        # Publier la formation
        update_data = {"status": "published"}
        formation = await update_formation(formation_id, update_data, str(user_org_id))
        return formation
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# -----------------------------------------------------------------------------
# Admin: affectation des formations publiées aux départements
# -----------------------------------------------------------------------------

@router.post("/{formation_id}/assign-departments")
async def assign_formation_to_departments_endpoint(
    formation_id: str,
    assignment: FormationDepartmentAssignment,
    current_user: dict = Depends(get_current_user),
):
    """
    Affecte une formation publiée à des départements.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent affecter les formations.",
        )

    if assignment.formation_id != formation_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="L'ID de la formation ne correspond pas.",
        )

    try:
        result = await assign_formation_to_departments(
            formation_id, assignment.department_ids, str(user_org_id)
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{formation_id}/assigned-departments")
async def get_assigned_departments(
    formation_id: str, current_user: dict = Depends(get_current_user)
):
    """
    Récupère les départements auxquels une formation est affectée.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent voir les affectations.",
        )

    department_ids = await get_departments_for_formation(formation_id)
    return {"formation_id": formation_id, "department_ids": department_ids}


# -----------------------------------------------------------------------------
# Utilisateur: endpoints IA "à la demande" en lecture (générer contenu / suggérer)
# -----------------------------------------------------------------------------

@router.post(
    "/{formation_id}/modules/{module_id}/chapitres/{chapitre_id}/generate-content-user"
)
async def generate_chapitre_content_user_endpoint(
    formation_id: str,
    module_id: str,
    chapitre_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Génère le contenu d'un chapitre avec l'IA pour un utilisateur.
    Vérifie que la formation est assignée au département de l'utilisateur.
    """
    from app.models.formation_assignment import get_formations_for_department
    from app.services.ai_service import generate_chapitre_content

    user_org_id = current_user.get("organization_id")
    user_dept_id = current_user.get("department_id")

    if not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être associé à une organisation pour accéder aux formations.",
        )

    # Vérifier que l'utilisateur a un département et que la formation est assignée à ce département
    if user_dept_id:
        assigned_formations = await get_formations_for_department(str(user_dept_id), str(user_org_id))
        formation_ids = [f["id"] for f in assigned_formations]
        if formation_id not in formation_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cette formation n'est pas assignée à votre département.",
            )

    # Récupérer la formation
    formation = await get_formation_by_id(formation_id)
    if not formation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Formation introuvable.",
        )

    if formation.get("status") != "published":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cette formation n'est pas encore publiée.",
        )

    # Trouver le module et le chapitre
    module = None
    chapitre = None
    for m in formation.get("modules", []):
        if str(m["id"]) == module_id:
            module = m
            for ch in m.get("chapitres", []):
                if str(ch["id"]) == chapitre_id:
                    chapitre = ch
                    break
            break

    if not module or not chapitre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module ou chapitre introuvable.",
        )

    # Vérifier si le contenu est déjà généré
    if chapitre.get("contenu_genere"):
        return {
            "chapitre_id": chapitre_id,
            "contenu_genere": chapitre.get("contenu_genere"),
            "message": "Le contenu de ce chapitre a déjà été généré.",
            "already_generated": True,
        }

    # Générer le contenu
    parties = chapitre.get("parties", [])
    if not parties or not any(p.get("contenu") for p in parties):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ce chapitre n'a pas de parties avec des prompts pour générer le contenu.",
        )

    try:
        generated_content = await generate_chapitre_content(
            introduction=chapitre.get("introduction", ""),
            parties=parties,
            formation_titre=formation.get("titre", ""),
            module_titre=module.get("titre", ""),
            chapitre_titre=chapitre.get("titre", ""),
        )

        # Mettre à jour dans la base de données (lecture seule pour les utilisateurs, on retourne juste le contenu)
        # Note: On ne sauvegarde pas pour les utilisateurs, ils voient juste le contenu généré
        return {
            "chapitre_id": chapitre_id,
            "contenu_genere": generated_content,
            "message": "Contenu généré avec succès.",
            "already_generated": False,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la génération du contenu: {str(e)}",
        )


@router.get(
    "/{formation_id}/modules/{module_id}/chapitres/{chapitre_id}/question-suggestions"
)
async def get_chapter_question_suggestions_endpoint(
    formation_id: str,
    module_id: str,
    chapitre_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Génère des suggestions de questions pertinentes sur un chapitre pour aider l'utilisateur.
    """
    from app.models.formation_assignment import get_formations_for_department

    user_org_id = current_user.get("organization_id")
    user_dept_id = current_user.get("department_id")

    if not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être associé à une organisation pour accéder aux formations.",
        )

    # Vérifier que la formation est assignée au département de l'utilisateur
    if user_dept_id:
        assigned_formations = await get_formations_for_department(str(user_dept_id), str(user_org_id))
        formation_ids = [f["id"] for f in assigned_formations]
        if formation_id not in formation_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cette formation n'est pas assignée à votre département.",
            )

    # Récupérer la formation
    formation = await get_formation_by_id(formation_id)
    if not formation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Formation introuvable.",
        )

    # Trouver le module et le chapitre
    module = None
    chapitre = None
    for m in formation.get("modules", []):
        if str(m["id"]) == module_id:
            module = m
            for ch in m.get("chapitres", []):
                if str(ch["id"]) == chapitre_id:
                    chapitre = ch
                    break
            break

    if not module or not chapitre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module ou chapitre introuvable.",
        )

    try:
        suggestions = await generate_chapter_question_suggestions(
            chapitre_introduction=chapitre.get("introduction", ""),
            contenu_genere=chapitre.get("contenu_genere"),
            parties=chapitre.get("parties", []),
            nombre_suggestions=3,
        )

        return {"chapitre_id": chapitre_id, "suggestions": suggestions}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la génération des suggestions: {str(e)}",
        )


@router.post(
    "/{formation_id}/modules/{module_id}/chapitres/{chapitre_id}/parties/{partie_id}/generate-content-user"
)
async def generate_partie_content_user_endpoint(
    formation_id: str,
    module_id: str,
    chapitre_id: str,
    partie_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Génère le contenu d'une partie spécifique avec l'IA pour un utilisateur.
    """
    from app.models.formation_assignment import get_formations_for_department

    user_org_id = current_user.get("organization_id")
    user_dept_id = current_user.get("department_id")

    if not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être associé à une organisation pour accéder aux formations.",
        )

    # Vérifier que la formation est assignée au département de l'utilisateur
    if user_dept_id:
        assigned_formations = await get_formations_for_department(str(user_dept_id), str(user_org_id))
        formation_ids = [f["id"] for f in assigned_formations]
        if formation_id not in formation_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cette formation n'est pas assignée à votre département.",
            )

    # Récupérer la formation
    formation = await get_formation_by_id(formation_id)
    if not formation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Formation introuvable.",
        )

    if formation.get("status") != "published":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cette formation n'est pas encore publiée.",
        )

    # Trouver le module, le chapitre et la partie
    module = None
    chapitre = None
    partie = None

    for m in formation.get("modules", []):
        if str(m["id"]) == module_id:
            module = m
            for ch in m.get("chapitres", []):
                if str(ch["id"]) == chapitre_id:
                    chapitre = ch
                    for p in ch.get("parties", []):
                        if str(p["id"]) == partie_id:
                            partie = p
                            break
                    break
            break

    if not module or not chapitre or not partie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module, chapitre ou partie introuvable.",
        )

    # Vérifier si le contenu est déjà généré
    if partie.get("contenu_genere"):
        return {
            "partie_id": partie_id,
            "contenu_genere": partie.get("contenu_genere"),
            "message": "Le contenu de cette partie a déjà été généré.",
            "already_generated": True,
        }

    # Générer le contenu
    if not partie.get("contenu"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cette partie n'a pas de prompt pour générer le contenu.",
        )

    try:
        generated_content = await generate_partie_content(
            partie_titre=partie.get("titre", ""),
            partie_prompt=partie.get("contenu", ""),
            chapitre_introduction=chapitre.get("introduction", ""),
            formation_titre=formation.get("titre", ""),
            module_titre=module.get("titre", ""),
        )

        # Sauvegarder le contenu généré dans la base de données
        from datetime import datetime

        from bson import ObjectId

        from app.core.db import get_database

        db = get_database()
        try:
            formation_oid = ObjectId(formation_id)
            module_oid = ObjectId(module_id)
            chapitre_oid = ObjectId(chapitre_id)
            partie_oid = ObjectId(partie_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="IDs invalides.",
            )

        # Mettre à jour la partie avec le contenu généré
        formation_doc = await db["formations"].find_one({"_id": formation_oid})
        if formation_doc:
            modules = formation_doc.get("modules", [])
            for m in modules:
                if str(m["_id"]) == module_id:
                    chapitres = m.get("chapitres", [])
                    for ch in chapitres:
                        if str(ch["_id"]) == chapitre_id:
                            parties = ch.get("parties", [])
                            for p in parties:
                                if str(p["_id"]) == partie_id:
                                    p["contenu_genere"] = generated_content
                                    break
                            ch["parties"] = parties
                            break
                    m["chapitres"] = chapitres
                    break

            await db["formations"].update_one(
                {"_id": formation_oid},
                {"$set": {"modules": modules, "updated_at": datetime.utcnow()}},
            )

        return {
            "partie_id": partie_id,
            "contenu_genere": generated_content,
            "message": "Contenu généré avec succès.",
            "already_generated": False,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la génération du contenu: {str(e)}",
        )


@router.post("/{formation_id}/modules/{module_id}/chapitres/{chapitre_id}/ask-question")
async def ask_chapitre_question_endpoint(
    formation_id: str,
    module_id: str,
    chapitre_id: str,
    question_data: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Permet à un utilisateur de poser une question d'éclaircissement sur un chapitre.
    """
    from app.models.formation_assignment import get_formations_for_department
    from app.models.question import create_question
    from app.services.ai_service import OPENAI_MODEL, client

    user_id = current_user["id"]
    user_org_id = current_user.get("organization_id")
    user_dept_id = current_user.get("department_id")

    if not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être associé à une organisation pour accéder aux formations.",
        )

    # Vérifier que la formation est assignée au département de l'utilisateur
    if user_dept_id:
        assigned_formations = await get_formations_for_department(str(user_dept_id), str(user_org_id))
        formation_ids = [f["id"] for f in assigned_formations]
        if formation_id not in formation_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cette formation n'est pas assignée à votre département.",
            )

    # Récupérer la formation
    formation = await get_formation_by_id(formation_id)
    if not formation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Formation introuvable.",
        )

    # Trouver le module et le chapitre
    module = None
    chapitre = None
    for m in formation.get("modules", []):
        if str(m["id"]) == module_id:
            module = m
            for ch in m.get("chapitres", []):
                if str(ch["id"]) == chapitre_id:
                    chapitre = ch
                    break
            break

    if not module or not chapitre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module ou chapitre introuvable.",
        )

    question_text = question_data.get("question", "").strip()
    if not question_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La question ne peut pas être vide.",
        )

    # Construire le contexte pour la question
    contexte_chapitre = f"""
Formation: {formation.get("titre", "")}
Module: {module.get("titre", "")}
Chapitre: {chapitre.get("introduction", "")}
"""

    if chapitre.get("contenu_genere"):
        contexte_chapitre += (
            f"\nContenu du chapitre:\n{chapitre.get('contenu_genere', '')}"
        )
    else:
        # Si le contenu n'est pas encore généré, utiliser les parties
        parties_text = "\n".join(
            [
                f"- {p.get('titre', '')}: {p.get('contenu', '')}"
                for p in chapitre.get("parties", [])
            ]
        )
        contexte_chapitre += f"\nStructure du chapitre:\n{parties_text}"

    # Créer la question avec le contexte
    try:
        question = await create_question(
            user_id,
            question_text,
            context=f"Question sur le chapitre '{chapitre.get('introduction', '')}' de la formation '{formation.get('titre', '')}'.\n\n{contexte_chapitre}",
        )

        # La réponse est déjà générée automatiquement par create_question avec l'IA
        return question
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{formation_id}/modules/{module_id}/generate-qcm")
async def generate_qcm_for_module_endpoint(
    formation_id: str,
    module_id: str,
    nombre_questions: int = 5,
    current_user: dict = Depends(get_current_user),
):
    """
    Génère des questions QCM pour un module avec l'IA.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent générer des QCM.",
        )

    # Récupérer la formation
    formation = await get_formation_by_id(formation_id)
    if not formation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Formation introuvable.",
        )

    # Vérifier que la formation appartient à l'organisation
    if formation["organization_id"] != str(user_org_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cette formation n'appartient pas à votre organisation.",
        )

    # Trouver le module
    module = None
    for m in formation.get("modules", []):
        if str(m["id"]) == module_id:
            module = m
            break

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module introuvable.",
        )

    # Générer les questions QCM avec l'IA
    chapitres = module.get("chapitres", [])
    questions = await generate_qcm_questions(
        module_titre=module.get("titre", ""),
        chapitres=chapitres,
        nombre_questions=nombre_questions,
    )

    # Sauvegarder les questions dans le module
    db = get_database()
    try:
        formation_oid = ObjectId(formation_id)
        module_oid = ObjectId(module_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="IDs invalides.",
        )

    # Mettre à jour le module avec les questions QCM
    formation_doc = await db["formations"].find_one({"_id": formation_oid})
    if formation_doc:
        modules = formation_doc.get("modules", [])
        for m in modules:
            if str(m["_id"]) == module_id:
                m["questions_qcm"] = questions
                break

        await db["formations"].update_one(
            {"_id": formation_oid},
            {"$set": {"modules": modules, "updated_at": datetime.utcnow()}},
        )

    return {
        "module_id": module_id,
        "questions": questions,
        "message": f"{len(questions)} questions QCM générées avec succès.",
    }


@router.post(
    "/{formation_id}/modules/{module_id}/chapitres/{chapitre_id}/generate-content"
)
async def generate_chapitre_content_endpoint(
    formation_id: str,
    module_id: str,
    chapitre_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Génère le contenu d'un chapitre avec l'IA en utilisant les prompts des parties.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent générer du contenu.",
        )

    # Récupérer la formation
    formation = await get_formation_by_id(formation_id)
    if not formation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Formation introuvable.",
        )

    # Vérifier que la formation appartient à l'organisation
    if formation["organization_id"] != str(user_org_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cette formation n'appartient pas à votre organisation.",
        )

    # Trouver le module et le chapitre
    module = None
    chapitre = None
    for m in formation.get("modules", []):
        if str(m["id"]) == module_id:
            module = m
            for ch in m.get("chapitres", []):
                if str(ch["id"]) == chapitre_id:
                    chapitre = ch
                    break
            break

    if not module or not chapitre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module ou chapitre introuvable.",
        )

    # Générer le contenu avec l'IA
    parties = chapitre.get("parties", [])
    generated_content = await generate_chapitre_content(
        introduction=chapitre.get("introduction", ""),
        parties=parties,
        formation_titre=formation.get("titre", ""),
        module_titre=module.get("titre", ""),
        chapitre_titre=chapitre.get("titre", ""),
    )

    # Sauvegarder le contenu généré dans le chapitre
    db = get_database()
    try:
        formation_oid = ObjectId(formation_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID de formation invalide.",
        )

    # Mettre à jour le chapitre avec le contenu généré
    formation_doc = await db["formations"].find_one({"_id": formation_oid})
    if formation_doc:
        modules = formation_doc.get("modules", [])
        for m in modules:
            if str(m["_id"]) == module_id:
                chapitres = m.get("chapitres", [])
                for ch in chapitres:
                    if str(ch["_id"]) == chapitre_id:
                        ch["contenu_genere"] = generated_content
                        break
                m["chapitres"] = chapitres
                break

        await db["formations"].update_one(
            {"_id": formation_oid},
            {"$set": {"modules": modules, "updated_at": datetime.utcnow()}},
        )

    return {
        "chapitre_id": chapitre_id,
        "contenu_genere": generated_content,
        "message": "Contenu généré avec succès.",
    }


# -----------------------------------------------------------------------------
# Catalogue global: liste, organisations, affectation
# -----------------------------------------------------------------------------

async def _is_catalogue_admin(current_user: dict, db) -> bool:
    """Vérifie que l'utilisateur est admin de l'org CATALOGUE."""
    if current_user.get("role") != "admin":
        return False
    org_id = current_user.get("organization_id")
    if not org_id:
        return False
    org = await db["organizations"].find_one({"_id": ObjectId(str(org_id))})
    return org is not None and org.get("code") == "CATALOGUE"


@router.get("/catalogue/list", response_model=list[FormationPublic])
async def get_catalogue_formations(current_user: dict = Depends(get_current_user)):
    """
    Liste toutes les formations du catalogue global.
    Accessible à l'admin catalogue et au superadmin.
    """
    db = get_database()
    user_role = current_user.get("role")

    if user_role == "superadmin":
        pass  # accès total
    elif not await _is_catalogue_admin(current_user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé à l'administrateur du catalogue.",
        )

    catalogue_org = await db["organizations"].find_one({"code": "CATALOGUE"})
    if not catalogue_org:
        return []

    formations = await list_formations_by_org(str(catalogue_org["_id"]))
    return formations


@router.get("/catalogue/organizations")
async def get_assignable_organizations(current_user: dict = Depends(get_current_user)):
    """
    Liste toutes les organisations (hors CATALOGUE) pour l'affectation.
    Accessible à l'admin catalogue et au superadmin.
    """
    db = get_database()
    user_role = current_user.get("role")

    if user_role == "superadmin":
        pass
    elif not await _is_catalogue_admin(current_user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé à l'administrateur du catalogue.",
        )

    cursor = db["organizations"].find(
        {"code": {"$ne": "CATALOGUE"}, "status": "active"},
        {"_id": 1, "name": 1, "code": 1, "country": 1}
    )
    orgs = []
    async for doc in cursor:
        orgs.append({
            "id": str(doc["_id"]),
            "name": doc.get("name", ""),
            "code": doc.get("code", ""),
            "country": doc.get("country", ""),
        })
    return orgs


@router.post("/{formation_id}/assign")
async def assign_formation_to_orgs(
    formation_id: str,
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Copie une formation du catalogue vers une ou plusieurs organisations.
    Body: { "org_ids": ["<id1>", "<id2>", ...] }
    Accessible à l'admin catalogue et au superadmin.
    """
    import copy

    db = get_database()
    user_role = current_user.get("role")

    if user_role == "superadmin":
        pass
    elif not await _is_catalogue_admin(current_user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé à l'administrateur du catalogue.",
        )

    org_ids = body.get("org_ids", [])
    if not org_ids:
        raise HTTPException(status_code=400, detail="Aucune organisation fournie.")

    # Récupérer la formation source
    try:
        source_oid = ObjectId(formation_id)
    except Exception:
        raise HTTPException(status_code=400, detail="formation_id invalide.")

    source = await db["formations"].find_one({"_id": source_oid})
    if not source:
        raise HTTPException(status_code=404, detail="Formation introuvable.")

    results = []
    for org_id in org_ids:
        try:
            target_oid = ObjectId(org_id)
        except Exception:
            results.append({"org_id": org_id, "status": "error", "detail": "org_id invalide"})
            continue

        # Vérifier que l'org existe
        org = await db["organizations"].find_one({"_id": target_oid})
        if not org:
            results.append({"org_id": org_id, "status": "error", "detail": "Organisation introuvable"})
            continue

        # Vérifier doublon
        existing = await db["formations"].find_one({
            "titre": source["titre"],
            "organization_id": target_oid,
        })
        if existing:
            results.append({
                "org_id": org_id,
                "org_name": org.get("name"),
                "status": "skipped",
                "detail": "Formation déjà présente dans cette organisation",
            })
            continue

        # Copie profonde avec nouveaux ObjectIds
        doc = copy.deepcopy(source)
        doc.pop("_id")
        doc["organization_id"] = target_oid
        doc["created_at"] = datetime.utcnow()

        for m in doc.get("modules", []):
            m["_id"] = ObjectId()
            for ch in m.get("chapitres", []):
                ch["_id"] = ObjectId()
                for p in ch.get("parties", []):
                    p["_id"] = ObjectId()

        inserted = await db["formations"].insert_one(doc)
        results.append({
            "org_id": org_id,
            "org_name": org.get("name"),
            "status": "assigned",
            "formation_id": str(inserted.inserted_id),
        })

    assigned = [r for r in results if r["status"] == "assigned"]
    skipped  = [r for r in results if r["status"] == "skipped"]
    errors   = [r for r in results if r["status"] == "error"]

    return {
        "formation_titre": source.get("titre"),
        "total": len(org_ids),
        "assigned": len(assigned),
        "skipped": len(skipped),
        "errors": len(errors),
        "details": results,
    }
