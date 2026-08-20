"""数据源管理 API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services import datasource_service, schema_import

router = APIRouter(prefix="/datasources", tags=["datasources"])


class DatasourceCreate(BaseModel):
    project_id: str
    name: str
    type: str
    host: str = ""
    port: int | None = None
    database: str = ""
    username: str = ""
    password: str = ""


class DatasourceUpdate(BaseModel):
    name: str | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None


@router.get("")
def list_datasources(project_id: str = Query(...)):
    return datasource_service.list_datasources(project_id)


@router.get("/{datasource_id}")
def get_datasource(datasource_id: str):
    ds = datasource_service.get_datasource(datasource_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="Datasource not found")
    return ds


@router.post("")
def create_datasource(body: DatasourceCreate):
    return datasource_service.create_datasource(
        project_id=body.project_id,
        name=body.name,
        ds_type=body.type,
        host=body.host,
        port=body.port,
        database=body.database,
        username=body.username,
        password=body.password,
    )


@router.patch("/{datasource_id}")
def update_datasource(datasource_id: str, body: DatasourceUpdate):
    ds = datasource_service.update_datasource(
        datasource_id,
        name=body.name,
        host=body.host,
        port=body.port,
        database=body.database,
        username=body.username,
        password=body.password,
    )
    if ds is None:
        raise HTTPException(status_code=404, detail="Datasource not found")
    return ds


@router.delete("/{datasource_id}")
def delete_datasource(datasource_id: str):
    success = datasource_service.delete_datasource(datasource_id)
    if not success:
        raise HTTPException(status_code=404, detail="Datasource not found")
    return {"success": True}


@router.post("/{datasource_id}/test-connection")
def test_connection(datasource_id: str):
    success, message = datasource_service.test_connection_by_id(datasource_id)
    if not success and "not found" in message.lower():
        raise HTTPException(status_code=404, detail=message)
    return {"success": success, "message": message}


@router.post("/{datasource_id}/import-schema")
def import_schema(datasource_id: str, use_llm: bool = Query(False)):
    ds = datasource_service.get_datasource(datasource_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="Datasource not found")

    result = schema_import.import_schema_from_database(datasource_id, use_llm=use_llm)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Import failed"))
    return result
