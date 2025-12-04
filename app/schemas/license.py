from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date


class LicenseBase(BaseModel):
    organization_id: str = Field(..., description="ID de la banque (organization)")
    plan: str = Field(..., example="Standard")  # Standard, Pro, etc.
    max_users: int = Field(..., ge=1, example=50)
    start_date: date
    end_date: date
    status: str = Field("active", example="active")  # active, expired, suspended
    features: List[str] = Field(
        default_factory=list,
        example=["bank_qa", "letters", "training_modules"],
    )


class LicenseCreate(LicenseBase):
    pass


class LicenseUpdate(BaseModel):
    organization_id: Optional[str] = None
    plan: Optional[str] = None
    max_users: Optional[int] = Field(None, ge=1)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None
    features: Optional[List[str]] = None


class LicensePublic(LicenseBase):
    id: str
