"""聊天 API：发送消息 + SSE 事件流."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services import chat_service, session_service

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str
    message: str


@router.post("")
async def send_message(req: ChatRequest):
    """发送消息，启动后台生成任务."""
    # 验证会话存在
    session = session_service.get_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    await chat_service.start_chat(req.session_id, req.message)
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
