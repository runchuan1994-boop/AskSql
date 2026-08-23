/**
 * 聊天主面板
 *
 * - 消息列表
 * - 输入框
 * - 数据源选择器
 * - 如无会话，输入第一条消息时自动创建
 */
import { useEffect, useRef, useState } from 'react'
import { MessageSquarePlus } from 'lucide-react'
import { useChat } from '../../hooks/useChat'
import { MessageList } from './MessageList'
import { ChatInput } from './ChatInput'
import { DatasourceSelector } from './DatasourceSelector'
import type { Session, Datasource } from '../../lib/types'
import { createSession, listDatasources } from '../../lib/api'

interface ChatPanelProps {
  projectId: string
  session: Session | null
  onSessionCreated: (s: Session) => void
}

export function ChatPanel({ projectId, session, onSessionCreated }: ChatPanelProps) {
  const {
    messages,
    isLoading,
    isStreaming,
    thinkingSteps,
    awaitingClarification,
    sendMessage,
    error,
  } = useChat(session?.id || null)

  // 数据源列表
  const [datasources, setDatasources] = useState<Datasource[]>([])
  const [datasourcesLoading, setDatasourcesLoading] = useState(true)
  const [selectedDatasourceId, setSelectedDatasourceId] = useState<string | null>(null)

  // 当用户在无会话状态下发送第一条消息时
  // 先创建会话，切换到该会话，再发送消息
  const [pendingFirstMessage, setPendingFirstMessage] = useState<string | null>(null)
  const didInitRef = useRef(false)

  // 加载数据源列表
  useEffect(() => {
    let mounted = true
    async function load() {
      setDatasourcesLoading(true)
      try {
        const data = await listDatasources(projectId)
        if (mounted) {
          setDatasources(data)
          // 默认选中第一个
          if (data.length > 0 && !selectedDatasourceId) {
            setSelectedDatasourceId(data[0].id)
          }
          // 如果当前选中的数据源不在列表中了，重置
          if (
            selectedDatasourceId &&
            !data.find((d) => d.id === selectedDatasourceId)
          ) {
            setSelectedDatasourceId(data[0]?.id || null)
          }
        }
      } catch {
        // 加载失败，保持空列表
      } finally {
        if (mounted) setDatasourcesLoading(false)
      }
    }
    load()
    return () => {
      mounted = false
    }
  }, [projectId])

  // 如果有 pending 的消息且 session 已切换，发送它
  useEffect(() => {
    if (pendingFirstMessage && session && !didInitRef.current) {
      didInitRef.current = true
      sendMessage(pendingFirstMessage, selectedDatasourceId || undefined).finally(() => {
        setPendingFirstMessage(null)
        didInitRef.current = false
      })
    }
  }, [pendingFirstMessage, session, sendMessage, selectedDatasourceId])

  const handleSend = async (content: string) => {
    if (!content.trim()) return

    // 如果没有会话，先创建一个
    if (!session) {
      try {
        const title = content.slice(0, 30)
        const newSession = await createSession(projectId, title)
        onSessionCreated(newSession)
        // 等 session prop 更新后再发送（由上方 useEffect 处理）
        setPendingFirstMessage(content.trim())
      } catch {
        // 错误会在 UI 中体现
      }
      return
    }

    await sendMessage(content, selectedDatasourceId || undefined)
  }

  const hasDatasources = datasources.length > 0
  // 澄清状态下输入框不禁用（用户需要回复澄清问题）
  const inputDisabled = (isStreaming && !awaitingClarification) || !!pendingFirstMessage || !hasDatasources

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-gray-50">
      {/* 会话标题栏 */}
      {session && (
        <div className="h-12 border-b border-gray-200 bg-white flex items-center px-4 shrink-0">
          <span className="text-sm font-medium text-gray-700 truncate">
            {session.title}
          </span>
        </div>
      )}

      {/* 消息列表 */}
      <div className="flex-1 overflow-hidden">
        {!session && messages.length === 0 && !isStreaming ? (
          <EmptyState />
        ) : (
          <MessageList
            messages={messages}
            isLoading={isLoading}
            isStreaming={isStreaming || !!pendingFirstMessage}
            thinkingSteps={thinkingSteps}
          />
        )}
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="px-4 py-2 bg-red-50 text-red-600 text-sm border-t border-red-100">
          错误: {error}
        </div>
      )}

      {/* 数据源选择器 + 输入框 */}
      <div className="border-t border-gray-200 bg-white shrink-0">
        <div className="max-w-4xl mx-auto px-3 pt-3">
          <DatasourceSelector
            datasources={datasources}
            value={selectedDatasourceId}
            onChange={setSelectedDatasourceId}
            loading={datasourcesLoading}
            disabled={isStreaming || !!pendingFirstMessage}
          />
        </div>
        <ChatInput
          onSend={handleSend}
          disabled={inputDisabled}
          placeholder={
            !hasDatasources
              ? '请先连接数据源...'
              : awaitingClarification
                ? '请回答澄清问题，按 Enter 发送...'
                : '输入你的问题，按 Enter 发送...'
          }
        />
      </div>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="h-full flex flex-col items-center justify-center text-gray-400 px-6">
      <MessageSquarePlus size={48} strokeWidth={1} className="text-gray-300" />
      <p className="mt-3 text-sm">在下方输入问题，开始你的第一次 NL2SQL 对话</p>
      <div className="mt-6 grid grid-cols-2 gap-2 max-w-md">
        {['查询总用户数', '最近 7 天的日活', '订单金额排名 top10', '各部门人数统计'].map(
          (q) => (
            <div
              key={q}
              className="text-xs bg-white border border-gray-200 rounded-md px-3 py-2 text-gray-500"
            >
              {q}
            </div>
          ),
        )}
      </div>
    </div>
  )
}
