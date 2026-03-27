from typing import Optional

from pydantic import BaseModel, Field


class ConsommableBase(BaseModel):
    type: str = Field(..., example="Carton de paquets de Rammes de papier")

    # Quantité d'unités par conteneur
    quantite_par_conteneur: int = Field(
        1, ge=1, example=5, description="Nombre d'unités par conteneur"
    )

    # Stock en conteneurs
    quantite_stock_conteneur: int = Field(
        0, ge=0, example=10, description="Nombre de conteneurs en stock"
    )

    # Quantité totale calculée (quantite_stock_conteneur × quantite_par_conteneur)
    quantite_stock_total: int = Field(
        0, ge=0, example=50, description="Quantité totale en unités"
    )

    # Seuil d'alerte en conteneurs
    limite_alerte: int = Field(0, ge=0, example=2, description="Niveau d'alerte")

    # Champs simplifiés avec valeurs fixes
    description: Optional[str] = Field("", example="")
    unite_base: str = Field("unité", example="unité")
    unite_conteneur: str = Field("conteneur", example="conteneur")


class ConsommableCreate(ConsommableBase):
    pass


class ConsommablePublic(ConsommableBase):
    id: str
    organization_id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ConsommableUpdate(BaseModel):
    type: Optional[str] = None
    quantite_par_conteneur: Optional[int] = Field(None, ge=1)
    quantite_stock_conteneur: Optional[int] = Field(None, ge=0)
    limite_alerte: Optional[int] = Field(None, ge=0)


class StockUpdate(BaseModel):
    quantite: int = Field(..., ge=0, example=10)
    operation: str = Field("set", example="set", description="set, add, or subtract")
