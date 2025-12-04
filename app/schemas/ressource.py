from pydantic import BaseModel, Field
from typing import Optional, List


class RessourceBase(BaseModel):
    titre: str = Field(..., example="Demande de congé")
    description: Optional[str] = Field(None, example="Formulaire de demande de congé")


class RessourceCreate(RessourceBase):
    pass


class RessourcePublic(RessourceBase):
    id: str
    filename: Optional[str] = None
    file_name: Optional[str] = None  # Alias pour compatibilité
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    organization_id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    departments: Optional[List[dict]] = Field(default_factory=list)


class RessourceUpdate(BaseModel):
    titre: Optional[str] = None
    description: Optional[str] = None


class RessourceDepartmentAssignment(BaseModel):
    ressource_id: str
    department_ids: List[str] = Field(..., example=["507f1f77bcf86cd799439011"])

