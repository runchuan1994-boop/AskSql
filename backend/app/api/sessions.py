"""会话管理 API."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services import session_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    project_id: str
    title: str | None = None


class UpdateSessionRequest(BaseModel):
    title: str | None = None


@router.get("")
def list_sessions(project_id: str = Query(..., description="项目ID")):
    """获取项目的会话列表，按更新时间倒序."""
    sessions = session_service.list_sessions(project_id)
    return sessions


@router.post("")
def create_session(req: CreateSessionRequest):
    """创建新会话."""
    title = req.title if req.title is not None else "新对话"
    session = session_service.create_session(req.project_id, title=title)
    return session


@router.get("/{session_id}")
def get_session(session_id: str):
    """获取会话详情."""
    session = session_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.patch("/{session_id}")
def update_session(session_id: str, req: UpdateSessionRequest):
    """更新会话标题."""
    session = session_service.update_session(session_id, title=req.title)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.delete("/{session_id}")
def delete_session(session_id: str):
    """删除会话（级联删除消息）."""
    success = session_service.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"deleted": True}


@router.get("/{session_id}/messages")
def get_messages(session_id: str):
    """获取会话的所有消息."""
    # 检查会话是否存在
    session = session_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = session_service.get_messages(session_id)
    return messages
