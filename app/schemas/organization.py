from pydantic import BaseModel, Field
from typing import Optional, List


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


class WebSearchConfig(BaseModel):
    web_search_enabled: bool = False
    web_search_sites: List[str] = []


class WebSearchConfigUpdate(BaseModel):
    web_search_enabled: Optional[bool] = None
    web_search_sites: Optional[List[str]] = None
