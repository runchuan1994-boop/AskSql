/**
 * 会话列表侧边栏
 * 玻璃质感风格
 */
import { useEffect, useState } from 'react'
import { Plus, MessageSquare } from 'lucide-react'
import { createSession, listSessions } from '../../lib/api'
import type { Session } from '../../lib/types'
import { clsx, formatTime, truncate } from '../../lib/utils'
import { useTranslation } from '../../i18n'

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
  const { t } = useTranslation()

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
      const session = await createSession(projectId, t('sidebar.newChatDefault'))
      setSessions((prev) => [session, ...prev])
      onSessionCreated(session)
    } finally {
      setCreating(false)
    }
  }

  return (
    <aside className="w-60 border-r border-white/40 bg-white/50 backdrop-blur-xl flex flex-col shrink-0">
      {/* 新建会话按钮 */}
      <div className="p-3 border-b border-white/30">
        <button
          onClick={handleNewSession}
          disabled={creating}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-gradient-to-r from-brand-500 to-violet-500 text-white rounded-2xl hover:from-brand-600 hover:to-violet-600 transition-all text-sm font-medium disabled:opacity-60 shadow-glass hover:shadow-glow active:scale-[0.98]"
        >
          <Plus size={16} />
          {t('sidebar.newChat')}
        </button>
      </div>

      {/* 会话列表 */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-4 text-center text-sm text-slate-400">{t('sidebar.loading')}</div>
        ) : sessions.length === 0 ? (
          <div className="p-4 text-center text-sm text-slate-400">{t('sidebar.noSessions')}</div>
        ) : (
          <ul className="py-2 px-2">
            {sessions.map((s) => (
              <li key={s.id} className="mb-0.5">
                <button
                  onClick={() => onSelectSession(s)}
                  className={clsx(
                    'w-full text-left px-3 py-2.5 flex items-start gap-2 text-sm transition-all rounded-2xl',
                    activeSession?.id === s.id
                      ? 'bg-white/90 text-brand-600 shadow-glass font-medium'
                      : 'text-slate-600 hover:bg-white/40',
                  )}
                >
                  <MessageSquare
                    size={16}
                    className={clsx(
                      'mt-0.5 shrink-0',
                      activeSession?.id === s.id
                        ? 'text-brand-500'
                        : 'text-slate-400',
                    )}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">
                      {truncate(s.title || t('sidebar.newChatDefault'), 24)}
                    </div>
                    <div
                      className={clsx(
                        'text-xs mt-0.5',
                        activeSession?.id === s.id
                          ? 'text-brand-400'
                          : 'text-slate-400',
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
