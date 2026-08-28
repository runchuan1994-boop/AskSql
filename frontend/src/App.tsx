/**
 * 应用入口组件
 *
 * 简化版 V1：默认加载第一个项目，支持会话切换和聊天。
 * 项目和会话选择持久化到 localStorage，刷新后保持。
 */
import { useEffect, useState } from 'react'
import { AppLayout } from './components/layout/AppLayout'
import { listProjects } from './lib/api'
import type { Project, Session } from './lib/types'
import { useTranslation } from './i18n'

const LS_PROJECT_KEY = 'asksql:active_project_id'
const LS_SESSION_KEY = 'asksql:active_session_id'

function App() {
  const { t } = useTranslation()
  const [projects, setProjects] = useState<Project[]>([])
  const [activeProject, setActiveProject] = useState<Project | null>(null)
  const [activeSession, setActiveSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 持久化选中的项目
  const handleSelectProject = (project: Project) => {
    setActiveProject(project)
    setActiveSession(null) // 切换项目时清空会话
    try {
      localStorage.setItem(LS_PROJECT_KEY, project.id)
      localStorage.removeItem(LS_SESSION_KEY)
    } catch {
      // localStorage 不可用时忽略
    }
  }

  // 持久化选中的会话
  const handleSelectSession = (session: Session | null) => {
    setActiveSession(session)
    try {
      if (session) {
        localStorage.setItem(LS_SESSION_KEY, session.id)
      } else {
        localStorage.removeItem(LS_SESSION_KEY)
      }
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    let mounted = true
    async function load() {
      try {
        const projs = await listProjects()
        if (!mounted) return
        setProjects(projs)
        if (projs.length > 0) {
          // 尝试从 localStorage 恢复上次选中的项目
          const savedId = localStorage.getItem(LS_PROJECT_KEY)
          const saved = savedId ? projs.find((p) => p.id === savedId) : null
          setActiveProject(saved ?? projs[0])
        }
      } catch (e) {
        if (!mounted) return
        setError(e instanceof Error ? e.message : '加载项目失败')
      } finally {
        if (mounted) setLoading(false)
      }
    }
    load()
    return () => {
      mounted = false
    }
  }, [])

  if (loading) {
    return (
      <div className="h-full w-full flex items-center justify-center text-slate-500">
        {t('app.loading')}
      </div>
    )
  }

  if (error) {
    return (
      <div className="h-full w-full flex items-center justify-center text-red-500">
        {t('app.error')}: {error}
      </div>
    )
  }

  if (!activeProject) {
    return (
      <div className="h-full w-full flex items-center justify-center text-slate-500">
        {t('app.noProject')}
      </div>
    )
  }

  return (
    <AppLayout
      project={activeProject}
      projects={projects}
      onSelectProject={handleSelectProject}
      activeSession={activeSession}
      onSelectSession={handleSelectSession}
      onSessionCreated={(session) => {
        handleSelectSession(session)
      }}
    />
  )
}

export default App
