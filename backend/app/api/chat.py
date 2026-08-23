"""聊天 API：发送消息 + SSE 事件流."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services import chat_service, session_service
from app.services.result_cache import result_cache

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str
    message: str
    datasource_id: str | None = None


@router.post("")
async def send_message(req: ChatRequest):
    """发送消息，启动后台生成任务."""
    # 验证会话存在
    session = session_service.get_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    await chat_service.start_chat(req.session_id, req.message, req.datasource_id)
    return {
        "session_id": req.session_id,
        "status": "started",
    }


@router.get("/stream/{session_id}")
async def stream_events(session_id: str):
    """SSE 事件流接口."""
    # 验证会话存在
    session = session_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    return StreamingResponse(
        chat_service.event_stream(session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/messages/{message_id}/result")
async def get_result_page(
    message_id: str,
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(100, ge=1, le=500, description="每页条数"),
):
    """分页获取查询结果."""
    cached = result_cache.get(f"msg:{message_id}")
    if cached is None:
        raise HTTPException(status_code=404, detail="结果不存在或已过期")

    total = cached["row_count"]
    all_rows = cached["rows"]
    columns = cached["columns"]

    start = (page - 1) * page_size
    end = start + page_size
    page_rows = all_rows[start:end]

    return {
        "columns": columns,
        "rows": page_rows,
        "page": page,
        "page_size": page_size,
        "total": total,
        "has_more": end < total,
    }
