from pydantic import BaseModel, Field
from typing import Optional


class OrganizationBase(BaseModel):
    name: str = Field(..., example="BSIC Niger")
    code: str = Field(..., example="BSIC_NER")
    country: Optional[str] = Field(None, example="Niger")


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    country: Optional[str] = None
    status: Optional[str] = None


class OrganizationPublic(OrganizationBase):
    id: str
    status: str = "active"
