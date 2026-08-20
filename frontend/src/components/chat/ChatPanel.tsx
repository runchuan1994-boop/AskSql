/**
 * 聊天主面板
 *
 * - 消息列表
 * - 输入框
 * - 如无会话，输入第一条消息时自动创建
 */
import { useEffect, useRef, useState } from 'react'
import { MessageSquarePlus } from 'lucide-react'
import { useChat } from '../../hooks/useChat'
import { MessageList } from './MessageList'
import { ChatInput } from './ChatInput'
import type { Session } from '../../lib/types'
import { createSession, sendChatMessage } from '../../lib/api'

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
    currentStage,
    streamingSql,
    sendMessage,
    error,
  } = useChat(session?.id || null)

  // 当用户在无会话状态下发送第一条消息时
  // 先创建会话，切换到该会话，再发送消息
  const [pendingFirstMessage, setPendingFirstMessage] = useState<string | null>(null)
  const didInitRef = useRef(false)

  // 如果有 pending 的消息且 session 已切换，发送它
  useEffect(() => {
    if (pendingFirstMessage && session && !didInitRef.current) {
      didInitRef.current = true
      sendMessage(pendingFirstMessage).finally(() => {
        setPendingFirstMessage(null)
        didInitRef.current = false
      })
    }
  }, [pendingFirstMessage, session, sendMessage])

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

    await sendMessage(content)
  }

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
            currentStage={currentStage}
            streamingSql={streamingSql}
          />
        )}
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="px-4 py-2 bg-red-50 text-red-600 text-sm border-t border-red-100">
          错误: {error}
        </div>
      )}

      {/* 输入框 */}
      <ChatInput onSend={handleSend} disabled={isStreaming || !!pendingFirstMessage} />
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
