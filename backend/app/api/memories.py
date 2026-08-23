"""Schema 记忆管理 API。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services import memory_service

router = APIRouter(prefix="/memories", tags=["memories"])


class MemoryCreateRequest(BaseModel):
    datasource_id: str
    memory_type: str
    entity_type: str | None = None
    entity_name: str | None = None
    content: str


class MemoryUpdateRequest(BaseModel):
    content: str | None = None
    memory_type: str | None = None
    entity_type: str | None = None
    entity_name: str | None = None
    confidence: float | None = None


@router.get("")
def list_memories(
    datasource_id: str = Query(..., description="数据源ID"),
    memory_type: str | None = Query(None, description="记忆类型筛选"),
    entity_type: str | None = Query(None, description="实体类型筛选"),
    search: str | None = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """列出指定数据源的记忆列表。"""
    result = memory_service.list_memories(
        datasource_id,
        memory_type=memory_type,
        entity_type=entity_type,
        search=search,
        page=page,
        page_size=page_size,
    )
    return result


@router.post("")
def create_memory(req: MemoryCreateRequest):
    """手动添加一条记忆。"""
    mem = memory_service.add_memory(
        datasource_id=req.datasource_id,
        memory_type=req.memory_type,
        entity_type=req.entity_type,
        entity_name=req.entity_name,
        content=req.content,
        source="manual_add",
        confidence=1.0,
    )
    return mem


@router.get("/{memory_id}")
def get_memory(memory_id: str):
    """获取单条记忆详情。"""
    mem = memory_service.get_memory(memory_id)
    if mem is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return mem


@router.put("/{memory_id}")
def update_memory(memory_id: str, req: MemoryUpdateRequest):
    """更新记忆内容。"""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    mem = memory_service.update_memory(memory_id, updates)
    if mem is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return mem


@router.delete("/{memory_id}")
def delete_memory(memory_id: str):
    """删除记忆（软删除）。"""
    success = memory_service.delete_memory(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True}
