"""Schema API - 数据源 schema 概览和表详情."""

from fastapi import APIRouter, HTTPException, Query

from app.services import schema_service

router = APIRouter(prefix="/schema", tags=["schema"])


@router.get("")
def get_project_schemas(project_id: str = Query(..., description="项目ID")):
    """获取项目所有数据源的 schema 概览."""
    schemas = schema_service.get_project_schemas(project_id)
    return schemas


@router.get("/table/{datasource_id}/{table_name}")
def get_table_detail(datasource_id: str, table_name: str):
    """获取指定数据源的单表详情."""
    table = schema_service.get_table_detail(datasource_id, table_name)
    if table is None:
        raise HTTPException(status_code=404, detail="表或数据源不存在")
    return table
