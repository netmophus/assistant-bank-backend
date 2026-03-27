from typing import Optional
from pydantic import BaseModel, Field, validator
import re


class GlobalKnowledgeCategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Nom de la catégorie")
    slug: str = Field(..., min_length=1, max_length=100, description="Slug unique (utilisé dans l'API)")
    description: Optional[str] = Field(None, max_length=500, description="Description de la catégorie")

    @validator("slug")
    def validate_slug(cls, v):
        """Valide que le slug est au format valide (minuscules, tirets, underscores)."""
        if not re.match(r"^[a-z0-9_-]+$", v):
            raise ValueError("Le slug doit contenir uniquement des lettres minuscules, chiffres, tirets et underscores")
        return v


class GlobalKnowledgeCategoryCreate(GlobalKnowledgeCategoryBase):
    pass


class GlobalKnowledgeCategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    slug: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None

    @validator("slug")
    def validate_slug(cls, v):
        if v is not None and not re.match(r"^[a-z0-9_-]+$", v):
            raise ValueError("Le slug doit contenir uniquement des lettres minuscules, chiffres, tirets et underscores")
        return v


class GlobalKnowledgeCategoryPublic(GlobalKnowledgeCategoryBase):
    id: str
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True

