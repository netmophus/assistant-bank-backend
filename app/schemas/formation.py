"""Schémas Pydantic: Formations.

Ces schémas définissent le contrat JSON (API) entre frontend et backend.

Points clés:
- `Partie.contenu` correspond au *prompt* saisi par l'admin (matière première IA).
- `contenu_genere` correspond au contenu généré automatiquement (IA) et stocké.
- `status` permet de distinguer:
  - `draft`: brouillon (saisie en cours)
  - `published`: publié (visible côté user)
"""

from pydantic import BaseModel, Field
from typing import Optional, List


class PartieBase(BaseModel):
    titre: str = Field(default="", example="Introduction aux crédits")
    contenu: str = Field(default="", description="Prompt pour l'IA pour générer cette partie")


class PartieCreate(PartieBase):
    pass


class PartiePublic(PartieBase):
    id: str
    ordre: int = 0
    contenu_genere: Optional[str] = Field(None, description="Contenu généré par l'IA pour cette partie")


class ChapitreBase(BaseModel):
    titre: str = Field(default="", example="Chapitre 1: Notions clés")
    introduction: str = Field(default="", description="Introduction du chapitre")
    nombre_parties: int = Field(default=0, ge=0, description="Nombre de parties dans ce chapitre")
    contenu_genere: Optional[str] = Field(None, description="Contenu généré par l'IA")


class ChapitreCreate(ChapitreBase):
    parties: List[PartieCreate] = Field(default_factory=list)


class ChapitrePublic(ChapitreBase):
    id: str
    ordre: int = 0
    parties: List[PartiePublic] = []


class ModuleBase(BaseModel):
    titre: str = Field(default="", example="Module 1: Introduction à la banque")
    nombre_chapitres: int = Field(default=0, ge=0, description="Nombre de chapitres dans ce module")


class ModuleCreate(ModuleBase):
    chapitres: List[ChapitreCreate] = Field(default_factory=list)
    questions_qcm: Optional[List[dict]] = Field(default_factory=list, description="Questions QCM générées par l'IA")


class ModulePublic(ModuleBase):
    id: str
    ordre: int = 0
    chapitres: List[ChapitrePublic] = []
    questions_qcm: Optional[List[dict]] = Field(default_factory=list, description="Questions QCM générées par l'IA")


class FormationBase(BaseModel):
    titre: str = Field(default="", example="Formation sur la réglementation bancaire")
    description: Optional[str] = Field(None, example="Formation complète sur la réglementation UEMOA")
    bloc_numero: Optional[int] = Field(None, description="Numéro du bloc de formation (ex: 1)")
    bloc_titre: Optional[str] = Field(None, description="Titre du bloc (ex: Plan Comptable Bancaire)")


class FormationCreate(FormationBase):
    organization_id: Optional[str] = Field(None, description="ID de l'organisation")
    modules: List[ModuleCreate] = Field(default_factory=list)
    status: Optional[str] = Field("draft", description="Statut de la formation (draft par défaut)")


class FormationUpdate(BaseModel):
    titre: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None  # draft, published, archived
    modules: Optional[List[ModuleCreate]] = None
    bloc_numero: Optional[int] = None
    bloc_titre: Optional[str] = None


class FormationDepartmentAssignment(BaseModel):
    formation_id: str
    department_ids: List[str] = Field(..., description="Liste des IDs des départements")


class FormationPublic(FormationBase):
    id: str
    organization_id: str
    status: str = "draft"  # draft, published, archived
    is_ready_to_distribute: Optional[bool] = Field(
        False,
        description="True si status=published ET tous chapitres ont contenu_genere ET tous modules ont QCM. Utilise par l'UI catalogue."
    )
    modules: List[ModulePublic] = Field(default_factory=list, description="Liste des modules de la formation")
    modules_count: Optional[int] = 0
    created_at: Optional[str] = None
    bloc_label: Optional[str] = Field(None, description="Label complet: BLOC N — Titre")
    # Rempli uniquement par publish_formation quand auto_generate_* est demande
    generation_stats: Optional[dict] = Field(
        None,
        description="Stats de generation IA : content_ok, content_failed, qcm_ok, qcm_failed, errors[]. Seulement present apres /publish avec auto_generate_*."
    )

