from pydantic import BaseModel, Field
from typing import Optional, List


class DepartmentBase(BaseModel):
    name: str = Field(..., example="Ressources Humaines")
    code: str = Field(..., example="RH")
    description: Optional[str] = Field(None, example="Gestion des ressources humaines")


class DepartmentCreate(DepartmentBase):
    organization_id: str = Field(..., description="ID de l'organisation")


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class DepartmentPublic(DepartmentBase):
    id: str
    organization_id: str
    status: str = "active"
    services_count: Optional[int] = 0
    users_count: Optional[int] = 0


class ServiceBase(BaseModel):
    name: str = Field(..., example="Recrutement")
    code: str = Field(..., example="REC")
    description: Optional[str] = Field(None, example="Service de recrutement")


class ServiceCreate(ServiceBase):
    department_id: str = Field(..., description="ID du département")


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class ServicePublic(ServiceBase):
    id: str
    department_id: str
    status: str = "active"
    users_count: Optional[int] = 0

