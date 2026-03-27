from typing import Optional

from pydantic import BaseModel, Field


class IntroductionStockBase(BaseModel):
    consommable_id: str = Field(..., example="507f1f77bcf86cd799439011")
    quantite: int = Field(..., gt=0, example=10, description="Quantité à introduire")
    type_quantite: str = Field(
        "conteneur",
        example="conteneur",
        description="Type de quantité: 'unite' (unités) ou 'conteneur' (conteneurs)",
    )
    operation: str = Field(
        "add",
        example="add",
        description="Type d'opération: 'set' (remplacer), 'add' (ajouter), 'subtract' (soustraire)",
    )
    motif: Optional[str] = Field(None, example="Réapprovisionnement mensuel")


class IntroductionStockCreate(IntroductionStockBase):
    pass


class IntroductionStockPublic(IntroductionStockBase):
    id: str
    gestionnaire_id: str
    organization_id: str
    statut: str = Field(..., example="en_attente")
    validation_drh: dict = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ValidationDRHStock(BaseModel):
    commentaire: Optional[str] = Field(None, example="Stock validé par la DRH")
