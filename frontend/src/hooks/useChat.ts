/**
 * 聊天逻辑 Hook
 *
 * 管理：
 * - 当前会话的消息列表
 * - 发送消息
 * - SSE 流式接收
 * - 思考状态
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { getMessages, sendChatMessage } from '../lib/api'
import type { Message, SseEvent, QueryResult, ThinkingStage } from '../lib/types'
import { useSSE } from './useSSE'

export interface UseChatReturn {
  messages: Message[]
  isLoading: boolean
  isStreaming: boolean
  currentStage: ThinkingStage | null
  streamingSql: string | null
  sendMessage: (content: string) => Promise<void>
  loadMessages: (sessionId: string) => Promise<void>
  clearMessages: () => void
  error: string | null
}

export function useChat(sessionId: string | null): UseChatReturn {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [currentStage, setCurrentStage] = useState<ThinkingStage | null>(null)
  const [streamingSql, setStreamingSql] = useState<string | null>(null)

  // 跟踪流式过程中的临时状态
  const tempSqlRef = useRef<string>('')

  const handleEvent = useCallback((evt: SseEvent) => {
    switch (evt.event) {
      case 'intent_analysis':
        setCurrentStage('intent_analysis')
        break
      case 'intent_probe':
        setCurrentStage('intent_probe')
        break
      case 'clarification_needed':
        setCurrentStage('clarification_needed')
        break
      case 'sql_generated':
        setCurrentStage('sql_generated')
        if (typeof evt.data.sql === 'string') {
          tempSqlRef.current = evt.data.sql
          setStreamingSql(evt.data.sql)
        }
        break
      case 'sql_executing':
        setCurrentStage('sql_executing')
        if (typeof evt.data.sql === 'string') {
          tempSqlRef.current = evt.data.sql
          setStreamingSql(evt.data.sql)
        }
        break
      case 'sql_executed':
        setCurrentStage('sql_executed')
        break
      case 'reflection':
        setCurrentStage('reflection')
        break
      case 'final_result':
        // 追加助手消息
        const answer = (evt.data.answer as string) || ''
        const sql = (evt.data.sql as string) || tempSqlRef.current
        const result = evt.data.result as QueryResult | undefined
        const assistantMsg: Message = {
          id: `assistant-${Date.now()}`,
          session_id: '',
          role: 'assistant',
          content: answer,
          sql_text: sql || null,
          result: result || null,
          created_at: new Date().toISOString(),
        }
        setMessages((prev) => [...prev, assistantMsg])
        setStreamingSql(null)
        tempSqlRef.current = ''
        break
      case 'error':
        setError((evt.data.message as string) || '发生错误')
        break
      case 'done':
      case 'chat_done':
        setCurrentStage('done')
        // 短暂延迟后清除阶段指示
        setTimeout(() => setCurrentStage(null), 1500)
        break
    }
  }, [])

  const { isStreaming, connect, disconnect } = useSSE(null, {
    onEvent: handleEvent,
  })

  const loadMessages = useCallback(async (sid: string) => {
    setIsLoading(true)
    setError(null)
    try {
      const msgs = await getMessages(sid)
      setMessages(msgs)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载消息失败')
      setMessages([])
    } finally {
      setIsLoading(false)
    }
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
    setError(null)
    setCurrentStage(null)
    setStreamingSql(null)
    tempSqlRef.current = ''
  }, [])

  // sessionId 变化时加载消息
  useEffect(() => {
    if (sessionId) {
      loadMessages(sessionId)
    } else {
      clearMessages()
    }
    disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  const sendMessage = useCallback(
    async (content: string) => {
      if (!sessionId || !content.trim()) return
      setError(null)

      // 立即追加用户消息
      const userMsg: Message = {
        id: `user-${Date.now()}`,
        session_id: sessionId,
        role: 'user',
        content: content.trim(),
        created_at: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, userMsg])

      try {
        // 启动 SSE 连接
        connect(sessionId)

        // 发送消息
        await sendChatMessage(sessionId, content.trim())
      } catch (e) {
        setError(e instanceof Error ? e.message : '发送消息失败')
        disconnect()
      }
    },
    [sessionId, connect, disconnect],
  )

  return {
    messages,
    isLoading,
    isStreaming,
    currentStage,
    streamingSql,
    sendMessage,
    loadMessages,
    clearMessages,
    error,
  }
}
