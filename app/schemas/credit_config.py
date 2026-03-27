from typing import Dict, Optional

from pydantic import BaseModel, Field


class CriteresEligibilite(BaseModel):
    salaire_minimum: int = Field(..., ge=500, example=2000)
    anciennete_minimum_mois: int = Field(..., ge=1, le=60, example=6)
    age_maximum: int = Field(..., ge=18, le=80, example=65)
    taux_endettement_max: int = Field(..., ge=10, le=50, example=33)


class CreditConfigBase(BaseModel):
    taux_interet_base: float = Field(..., ge=0, le=20, example=5.0)
    taux_interet_premium: float = Field(..., ge=0, le=20, example=3.5)
    montant_max_credit: int = Field(..., ge=1000, le=1000000, example=100000)
    duree_max_mois: int = Field(..., ge=12, le=360, example=120)
    apport_minimum_pct: int = Field(..., ge=0, le=50, example=20)
    frais_dossier: int = Field(..., ge=0, le=5000, example=500)
    assurance_obligatoire: bool = Field(..., example=True)
    taux_assurance: float = Field(..., ge=0, le=5, example=0.5)
    criteres_eligibilite: CriteresEligibilite


class CreditConfigCreate(CreditConfigBase):
    pass


class CreditConfigUpdate(CreditConfigBase):
    pass


class CreditConfigPublic(CreditConfigBase):
    id: str
    organization_id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CreditStats(BaseModel):
    demandes_en_cours: int = Field(default=0, example=15)
    credits_actifs: int = Field(default=0, example=42)
    taux_approbation: float = Field(default=0.0, example=75.5)
    montant_total_encours: float = Field(default=0.0, example=2500000.0)
    encours_par_type: Dict[str, float] = Field(default_factory=dict)
    evolution_mensuelle: Dict[str, int] = Field(default_factory=dict)
