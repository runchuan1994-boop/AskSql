"""项目管理 API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import project_service

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


@router.get("")
def list_projects():
    return project_service.list_projects()


@router.get("/{project_id}")
def get_project(project_id: str):
    project = project_service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("")
def create_project(body: ProjectCreate):
    return project_service.create_project(body.name, body.description)


@router.patch("/{project_id}")
def update_project(project_id: str, body: ProjectUpdate):
    project = project_service.update_project(
        project_id,
        name=body.name,
        description=body.description,
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}")
def delete_project(project_id: str):
    success = project_service.delete_project(project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"success": True}
