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


class FormationCreate(FormationBase):
    organization_id: str = Field(..., description="ID de l'organisation")
    modules: List[ModuleCreate] = Field(default_factory=list)
    status: Optional[str] = Field("draft", description="Statut de la formation (draft par défaut)")


class FormationUpdate(BaseModel):
    titre: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None  # draft, published, archived
    modules: Optional[List[ModuleCreate]] = None


class FormationDepartmentAssignment(BaseModel):
    formation_id: str
    department_ids: List[str] = Field(..., description="Liste des IDs des départements")


class FormationPublic(FormationBase):
    id: str
    organization_id: str
    status: str = "draft"  # draft, published, archived
    modules: List[ModulePublic] = Field(default_factory=list, description="Liste des modules de la formation")
    modules_count: Optional[int] = 0
    created_at: Optional[str] = None

