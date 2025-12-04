from pydantic import BaseModel, Field
from typing import Optional


class DemandeConsommableBase(BaseModel):
    consommable_id: str = Field(..., example="507f1f77bcf86cd799439011")
    quantite_demandee: int = Field(..., gt=0, example=10)
    motif: str = Field(..., example="Pour le service comptabilité")


class DemandeConsommableCreate(DemandeConsommableBase):
    pass


class DemandeConsommablePublic(DemandeConsommableBase):
    id: str
    user_id: str
    department_id: str
    statut: str = Field(..., example="en_attente")
    approbation_directeur: dict = Field(default_factory=dict)
    traitement_stock: dict = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ApprobationDirecteur(BaseModel):
    commentaire: Optional[str] = Field(None, example="Demande approuvée")


class TraitementGestionnaire(BaseModel):
    quantite_accordee: int = Field(..., gt=0, example=10)
    commentaire: Optional[str] = Field(None, example="Stock débité avec succès")

