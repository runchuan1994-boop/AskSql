/**
 * 整体布局：Header + Sidebar + 主内容区（聊天）
 */
import { useState } from 'react'
import { Database, Menu, X } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { ChatPanel } from '../chat/ChatPanel'
import { SchemaPanel } from '../schema/SchemaPanel'
import type { Project, Session } from '../../lib/types'
import { clsx } from '../../lib/utils'

interface AppLayoutProps {
  project: Project
  projects: Project[]
  onSelectProject: (p: Project) => void
  activeSession: Session | null
  onSelectSession: (s: Session) => void
  onSessionCreated: (s: Session) => void
}

export function AppLayout({
  project,
  projects,
  onSelectProject,
  activeSession,
  onSelectSession,
  onSessionCreated,
}: AppLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [schemaOpen, setSchemaOpen] = useState(false)

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <header className="h-14 border-b border-gray-200 bg-white flex items-center px-4 gap-3 shrink-0">
        <button
          className="p-1.5 rounded hover:bg-gray-100 text-gray-600"
          onClick={() => setSidebarOpen(!sidebarOpen)}
          title={sidebarOpen ? '收起侧边栏' : '展开侧边栏'}
        >
          {sidebarOpen ? <X size={18} /> : <Menu size={18} />}
        </button>

        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-md bg-indigo-600 text-white flex items-center justify-center">
            <Database size={16} />
          </div>
          <h1 className="text-base font-semibold text-gray-800">NL2SQL</h1>
        </div>

        <div className="flex-1" />

        {/* 项目选择器（简化版下拉） */}
        {projects.length > 1 && (
          <select
            value={project.id}
            onChange={(e) => {
              const p = projects.find((x) => x.id === e.target.value)
              if (p) onSelectProject(p)
            }}
            className="text-sm border border-gray-300 rounded-md px-2 py-1 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        )}

        <span className="text-sm text-gray-600 font-medium">{project.name}</span>

        <button
          className={clsx(
            'px-3 py-1.5 text-sm rounded-md border transition-colors',
            schemaOpen
              ? 'bg-indigo-50 border-indigo-300 text-indigo-700'
              : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50',
          )}
          onClick={() => setSchemaOpen(!schemaOpen)}
        >
          Schema
        </button>
      </header>

      {/* 主内容区 */}
      <div className="flex-1 flex min-h-0">
        {/* 侧边栏 */}
        {sidebarOpen && (
          <Sidebar
            projectId={project.id}
            activeSession={activeSession}
            onSelectSession={onSelectSession}
            onSessionCreated={onSessionCreated}
          />
        )}

        {/* 聊天区 */}
        <div className="flex-1 flex min-w-0">
          <ChatPanel
            projectId={project.id}
            session={activeSession}
            onSessionCreated={(s) => {
              onSessionCreated(s)
            }}
          />

          {/* Schema 面板 */}
          {schemaOpen && (
            <div className="w-80 border-l border-gray-200 bg-white flex-shrink-0 overflow-hidden">
              <SchemaPanel projectId={project.id} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
