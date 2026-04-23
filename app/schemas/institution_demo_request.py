"""
Schemas Pydantic pour les demandes de demonstration B2B (institutions).
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

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

# Modules d'interet possibles (correspondent aux 3 modules institution)
ALLOWED_MODULES = {"credit", "impayes", "pcb", "all"}

InstitutionTypeLiteral = Literal[
    "banque_commerciale",
    "sfd",
    "microfinance",
    "assurance",
    "autre",
]

FunctionLiteral = Literal[
    "dg",
    "drh",
    "dsi",
    "risques",
    "credit",
    "conformite",
    "autre",
]

EstimatedUsersLiteral = Literal["1-10", "11-50", "51-200", "200+"]

InstitutionDemoStatusLiteral = Literal[
    "pending",
    "contacted",
    "meeting_scheduled",
    "proposal_sent",
    "won",
    "lost",
]


class InstitutionDemoCreate(BaseModel):
    """Payload public pour soumettre une demande de demonstration institution."""

    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    function: FunctionLiteral
    email: EmailStr
    phone_country_code: str = Field(min_length=2, max_length=5)
    phone_number: str = Field(min_length=6, max_length=20)
    country: str
    institution_name: str = Field(min_length=1, max_length=200)
    institution_type: InstitutionTypeLiteral
    modules_interest: List[str] = Field(min_length=1)
    estimated_users: EstimatedUsersLiteral
    message: Optional[str] = Field(None, max_length=2000)

    @field_validator("country")
    @classmethod
    def _country_uemoa(cls, v: str) -> str:
        if v not in UEMOA_COUNTRIES:
            raise ValueError(
                f"Pays non supporte. Valeurs acceptees: {sorted(UEMOA_COUNTRIES)}"
            )
        return v

    @field_validator("modules_interest")
    @classmethod
    def _modules_in_allowed(cls, v: List[str]) -> List[str]:
        unknown = [m for m in v if m not in ALLOWED_MODULES]
        if unknown:
            raise ValueError(
                f"Modules invalides : {unknown}. Valeurs acceptees: {sorted(ALLOWED_MODULES)}"
            )
        # Deduplique en preservant l'ordre
        seen = set()
        result = []
        for m in v:
            if m not in seen:
                seen.add(m)
                result.append(m)
        return result


class InstitutionDemoPublic(BaseModel):
    """Reponse API pour les demandes (admin ou lecture)."""

    id: str
    first_name: str
    last_name: str
    function: str
    email: str
    phone_country_code: str
    phone_number: str
    country: str
    institution_name: str
    institution_type: str
    modules_interest: List[str]
    estimated_users: str
    message: Optional[str] = None
    status: str
    admin_notes: Optional[str] = None
    created_at: Optional[datetime] = None
    contacted_at: Optional[datetime] = None
    meeting_scheduled_at: Optional[datetime] = None
    proposal_sent_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


class UpdateInstitutionDemoStatus(BaseModel):
    """Payload admin PATCH pour changer le statut d'une demande institution."""

    status: InstitutionDemoStatusLiteral
    admin_notes: Optional[str] = None
