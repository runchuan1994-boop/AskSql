/**
 * 整体布局：Header + Sidebar + 主内容区（聊天）
 * 玻璃质感风格
 */
import { useState } from 'react'
import { Database, Menu, X, Globe, ChevronDown } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { ChatPanel } from '../chat/ChatPanel'
import { SchemaPanel } from '../schema/SchemaPanel'
import type { Project, Session } from '../../lib/types'
import { clsx } from '../../lib/utils'
import { useTranslation, Locale } from '../../i18n'

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
  const [langMenuOpen, setLangMenuOpen] = useState(false)
  const { t, locale, setLocale } = useTranslation()

  const handleLocaleChange = (newLocale: Locale) => {
    setLocale(newLocale)
    setLangMenuOpen(false)
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header - 玻璃磨砂效果 */}
      <header className="h-14 border-b border-white/40 bg-white/60 backdrop-blur-xl flex items-center px-4 gap-3 shrink-0 z-20">
        <button
          className="p-1.5 rounded-xl hover:bg-white/60 text-slate-500 transition-all"
          onClick={() => setSidebarOpen(!sidebarOpen)}
          title={sidebarOpen ? t('layout.toggleSidebar') : t('layout.expandSidebar')}
        >
          {sidebarOpen ? <X size={18} /> : <Menu size={18} />}
        </button>

        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-brand-500 to-violet-500 text-white flex items-center justify-center shadow-glow">
            <Database size={16} />
          </div>
          <h1 className="text-base font-semibold text-slate-800">{t('layout.appName')}</h1>
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
            className="text-sm border border-white/60 bg-white/70 backdrop-blur rounded-xl px-3 py-1.5 text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400/50 transition-all"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        )}

        <span className="text-sm text-slate-600 font-medium">{project.name}</span>

        {/* 语言切换 */}
        <div className="relative">
          <button
            onClick={() => setLangMenuOpen(!langMenuOpen)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-xl border border-white/60 bg-white/70 text-slate-600 hover:bg-white/90 transition-all"
            title={t('lang.switch')}
          >
            <Globe size={14} />
            <span className="font-medium">
              {locale === 'zh-CN' ? '中' : 'EN'}
            </span>
            <ChevronDown size={12} />
          </button>

          {langMenuOpen && (
            <div className="absolute right-0 top-full mt-1 w-36 bg-white/90 backdrop-blur-xl border border-white/60 rounded-2xl shadow-glass-lg overflow-hidden z-50 p-1">
              <button
                onClick={() => handleLocaleChange('zh-CN')}
                className={clsx(
                  'w-full text-left px-3 py-2 text-sm rounded-xl transition-all',
                  locale === 'zh-CN'
                    ? 'bg-brand-500/10 text-brand-700 font-medium'
                    : 'text-slate-600 hover:bg-white/80',
                )}
              >
                🇨🇳 简体中文
              </button>
              <button
                onClick={() => handleLocaleChange('en')}
                className={clsx(
                  'w-full text-left px-3 py-2 text-sm rounded-xl transition-all',
                  locale === 'en'
                    ? 'bg-brand-500/10 text-brand-700 font-medium'
                    : 'text-slate-600 hover:bg-white/80',
                )}
              >
                🇺🇸 English
              </button>
            </div>
          )}
        </div>

        <button
          className={clsx(
            'px-3.5 py-1.5 text-sm rounded-xl border transition-all font-medium',
            schemaOpen
              ? 'bg-gradient-to-r from-brand-500/10 to-violet-500/10 border-brand-400/40 text-brand-600'
              : 'bg-white/70 border-white/60 text-slate-600 hover:bg-white/90',
          )}
          onClick={() => setSchemaOpen(!schemaOpen)}
        >
          {t('layout.schema')}
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

          {/* Schema 面板 - 玻璃质感 */}
          {schemaOpen && (
            <div className="w-80 border-l border-white/40 bg-white/50 backdrop-blur-xl flex-shrink-0 overflow-hidden">
              <SchemaPanel projectId={project.id} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
