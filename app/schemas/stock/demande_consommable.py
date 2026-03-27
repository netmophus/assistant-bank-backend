from typing import Optional

from pydantic import BaseModel, Field


class DemandeConsommableBase(BaseModel):
    consommable_id: str = Field(..., example="507f1f77bcf86cd799439011")
    quantite_demandee: int = Field(..., gt=0, example=10)
    motif: str = Field(..., example="Pour le service comptabilité")
    type_selection: Optional[str] = Field(
        "conteneur",
        example="conteneur",
        description="Type de sélection: 'conteneur' ou 'unite'",
    )


class DemandeConsommableCreate(DemandeConsommableBase):
    pass


class DemandeConsommablePublic(DemandeConsommableBase):
    id: str
    user_id: str
    user_name: Optional[str] = Field(None, description="Nom complet de l'utilisateur demandeur")
    department_id: str
    statut: str = Field(..., example="en_attente")
    approbation_directeur: dict = Field(default_factory=dict)
    approbation_drh: dict = Field(default_factory=dict)
    formalisation_drh: dict = Field(default_factory=dict)
    validation_sortie: dict = Field(default_factory=dict)
    traitement_stock: dict = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ApprobationDirecteur(BaseModel):
    commentaire: Optional[str] = Field(None, example="Demande approuvée")


class FormalisationDRH(BaseModel):
    commentaire: Optional[str] = Field(None, example="Demande formalisée par la DRH")


class ValidationSortie(BaseModel):
    quantite_accordee: int = Field(..., gt=0, example=10)
    commentaire: Optional[str] = Field(None, example="Sortie validée conjointement")
    valide_par_agent_departement: bool = Field(False, description="Validation par l'agent du département")
    valide_par_agent_stock: bool = Field(False, description="Validation par l'agent stock DRH")


class TraitementGestionnaire(BaseModel):
    quantite_accordee: int = Field(..., gt=0, example=10)
    commentaire: Optional[str] = Field(None, example="Stock débité avec succès")
