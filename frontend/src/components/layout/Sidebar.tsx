/**
 * 会话列表侧边栏
 */
import { useEffect, useState } from 'react'
import { Plus, MessageSquare, Trash2 } from 'lucide-react'
import { createSession, listSessions } from '../../lib/api'
import type { Session } from '../../lib/types'
import { clsx, formatTime, truncate } from '../../lib/utils'

interface SidebarProps {
  projectId: string
  activeSession: Session | null
  onSelectSession: (s: Session) => void
  onSessionCreated: (s: Session) => void
}

export function Sidebar({
  projectId,
  activeSession,
  onSelectSession,
  onSessionCreated,
}: SidebarProps) {
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)

  const loadSessions = async () => {
    setLoading(true)
    try {
      const list = await listSessions(projectId)
      setSessions(list)
    } catch {
      // 静默失败
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSessions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  const handleNewSession = async () => {
    if (creating) return
    setCreating(true)
    try {
      const session = await createSession(projectId, '新对话')
      setSessions((prev) => [session, ...prev])
      onSessionCreated(session)
    } finally {
      setCreating(false)
    }
  }

  return (
    <aside className="w-60 border-r border-gray-200 bg-white flex flex-col shrink-0">
      {/* 新建会话按钮 */}
      <div className="p-3 border-b border-gray-100">
        <button
          onClick={handleNewSession}
          disabled={creating}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 transition-colors text-sm font-medium disabled:opacity-60"
        >
          <Plus size={16} />
          新建会话
        </button>
      </div>

      {/* 会话列表 */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-4 text-center text-sm text-gray-400">加载中...</div>
        ) : sessions.length === 0 ? (
          <div className="p-4 text-center text-sm text-gray-400">暂无会话</div>
        ) : (
          <ul className="py-1">
            {sessions.map((s) => (
              <li key={s.id}>
                <button
                  onClick={() => onSelectSession(s)}
                  className={clsx(
                    'w-full text-left px-3 py-2 flex items-start gap-2 text-sm transition-colors',
                    activeSession?.id === s.id
                      ? 'bg-indigo-50 text-indigo-700'
                      : 'text-gray-700 hover:bg-gray-50',
                  )}
                >
                  <MessageSquare
                    size={16}
                    className={clsx(
                      'mt-0.5 shrink-0',
                      activeSession?.id === s.id
                        ? 'text-indigo-600'
                        : 'text-gray-400',
                    )}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">
                      {truncate(s.title || '新对话', 24)}
                    </div>
                    <div
                      className={clsx(
                        'text-xs mt-0.5',
                        activeSession?.id === s.id
                          ? 'text-indigo-500'
                          : 'text-gray-400',
                      )}
                    >
                      {formatTime(s.updated_at)}
                    </div>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}
