from typing import Optional

from pydantic import BaseModel, Field


class ConsommableBase(BaseModel):
    type: str = Field(..., example="Carton de Ramme de papier")
    description: Optional[str] = Field(None, example="Cartons de papier A4")

    # Unité de base (ce qu'on utilise vraiment)
    unite_base: str = Field("unité", example="paquet")

    # Unité de conteneur (ce qu'on stocke)
    unite_conteneur: str = Field("unité", example="carton")
    quantite_par_conteneur: int = Field(
        1, ge=1, example=5, description="Nombre d'unités de base par conteneur"
    )

    # Stock en conteneurs
    quantite_stock_conteneur: int = Field(
        0, ge=0, example=10, description="Nombre de conteneurs en stock"
    )

    # Quantité totale calculée (quantite_stock_conteneur × quantite_par_conteneur)
    quantite_stock_total: int = Field(
        0, ge=0, example=50, description="Quantité totale en unités de base"
    )

    # Seuil d'alerte en conteneurs
    limite_alerte: int = Field(0, ge=0, example=2)


class ConsommableCreate(ConsommableBase):
    pass


class ConsommablePublic(ConsommableBase):
    id: str
    organization_id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ConsommableUpdate(BaseModel):
    type: Optional[str] = None
    description: Optional[str] = None
    quantite_stock: Optional[int] = Field(None, ge=0)
    limite_alerte: Optional[int] = Field(None, ge=0)
    unite: Optional[str] = None


class StockUpdate(BaseModel):
    quantite: int = Field(..., ge=0, example=10)
    operation: str = Field("set", example="set", description="set, add, or subtract")
