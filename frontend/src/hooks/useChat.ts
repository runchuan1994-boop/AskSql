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
import type { Message, SseEvent, QueryResult, ThinkingStage, VizSpec, ThinkingStep } from '../lib/types'
import { useSSE } from './useSSE'

export interface UseChatReturn {
  messages: Message[]
  isLoading: boolean
  isStreaming: boolean
  currentStage: ThinkingStage | null
  streamingSql: string | null
  thinkingSteps: ThinkingStep[]
  awaitingClarification: boolean
  clarificationQuestions: string[]
  sendMessage: (content: string, datasourceId?: string) => Promise<void>
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
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([])
  const [awaitingClarification, setAwaitingClarification] = useState(false)
  const [clarificationQuestions, setClarificationQuestions] = useState<string[]>([])

  // 跟踪流式过程中的临时状态
  const tempSqlRef = useRef<string>('')
  const tempClarificationRef = useRef<string[]>([])

  const handleEvent = useCallback((evt: SseEvent) => {
    switch (evt.event) {
      case 'dispatch_started':
      case 'dispatch_result':
        setCurrentStage('dispatching')
        break
      case 'intent_analysis':
        setCurrentStage('intent_analysis')
        break
      case 'intent_probe':
        setCurrentStage('intent_probe')
        break
      case 'query_rewrite':
        setCurrentStage('query_rewrite')
        break
      case 'clarification_needed': {
        setCurrentStage('clarification_needed')
        const qs = (evt.data.questions as string[]) || []
        tempClarificationRef.current = qs
        setClarificationQuestions(qs)
        break
      }
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
      case 'ds_creating':
      case 'ds_created':
      case 'ds_testing':
        setCurrentStage('connecting_datasource')
        break
      case 'ds_connection_failed':
      case 'ds_create_failed':
        setCurrentStage('connecting_datasource')
        setError('数据源连接失败')
        break
      case 'ds_connected':
      case 'ds_importing':
        setCurrentStage('importing_schema')
        break
      case 'ds_imported':
        setCurrentStage('importing_schema')
        break
      case 'ds_import_failed':
        setCurrentStage('importing_schema')
        setError('Schema 导入失败')
        break
      case 'schema_exploring':
      case 'schema_tool_call':
      case 'schema_tool_result':
      case 'schema_explore_done':
        setCurrentStage('schema_exploring')
        break
      case 'viz_ready':
        setCurrentStage('visualizing')
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last && last.role === 'assistant' && !last.content) {
            const vizData = evt.data as unknown as VizSpec
            if (vizData.charts && vizData.charts.length > 0) {
              return [...prev.slice(0, -1), { ...last, viz: vizData }]
            }
          }
          return prev
        })
        break
      case 'reflection':
        setCurrentStage('reflection')
        break
      case 'step_detail': {
        const stepData = evt.data as unknown as ThinkingStep
        setThinkingSteps((prev) => {
          const idx = prev.findIndex((s) => s.step === stepData.step)
          if (idx >= 0) {
            // Update existing step
            const updated = [...prev]
            updated[idx] = { ...updated[idx], ...stepData }
            return updated
          }
          // Add new step
          return [...prev, stepData]
        })
        break
      }
      case 'final_result': {
        const answer = (evt.data.answer as string) || ''
        const sql = (evt.data.sql as string) || tempSqlRef.current
        const result = evt.data.result as QueryResult | undefined
        const viz = evt.data.viz as VizSpec | undefined
        const clarifQs = (evt.data.clarification_questions as string[]) || []
        const isClarifying = clarifQs.length > 0 && !evt.data.success
        const queryAssumptions = (evt.data.query_assumptions as string[]) || []

        const assistantMsg: Message = {
          id: `assistant-${Date.now()}`,
          session_id: '',
          role: 'assistant',
          content: answer,
          sql_text: sql || null,
          result: result || null,
          viz: viz || null,
          created_at: new Date().toISOString(),
          clarification: isClarifying
            ? { questions: clarifQs, resolved: false }
            : undefined,
          query_assumptions: queryAssumptions.length > 0 ? queryAssumptions : undefined,
        }
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last && last.role === 'assistant' && !last.content) {
            return [...prev.slice(0, -1), assistantMsg]
          }
          return [...prev, assistantMsg]
        })

        if (isClarifying) {
          setAwaitingClarification(true)
          setClarificationQuestions(clarifQs)
        } else {
          setAwaitingClarification(false)
          setClarificationQuestions([])
        }

        setStreamingSql(null)
        tempSqlRef.current = ''
        tempClarificationRef.current = []
        break
      }
      case 'error':
        setError((evt.data.message as string) || '发生错误')
        break
      case 'done':
      case 'chat_done': {
        const doneStatus = (evt.data.status as string) || 'done'
        if (doneStatus === 'clarifying') {
          setCurrentStage('clarification_needed')
          // 澄清状态下保持 stage 显示，等用户回复
        } else {
          setCurrentStage('done')
          setAwaitingClarification(false)
          setClarificationQuestions([])
          // 短暂延迟后清除阶段指示
          setTimeout(() => setCurrentStage(null), 1500)
        }
        break
      }
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
      // 后端把 viz 存在 result 里面，这里统一提升到顶层
      // 保证前端可以统一用 message.viz 访问
      const normalized = msgs.map((msg) => {
        const result = msg.result as Record<string, unknown> | undefined

        // viz 提升
        let viz = msg.viz
        if (!viz) {
          const resultViz = result?.viz as VizSpec | undefined
          if (resultViz?.charts?.length) {
            viz = resultViz
          }
        }

        // 澄清信息：从 result.is_clarification 中提取
        let clarification: Message['clarification'] = undefined
        const isClarification = result?.is_clarification as boolean | undefined
        const clarifQs = (result?.clarification_questions as string[]) || []
        if (isClarification && clarifQs.length > 0) {
          // 判断是否已被回复：如果这条消息后面有用户消息，说明已回复
          clarification = { questions: clarifQs, resolved: false }
        }

        // 查询假设：从 result 中提取
        const resultAssumptions = (result?.query_assumptions as string[]) || []
        const queryAssumptions =
          msg.query_assumptions && msg.query_assumptions.length > 0
            ? msg.query_assumptions
            : resultAssumptions.length > 0
              ? resultAssumptions
              : undefined

        return { ...msg, viz, clarification, query_assumptions: queryAssumptions }
      })

      // 标记已回复的澄清消息：如果一条澄清消息后面跟着用户消息，就是已回复
      for (let i = 0; i < normalized.length; i++) {
        const msg = normalized[i]
        if (msg.clarification && !msg.clarification.resolved) {
          // 找后面第一条非 assistant 消息
          for (let j = i + 1; j < normalized.length; j++) {
            if (normalized[j].role === 'user') {
              normalized[i] = {
                ...normalized[i],
                clarification: { ...normalized[i].clarification!, resolved: true },
              }
              break
            }
          }
        }
      }

      setMessages(normalized)

      // 恢复澄清等待状态：最后一条 assistant 消息如果是未解决的澄清
      const lastAssistant = [...normalized].reverse().find((m) => m.role === 'assistant')
      if (lastAssistant?.clarification && !lastAssistant.clarification.resolved) {
        setAwaitingClarification(true)
        setClarificationQuestions(lastAssistant.clarification.questions)
      } else {
        setAwaitingClarification(false)
        setClarificationQuestions([])
      }
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
    setThinkingSteps([])
    setAwaitingClarification(false)
    setClarificationQuestions([])
    tempSqlRef.current = ''
    tempClarificationRef.current = []
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
    async (content: string, datasourceId?: string) => {
      if (!sessionId || !content.trim()) return
      setError(null)
      setThinkingSteps([])

      // 如果处于澄清状态，先标记上一条澄清消息为已回复
      if (awaitingClarification) {
        setMessages((prev) => {
          const updated = [...prev]
          // 从后往前找第一条未解决的澄清消息
          for (let i = updated.length - 1; i >= 0; i--) {
            const msg = updated[i]
            if (msg.role === 'assistant' && msg.clarification && !msg.clarification.resolved) {
              updated[i] = {
                ...msg,
                clarification: { ...msg.clarification, resolved: true },
              }
              break
            }
          }
          return updated
        })
        setAwaitingClarification(false)
      }

      // 立即追加用户消息
      const userMsg: Message = {
        id: `user-${Date.now()}`,
        session_id: sessionId,
        role: 'user',
        content: content.trim(),
        created_at: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, userMsg])

      // 创建占位助手消息（内容会在 final_result 时填充）
      const placeholderMsg: Message = {
        id: `assistant-placeholder-${Date.now()}`,
        session_id: sessionId,
        role: 'assistant',
        content: '',
        created_at: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, placeholderMsg])

      try {
        // 启动 SSE 连接
        connect(sessionId)

        // 发送消息
        await sendChatMessage(sessionId, content.trim(), datasourceId)
      } catch (e) {
        setError(e instanceof Error ? e.message : '发送消息失败')
        disconnect()
      }
    },
    [sessionId, awaitingClarification, connect, disconnect],
  )

  return {
    messages,
    isLoading,
    isStreaming,
    currentStage,
    streamingSql,
    thinkingSteps,
    awaitingClarification,
    clarificationQuestions,
    sendMessage,
    loadMessages,
    clearMessages,
    error,
  }
}
