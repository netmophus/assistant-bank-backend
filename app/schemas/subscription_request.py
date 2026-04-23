"""
Schemas Pydantic pour les demandes d'abonnement publiques.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

# Les 8 pays de la zone UEMOA
UEMOA_COUNTRIES = {
    "Bénin",
    "Burkina Faso",
    "Côte d'Ivoire",
    "Guinée-Bissau",
    "Mali",
    "Niger",
    "Sénégal",
    "Togo",
}


class SubscriptionRequestCreate(BaseModel):
    """Payload public pour soumettre une demande d'abonnement."""

    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    email: EmailStr
    phone_country_code: str = Field(min_length=2, max_length=5)
    phone_number: str = Field(min_length=6, max_length=20)
    country: str
    city: str = Field(min_length=1, max_length=100)
    professional_status: Literal["student", "working"]
    institution: Optional[str] = Field(None, max_length=200)
    plan_requested: Literal["monthly", "semester", "annual"]

    @field_validator("country")
    @classmethod
    def _country_uemoa(cls, v: str) -> str:
        if v not in UEMOA_COUNTRIES:
            raise ValueError(
                f"Pays non supporte. Valeurs acceptees: {sorted(UEMOA_COUNTRIES)}"
            )
        return v

    @model_validator(mode="after")
    def _institution_required_if_working(self):
        # field_validator sur un Optional avec default=None n'est pas appele
        # quand le champ est absent dans Pydantic V2 -> on utilise un
        # model_validator qui s'execute toujours apres la validation de base.
        if self.professional_status == "working":
            if not self.institution or not self.institution.strip():
                raise ValueError(
                    "L'institution est requise pour les professionnels."
                )
        return self


class SubscriptionRequestPublic(BaseModel):
    """Reponse API pour les demandes (admin ou lecture)."""

    id: str
    first_name: str
    last_name: str
    email: str
    phone_country_code: str
    phone_number: str
    country: str
    city: str
    professional_status: str
    institution: Optional[str] = None
    plan_requested: str
    status: str
    admin_notes: Optional[str] = None
    created_at: Optional[datetime] = None
    contacted_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None


class UpdateSubscriptionRequestStatus(BaseModel):
    """Payload admin PATCH pour changer le statut d'une demande."""

    status: Literal["pending", "contacted", "paid", "activated", "rejected"]
    admin_notes: Optional[str] = None
