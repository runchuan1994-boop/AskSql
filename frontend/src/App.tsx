/**
 * 应用入口组件
 *
 * 简化版 V1：默认加载第一个项目，支持会话切换和聊天。
 */
import { useEffect, useState } from 'react'
import { AppLayout } from './components/layout/AppLayout'
import { listProjects } from './lib/api'
import type { Project, Session } from './lib/types'
import { useTranslation } from './i18n'

function App() {
  const { t } = useTranslation()
  const [projects, setProjects] = useState<Project[]>([])
  const [activeProject, setActiveProject] = useState<Project | null>(null)
  const [activeSession, setActiveSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let mounted = true
    async function load() {
      try {
        const projs = await listProjects()
        if (!mounted) return
        setProjects(projs)
        if (projs.length > 0) {
          setActiveProject(projs[0])
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
      onSelectProject={setActiveProject}
      activeSession={activeSession}
      onSelectSession={setActiveSession}
      onSessionCreated={(session) => {
        setActiveSession(session)
      }}
    />
  )
}

export default App
