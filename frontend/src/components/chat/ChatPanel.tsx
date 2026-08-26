/**
 * 聊天主面板
 * 玻璃质感风格
 *
 * - 消息列表
 * - 输入框
 * - 数据源选择器
 * - 如无会话，输入第一条消息时自动创建
 */
import { useEffect, useRef, useState } from 'react'
import { Sparkles } from 'lucide-react'
import { useChat } from '../../hooks/useChat'
import { MessageList } from './MessageList'
import { ChatInput } from './ChatInput'
import { DatasourceSelector } from './DatasourceSelector'
import { MemorySavedToast } from './MemorySavedToast'
import type { Session, Datasource } from '../../lib/types'
import { createSession, listDatasources } from '../../lib/api'
import { useTranslation } from '../../i18n'

interface ChatPanelProps {
  projectId: string
  session: Session | null
  onSessionCreated: (s: Session) => void
}

export function ChatPanel({ projectId, session, onSessionCreated }: ChatPanelProps) {
  const { t } = useTranslation()
  const {
    messages,
    isLoading,
    isStreaming,
    thinkingSteps,
    streamingSql,
    awaitingClarification,
    memorySavedNotice,
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
    <div className="flex-1 flex flex-col min-w-0">
      {/* 会话标题栏 - 玻璃质感 */}
      {session && (
        <div className="h-12 border-b border-white/30 bg-white/40 backdrop-blur-lg flex items-center px-5 shrink-0">
          <span className="text-sm font-medium text-slate-600 truncate">
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
            streamingSql={streamingSql}
          />
        )}
      </div>

      {/* 数据源选择器 + 输入框 - 玻璃质感底部 */}
      <div className="border-t border-white/40 bg-white/60 backdrop-blur-xl shrink-0">
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
              ? t('chat.placeholder.noDatasource')
              : awaitingClarification
                ? t('chat.placeholder.clarification')
                : t('chat.placeholder.default')
          }
        />
      </div>

      {/* 记忆保存提示 Toast */}
      <MemorySavedToast notice={memorySavedNotice} />
    </div>
  )
}

function EmptyState() {
  const { t } = useTranslation()
  const samples = [
    t('samples.totalUsers'),
    t('samples.dau7d'),
    t('samples.top10Orders'),
    t('samples.deptHeadcount'),
  ]

  return (
    <div className="h-full flex flex-col items-center justify-center text-slate-400 px-6 relative">
      {/* 装饰性渐变光晕 */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-96 h-96 bg-gradient-to-r from-brand-400/20 to-violet-400/20 rounded-full blur-3xl pointer-events-none" />

      <div className="relative z-10 flex flex-col items-center">
        <div className="w-16 h-16 rounded-3xl bg-gradient-to-br from-brand-500 to-violet-500 text-white flex items-center justify-center shadow-glow-lg mb-4">
          <Sparkles size={28} />
        </div>
        <p className="text-base font-medium text-slate-600">{t('chat.emptyTitle')}</p>
        <p className="text-sm text-slate-400 mt-1">{t('chat.emptySubtitle')}</p>

        <div className="mt-8 grid grid-cols-2 gap-3 max-w-lg w-full">
          {samples.map((q) => (
            <div
              key={q}
              className="text-sm bg-white/60 backdrop-blur border border-white/60 rounded-2xl px-4 py-3 text-slate-500 hover:bg-white/80 hover:border-brand-300/40 transition-all cursor-default shadow-glass"
            >
              {q}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
