from fastapi import APIRouter, HTTPException, status, Depends

from app.schemas.department import (
    DepartmentCreate, DepartmentPublic, DepartmentUpdate,
    ServiceCreate, ServicePublic, ServiceUpdate
)
from app.models.department import (
    create_department, list_departments_by_org, update_department,
    create_service, list_services_by_department, update_service
)
from app.core.deps import get_current_user

router = APIRouter(
    prefix="/departments",
    tags=["departments"],
)


@router.post("", response_model=DepartmentPublic)
async def create_dept(
    dept_in: DepartmentCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Crée un département pour l'organisation de l'admin connecté.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    # Vérifier que l'utilisateur est un admin d'organisation
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent créer des départements.",
        )
    
    # Vérifier que le département est créé pour la bonne organisation
    if dept_in.organization_id != str(user_org_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez créer des départements que pour votre propre organisation.",
        )
    
    try:
        dept = await create_department(dept_in, str(user_org_id))
        return dept
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("", response_model=list[DepartmentPublic])
async def get_departments(current_user: dict = Depends(get_current_user)):
    """
    Liste les départements de l'organisation de l'admin connecté.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    # Vérifier que l'utilisateur est un admin d'organisation
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent voir les départements.",
        )
    
    departments = await list_departments_by_org(str(user_org_id))
    return departments


@router.put("/{dept_id}", response_model=DepartmentPublic)
async def update_dept(
    dept_id: str,
    dept_update: DepartmentUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Met à jour un département.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent modifier les départements.",
        )
    
    try:
        update_data = dept_update.model_dump(exclude_unset=True)
        dept = await update_department(dept_id, update_data, str(user_org_id))
        return dept
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/services", response_model=ServicePublic)
async def create_svc(
    service_in: ServiceCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Crée un service pour un département.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent créer des services.",
        )
    
    try:
        service = await create_service(service_in, service_in.department_id, str(user_org_id))
        return service
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/services/by-department/{dept_id}", response_model=list[ServicePublic])
async def get_services_by_dept(
    dept_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Liste les services d'un département.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent voir les services.",
        )
    
    services = await list_services_by_department(dept_id)
    return services


@router.put("/services/{service_id}", response_model=ServicePublic)
async def update_svc(
    service_id: str,
    service_update: ServiceUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Met à jour un service.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent modifier les services.",
        )
    
    try:
        update_data = service_update.model_dump(exclude_unset=True)
        service = await update_service(service_id, update_data, str(user_org_id))
        return service
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

