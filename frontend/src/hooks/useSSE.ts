/**
 * SSE 连接 Hook
 *
 * 使用原生 EventSource 监听 SSE 事件流。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { SseEvent, SseEventType } from '../lib/types'

interface UseSseOptions {
  onEvent?: (event: SseEvent) => void
  onOpen?: () => void
  onError?: (err: Event) => void
  onDone?: () => void
}

export function useSSE(
  sessionId: string | null,
  options: UseSseOptions = {},
): {
  isConnecting: boolean
  isStreaming: boolean
  events: SseEvent[]
  connect: (sid: string) => void
  disconnect: () => void
} {
  const [isConnecting, setIsConnecting] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [events, setEvents] = useState<SseEvent[]>([])
  const sourceRef = useRef<EventSource | null>(null)
  const sessionIdRef = useRef<string | null>(sessionId)

  const disconnect = useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.close()
      sourceRef.current = null
    }
    setIsConnecting(false)
    setIsStreaming(false)
  }, [])

  const connect = useCallback(
    (sid: string) => {
      // 清理旧连接
      disconnect()
      sessionIdRef.current = sid
      setEvents([])
      setIsConnecting(true)

      const source = new EventSource(`/api/chat/stream/${encodeURIComponent(sid)}`)
      sourceRef.current = source

      source.onopen = () => {
        setIsConnecting(false)
        setIsStreaming(true)
        options.onOpen?.()
      }

      source.onerror = (err) => {
        setIsConnecting(false)
        setIsStreaming(false)
        options.onError?.(err)
        // 如果连接已关闭且 readyState 为 CLOSED，说明是服务端主动关闭
        if (source.readyState === EventSource.CLOSED) {
          disconnect()
        }
      }

      // 处理所有事件
      const allEvents: SseEventType[] = [
        'start',
        'dispatch_started',
        'dispatch_result',
        'intent_analysis',
        'intent_probe',
        'clarification_needed',
        'sql_generated',
        'sql_executing',
        'sql_executed',
        'sql_execution_error',
        'sql_execution_failed',
        'reflection',
        'ds_creating',
        'ds_created',
        'ds_create_failed',
        'ds_testing',
        'ds_connected',
        'ds_connection_failed',
        'ds_importing',
        'ds_imported',
        'ds_import_failed',
        'ds_connect_started',
        'schema_exploring',
        'schema_tool_call',
        'schema_tool_result',
        'schema_explore_done',
        'viz_ready',
        'final_result',
        'error',
        'done',
        'chat_done',
        'heartbeat',
      ]

      allEvents.forEach((evtName) => {
        source.addEventListener(evtName, (e: MessageEvent) => {
          let data: Record<string, unknown> = {}
          try {
            data = e.data ? JSON.parse(e.data) : {}
          } catch {
            // ignore parse error
          }
          const evt: SseEvent = { event: evtName, data }
          setEvents((prev) => [...prev, evt])
          options.onEvent?.(evt)

          // 完成事件
          if (evtName === 'chat_done' || evtName === 'done') {
            setIsStreaming(false)
            options.onDone?.()
            disconnect()
          }
        })
      })
    },
    [disconnect, options],
  )

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      disconnect()
    }
  }, [disconnect])

  return {
    isConnecting,
    isStreaming,
    events,
    connect,
    disconnect,
  }
}
