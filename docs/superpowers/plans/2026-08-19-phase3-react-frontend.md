# Phase 3: React 前端 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 React 前端界面，提供聊天对话、Schema 浏览、项目管理、数据源管理等完整交互体验。

**Architecture:** React + Vite + TypeScript + TailwindCSS + shadcn/ui。使用 SSE 接收 Agent 流式进展，REST API 发送消息和管理数据。左侧 Schema 面板 + 右侧聊天区的经典布局。

**Tech Stack:** React 18, Vite, TypeScript, TailwindCSS, shadcn/ui, TanStack Table, lucide-react

---

## 文件结构总览

```
frontend/
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.js
├── postcss.config.js
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── index.css
│   ├── lib/
│   │   ├── api.ts              # API 客户端
│   │   ├── sse.ts              # SSE 连接管理
│   │   ├── types.ts            # 类型定义
│   │   └── utils.ts            # 工具函数
│   ├── hooks/
│   │   ├── useChat.ts          # 聊天逻辑 hook
│   │   ├── useSSE.ts           # SSE hook
│   │   └── useProjects.ts      # 项目管理 hook
│   ├── components/
│   │   ├── layout/
│   │   │   ├── AppLayout.tsx   # 整体布局
│   │   │   ├── Sidebar.tsx     # 左侧边栏（项目+会话+Schema）
│   │   │   └── Header.tsx      # 顶部导航
│   │   ├── chat/
│   │   │   ├── ChatPanel.tsx   # 聊天主面板
│   │   │   ├── MessageList.tsx # 消息列表
│   │   │   ├── ChatMessage.tsx # 单条消息
│   │   │   ├── ChatInput.tsx   # 输入框
│   │   │   ├── ResultTable.tsx # 结果表格
│   │   │   ├── SqlDisplay.tsx  # SQL 代码展示
│   │   │   └── ThinkingIndicator.tsx  # 思考中指示器
│   │   ├── schema/
│   │   │   ├── SchemaPanel.tsx # Schema 浏览面板
│   │   │   ├── TableList.tsx   # 表列表
│   │   │   └── TableDetail.tsx # 表详情
│   │   ├── project/
│   │   │   ├── ProjectSwitcher.tsx  # 项目切换
│   │   │   └── ProjectModal.tsx     # 项目创建/编辑弹窗
│   │   └── datasource/
│   │       ├── DatasourceList.tsx   # 数据源列表
│   │       └── DatasourceModal.tsx  # 数据源配置弹窗（含导入）
│   ├── pages/
│   │   ├── ChatPage.tsx        # 聊天页面
│   │   └── SettingsPage.tsx    # 设置页面
│   └── context/
│       └── ProjectContext.tsx  # 项目上下文
```

---

## Task 1: React + Vite + Tailwind 项目初始化

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/index.css`

- [ ] **Step 1: 创建 package.json**

```json
{
  "name": "nl2sql-frontend",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "lint": "eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.23.0",
    "@tanstack/react-table": "^8.16.0",
    "lucide-react": "^0.378.0",
    "clsx": "^2.1.1",
    "tailwind-merge": "^2.3.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.1",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.4.5",
    "vite": "^5.2.11",
    "tailwindcss": "^3.4.3",
    "postcss": "^8.4.38",
    "autoprefixer": "^10.4.19"
  }
}
```

- [ ] **Step 2: 创建 Vite 配置**

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 3: 创建 tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 4: Tailwind 配置**

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
```

- [ ] **Step 5: PostCSS 配置**

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

- [ ] **Step 6: index.html + main.tsx + App.tsx + index.css**

`index.html`:
```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>NL2SQL Agent</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`src/main.tsx`:
```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

`src/App.tsx`:
```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import ChatPage from './pages/ChatPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ChatPage />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
```

`src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

html, body, #root {
  height: 100%;
  margin: 0;
  padding: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}

/* 滚动条样式 */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: #9ca3af;
}
```

`src/pages/ChatPage.tsx`:
```tsx
export default function ChatPage() {
  return (
    <div className="h-full flex items-center justify-center">
      <h1 className="text-2xl font-bold text-gray-700">NL2SQL Agent</h1>
    </div>
  )
}
```

- [ ] **Step 7: 安装依赖并启动验证**

Run: `cd frontend && npm install && npm run dev`
Expected: Vite 启动在 5173 端口，页面显示 "NL2SQL Agent"

- [ ] **Step 8: Commit**

```bash
git add frontend/
git commit -m "feat: React frontend scaffold with Vite + Tailwind"
```

---

## Task 2: 类型定义 + API 客户端 + SSE 工具

**Files:**
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/sse.ts`
- Create: `frontend/src/lib/utils.ts`
- Create: `frontend/src/hooks/useSSE.ts`

- [ ] **Step 1: 类型定义**

```ts
// 项目
export interface Project {
  id: string
  name: string
  description: string
  created_at: string
  updated_at: string
}

// 数据源
export interface Datasource {
  id: string
  project_id: string
  name: string
  type: string
  host?: string
  port?: number
  database?: string
  username?: string
  schema_file?: string
  created_at: string
  updated_at: string
}

// Schema
export interface SchemaColumn {
  name: string
  type: string
  description: string
  is_primary_key: boolean
  is_foreign_key: boolean
  semantic_type?: string
  enum_values?: string[]
}

export interface SchemaTable {
  name: string
  description: string
  columns: SchemaColumn[]
  examples?: Array<{ question: string; sql: string }>
}

export interface DatasourceSchema {
  datasource_id: string
  datasource_name: string
  datasource_type: string
  tables: Array<{ name: string; description: string; column_count: number }>
}

// 会话
export interface Session {
  id: string
  project_id: string
  title: string
  created_at: string
  updated_at: string
}

// 消息
export type MessageRole = 'user' | 'assistant' | 'system'

export interface ChatMessage {
  id: string
  session_id: string
  role: MessageRole
  content: string
  sql_text?: string
  result?: QueryResult
  created_at: string
}

export interface QueryResult {
  columns: string[]
  rows: any[][]
  row_count: number
  success: boolean
  error?: string
}

// SSE 事件
export type SSEEventType =
  | 'start'
  | 'intent_analysis'
  | 'intent_probe'
  | 'sql_generated'
  | 'sql_executing'
  | 'sql_executed'
  | 'reflection'
  | 'clarification_needed'
  | 'final_result'
  | 'error'
  | 'done'

export interface SSEEvent {
  type: SSEEventType
  data: any
}
```

- [ ] **Step 2: API 客户端**

```ts
import type {
  Project, Datasource, DatasourceSchema, SchemaTable,
  Session, ChatMessage,
} from './types'

const API_BASE = '/api'

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

// 项目
export const projectsApi = {
  list: () => request<{ projects: Project[] }>('/projects'),
  get: (id: string) => request<Project>(`/projects/${id}`),
  create: (name: string, description = '') =>
    request<Project>('/projects', { method: 'POST', body: JSON.stringify({ name, description }) }),
  update: (id: string, data: Partial<Pick<Project, 'name' | 'description'>>) =>
    request<Project>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  delete: (id: string) => request<{ success: boolean }>(`/projects/${id}`, { method: 'DELETE' }),
}

// 数据源
export const datasourcesApi = {
  list: (projectId: string) =>
    request<{ datasources: Datasource[] }>(`/datasources?project_id=${projectId}`),
  get: (id: string) => request<Datasource>(`/datasources/${id}`),
  create: (data: Partial<Datasource> & { project_id: string; password?: string }) =>
    request<Datasource>('/datasources', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: string, data: any) =>
    request<Datasource>(`/datasources/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  delete: (id: string) =>
    request<{ success: boolean }>(`/datasources/${id}`, { method: 'DELETE' }),
  testConnection: (id: string) =>
    request<{ success: boolean; error: string }>(`/datasources/${id}/test-connection`, { method: 'POST' }),
  importSchema: (id: string, useLLM = false) =>
    request<{ success: boolean; table_count: number; tables: any[] }>(
      `/datasources/${id}/import-schema?use_llm=${useLLM}`,
      { method: 'POST' },
    ),
}

// Schema
export const schemaApi = {
  list: (projectId: string) =>
    request<{ datasources: DatasourceSchema[] }>(`/schema?project_id=${projectId}`),
  getTable: (datasourceId: string, tableName: string) =>
    request<SchemaTable>(`/schema/table/${datasourceId}/${tableName}`),
}

// 会话
export const sessionsApi = {
  list: (projectId: string) =>
    request<{ sessions: Session[] }>(`/sessions?project_id=${projectId}`),
  get: (id: string) => request<Session>(`/sessions/${id}`),
  create: (projectId: string, title = '新对话') =>
    request<Session>('/sessions', { method: 'POST', body: JSON.stringify({ project_id: projectId, title }) }),
  update: (id: string, title: string) =>
    request<Session>(`/sessions/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
  delete: (id: string) =>
    request<{ success: boolean }>(`/sessions/${id}`, { method: 'DELETE' }),
  messages: (id: string) =>
    request<{ messages: ChatMessage[] }>(`/sessions/${id}/messages`),
}

// 聊天
export const chatApi = {
  send: (sessionId: string, message: string) =>
    request<{ session_id: string; status: string }>('/chat', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, message }),
    }),
}
```

- [ ] **Step 3: SSE 工具**

```ts
import type { SSEEvent, SSEEventType } from './types'

type EventHandler = (event: SSEEvent) => void

export class SSEConnection {
  private es: EventSource | null = null
  private handlers: Map<SSEEventType, EventHandler[]> = new Map()
  private url: string

  constructor(sessionId: string) {
    this.url = `/api/chat/stream/${sessionId}`
  }

  connect() {
    if (this.es) return
    this.es = new EventSource(this.url)
    this.es.onmessage = (e) => {
      // 默认消息类型
      this.emit('start', JSON.parse(e.data))
    }
    // 监听所有自定义事件
    const eventTypes: SSEEventType[] = [
      'start', 'intent_analysis', 'intent_probe', 'sql_generated',
      'sql_executing', 'sql_executed', 'reflection', 'clarification_needed',
      'final_result', 'error', 'done',
    ]
    eventTypes.forEach(type => {
      this.es!.addEventListener(type, (e: any) => {
        let data: any = {}
        try {
          data = JSON.parse(e.data)
        } catch {}
        this.emit(type, { type, data })
      })
    })
    this.es.onerror = () => {
      // 连接失败自动重连是 EventSource 内置的
    }
  }

  disconnect() {
    if (this.es) {
      this.es.close()
      this.es = null
    }
  }

  on(type: SSEEventType, handler: EventHandler) {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, [])
    }
    this.handlers.get(type)!.push(handler)
    return () => this.off(type, handler)
  }

  off(type: SSEEventType, handler: EventHandler) {
    const list = this.handlers.get(type)
    if (list) {
      const idx = list.indexOf(handler)
      if (idx >= 0) list.splice(idx, 1)
    }
  }

  private emit(type: SSEEventType, event: SSEEvent) {
    const handlers = this.handlers.get(type)
    if (handlers) {
      handlers.forEach(h => h(event))
    }
  }
}
```

- [ ] **Step 4: 工具函数**

```ts
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatTime(ms: number): string {
  if (ms < 1000) return `${ms.toFixed(0)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

export function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function copyToClipboard(text: string): Promise<void> {
  return navigator.clipboard.writeText(text)
}
```

- [ ] **Step 5: useSSE hook**

```ts
import { useEffect, useRef, useState } from 'react'
import { SSEConnection } from '@/lib/sse'
import type { SSEEventType, SSEEvent } from '@/lib/types'

export function useSSE(sessionId: string | null) {
  const connRef = useRef<SSEConnection | null>(null)
  const [events, setEvents] = useState<SSEEvent[]>([])
  const [isConnected, setIsConnected] = useState(false)

  useEffect(() => {
    if (!sessionId) return

    const conn = new SSEConnection(sessionId)
    connRef.current = conn

    const allTypes: SSEEventType[] = [
      'start', 'intent_analysis', 'intent_probe', 'sql_generated',
      'sql_executing', 'sql_executed', 'reflection', 'clarification_needed',
      'final_result', 'error', 'done',
    ]

    allTypes.forEach(type => {
      conn.on(type, (event) => {
        setEvents(prev => [...prev, event])
        if (type === 'start') setIsConnected(true)
        if (type === 'done' || type === 'error') setIsConnected(false)
      })
    })

    conn.connect()

    return () => {
      conn.disconnect()
      connRef.current = null
    }
  }, [sessionId])

  const clearEvents = () => setEvents([])

  return { events, isConnected, clearEvents }
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/ frontend/src/hooks/
git commit -m "feat: frontend types, API client, and SSE utilities"
```

---

## Task 3: 布局组件 + 项目上下文

**Files:**
- Create: `frontend/src/components/layout/AppLayout.tsx`
- Create: `frontend/src/components/layout/Header.tsx`
- Create: `frontend/src/components/layout/Sidebar.tsx`
- Create: `frontend/src/context/ProjectContext.tsx`
- Create: `frontend/src/hooks/useProjects.ts`

- [ ] **Step 1: 项目上下文**

```tsx
import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { projectsApi, sessionsApi } from '@/lib/api'
import type { Project, Session } from '@/lib/types'

interface ProjectContextType {
  currentProject: Project | null
  projects: Project[]
  sessions: Session[]
  loading: boolean
  setCurrentProject: (p: Project) => void
  refreshProjects: () => Promise<void>
  refreshSessions: () => Promise<void>
  createSession: () => Promise<Session | null>
}

const ProjectContext = createContext<ProjectContextType | null>(null)

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([])
  const [currentProject, setCurrentProject] = useState<Project | null>(null)
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)

  const refreshProjects = async () => {
    try {
      const res = await projectsApi.list()
      setProjects(res.projects)
      if (!currentProject && res.projects.length > 0) {
        setCurrentProject(res.projects[0])
      }
    } catch (e) {
      console.error('Failed to load projects:', e)
    } finally {
      setLoading(false)
    }
  }

  const refreshSessions = async () => {
    if (!currentProject) return
    try {
      const res = await sessionsApi.list(currentProject.id)
      setSessions(res.sessions)
    } catch (e) {
      console.error('Failed to load sessions:', e)
    }
  }

  const createSession = async (): Promise<Session | null> => {
    if (!currentProject) return null
    try {
      const session = await sessionsApi.create(currentProject.id)
      await refreshSessions()
      return session
    } catch (e) {
      console.error('Failed to create session:', e)
      return null
    }
  }

  useEffect(() => {
    refreshProjects()
  }, [])

  useEffect(() => {
    if (currentProject) {
      refreshSessions()
    }
  }, [currentProject?.id])

  return (
    <ProjectContext.Provider value={{
      currentProject, projects, sessions, loading,
      setCurrentProject, refreshProjects, refreshSessions, createSession,
    }}>
      {children}
    </ProjectContext.Provider>
  )
}

export function useProject() {
  const ctx = useContext(ProjectContext)
  if (!ctx) throw new Error('useProject must be used within ProjectProvider')
  return ctx
}
```

- [ ] **Step 2: Header 组件**

```tsx
import { Database, Settings } from 'lucide-react'
import { useProject } from '@/context/ProjectContext'

export default function Header() {
  const { currentProject } = useProject()

  return (
    <header className="h-14 border-b border-gray-200 bg-white px-4 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <Database className="w-6 h-6 text-blue-600" />
        <h1 className="font-semibold text-gray-800">NL2SQL Agent</h1>
        {currentProject && (
          <span className="text-sm text-gray-500 ml-2">/ {currentProject.name}</span>
        )}
      </div>
      <button className="p-2 hover:bg-gray-100 rounded-md transition-colors">
        <Settings className="w-5 h-5 text-gray-600" />
      </button>
    </header>
  )
}
```

- [ ] **Step 3: Sidebar 组件**

```tsx
import { Plus, MessageSquare, Database } from 'lucide-react'
import { useProject } from '@/context/ProjectContext'
import { formatDate } from '@/lib/utils'
import SchemaPanel from '@/components/schema/SchemaPanel'

interface SidebarProps {
  currentSessionId: string | null
  onSelectSession: (id: string) => void
  onNewSession: () => void
}

export default function Sidebar({ currentSessionId, onSelectSession, onNewSession }: SidebarProps) {
  const { sessions, createSession } = useProject()

  const handleNewSession = async () => {
    const session = await createSession()
    if (session) {
      onSelectSession(session.id)
      onNewSession()
    }
  }

  return (
    <aside className="w-72 border-r border-gray-200 bg-gray-50 flex flex-col h-full">
      {/* 新建对话按钮 */}
      <div className="p-3">
        <button
          onClick={handleNewSession}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium text-sm"
        >
          <Plus className="w-4 h-4" />
          新建对话
        </button>
      </div>

      {/* 会话列表 */}
      <div className="flex-1 overflow-y-auto px-2 pb-4">
        <div className="text-xs font-medium text-gray-500 uppercase px-2 py-2">
          历史会话
        </div>
        {sessions.length === 0 ? (
          <div className="text-sm text-gray-400 px-2 py-4 text-center">
            暂无会话
          </div>
        ) : (
          <div className="space-y-1">
            {sessions.map(session => (
              <button
                key={session.id}
                onClick={() => onSelectSession(session.id)}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                  currentSessionId === session.id
                    ? 'bg-blue-100 text-blue-800'
                    : 'hover:bg-gray-200 text-gray-700'
                }`}
              >
                <div className="flex items-center gap-2">
                  <MessageSquare className="w-4 h-4 flex-shrink-0" />
                  <span className="truncate">{session.title}</span>
                </div>
                <div className="text-xs text-gray-400 mt-1 ml-6">
                  {formatDate(session.updated_at)}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Schema 面板 */}
      <div className="border-t border-gray-200">
        <SchemaPanel />
      </div>
    </aside>
  )
}
```

- [ ] **Step 4: AppLayout 组件**

```tsx
import { ReactNode } from 'react'
import Header from './Header'
import Sidebar from './Sidebar'

interface AppLayoutProps {
  children: ReactNode
  currentSessionId: string | null
  onSelectSession: (id: string) => void
  onNewSession: () => void
}

export default function AppLayout({ children, currentSessionId, onSelectSession, onNewSession }: AppLayoutProps) {
  return (
    <div className="h-full flex flex-col bg-white">
      <Header />
      <div className="flex-1 flex overflow-hidden">
        <Sidebar
          currentSessionId={currentSessionId}
          onSelectSession={onSelectSession}
          onNewSession={onNewSession}
        />
        <main className="flex-1 overflow-hidden">
          {children}
        </main>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: 更新 App.tsx 和 ChatPage**

`App.tsx`:
```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import ChatPage from './pages/ChatPage'
import { ProjectProvider } from './context/ProjectContext'

function App() {
  return (
    <ProjectProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<ChatPage />} />
        </Routes>
      </BrowserRouter>
    </ProjectProvider>
  )
}

export default App
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/layout/ frontend/src/context/ frontend/src/hooks/
git commit -m "feat: app layout and project context"
```

---

## Task 4: 聊天组件（核心）

**Files:**
- Create: `frontend/src/hooks/useChat.ts`
- Create: `frontend/src/components/chat/ChatPanel.tsx`
- Create: `frontend/src/components/chat/ChatInput.tsx`
- Create: `frontend/src/components/chat/MessageList.tsx`
- Create: `frontend/src/components/chat/ChatMessage.tsx`
- Create: `frontend/src/components/chat/ResultTable.tsx`
- Create: `frontend/src/components/chat/SqlDisplay.tsx`
- Create: `frontend/src/components/chat/ThinkingIndicator.tsx`

- [ ] **Step 1: useChat hook**

```ts
import { useState, useCallback, useEffect, useRef } from 'react'
import { chatApi, sessionsApi } from '@/lib/api'
import { useSSE } from './useSSE'
import type { ChatMessage, QueryResult } from '@/lib/types'

export function useChat(projectId: string | null, sessionId: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const { events, isConnected, clearEvents } = useSSE(sessionId)
  const loadedRef = useRef(false)

  // 加载历史消息
  useEffect(() => {
    if (!sessionId || loadedRef.current) return
    loadedRef.current = true
    ;(async () => {
      try {
        const res = await sessionsApi.messages(sessionId)
        setMessages(res.messages)
      } catch (e) {
        console.error('Failed to load messages:', e)
      }
    })()
  }, [sessionId])

  // 重置加载标记
  useEffect(() => {
    loadedRef.current = false
  }, [sessionId])

  // 处理 SSE 事件，更新消息
  useEffect(() => {
    if (!sessionId || events.length === 0) return

    const lastEvent = events[events.length - 1]

    if (lastEvent.type === 'final_result') {
      const { answer, sql, result } = lastEvent.data
      setMessages(prev => [
        ...prev,
        {
          id: `assistant-${Date.now()}`,
          session_id: sessionId,
          role: 'assistant',
          content: answer,
          sql_text: sql,
          result: result as QueryResult,
          created_at: new Date().toISOString(),
        },
      ])
      setIsLoading(false)
    }
  }, [events, sessionId])

  const sendMessage = useCallback(async (content: string) => {
    if (!sessionId || !content.trim() || isLoading) return

    // 添加用户消息
    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      session_id: sessionId,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, userMsg])
    setIsLoading(true)
    clearEvents()

    try {
      await chatApi.send(sessionId, content)
    } catch (e: any) {
      setMessages(prev => [...prev, {
        id: `error-${Date.now()}`,
        session_id: sessionId,
        role: 'assistant',
        content: `发送失败: ${e.message}`,
        created_at: new Date().toISOString(),
      }])
      setIsLoading(false)
    }
  }, [sessionId, isLoading, clearEvents])

  return {
    messages,
    isLoading,
    isConnected,
    events,
    sendMessage,
  }
}
```

- [ ] **Step 2: ChatInput 组件**

```tsx
import { useState, KeyboardEvent } from 'react'
import { Send } from 'lucide-react'

interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
  placeholder?: string
}

export default function ChatInput({ onSend, disabled, placeholder = '输入你的问题...' }: ChatInputProps) {
  const [value, setValue] = useState('')

  const handleSend = () => {
    if (!value.trim() || disabled) return
    onSend(value.trim())
    setValue('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="border-t border-gray-200 p-4 bg-white">
      <div className="max-w-4xl mx-auto">
        <div className="relative flex items-end gap-2 bg-gray-50 border border-gray-200 rounded-xl p-2 focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100 transition-all">
          <textarea
            value={value}
            onChange={e => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled}
            rows={1}
            className="flex-1 bg-transparent resize-none outline-none px-3 py-2 text-sm max-h-32 min-h-[40px]"
            style={{ height: 'auto' }}
          />
          <button
            onClick={handleSend}
            disabled={disabled || !value.trim()}
            className="p-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-2 text-center">
          按 Enter 发送，Shift + Enter 换行
        </p>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: SqlDisplay 组件**

```tsx
import { useState } from 'react'
import { Copy, Check, ChevronDown, ChevronUp } from 'lucide-react'
import { copyToClipboard } from '@/lib/utils'

interface SqlDisplayProps {
  sql: string
}

export default function SqlDisplay({ sql }: SqlDisplayProps) {
  const [copied, setCopied] = useState(false)
  const [expanded, setExpanded] = useState(true)

  const handleCopy = async () => {
    await copyToClipboard(sql)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="bg-gray-900 rounded-lg overflow-hidden mt-3">
      <div className="flex items-center justify-between px-3 py-2 bg-gray-800 text-gray-400 text-xs">
        <div className="flex items-center gap-2">
          <span className="font-medium">SQL</span>
          <button
            onClick={() => setExpanded(!expanded)}
            className="hover:text-white transition-colors"
          >
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 hover:text-white transition-colors"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      {expanded && (
        <pre className="p-3 text-sm text-gray-100 overflow-x-auto font-mono leading-relaxed">
          <code>{sql}</code>
        </pre>
      )}
    </div>
  )
}
```

- [ ] **Step 4: ResultTable 组件**

```tsx
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table'

interface ResultTableProps {
  columns: string[]
  rows: any[][]
  truncated?: boolean
}

export default function ResultTable({ columns, rows, truncated }: ResultTableProps) {
  const tableColumns = columns.map((col, i) => ({
    accessorKey: String(i),
    header: col,
    cell: (info: any) => String(info.getValue() ?? ''),
  }))

  const table = useReactTable({
    data: rows.map(r => Object.fromEntries(r.map((v, i) => [String(i), v]))),
    columns: tableColumns,
    getCoreRowModel: getCoreRowModel(),
  })

  return (
    <div className="mt-3 rounded-lg border border-gray-200 overflow-hidden">
      <div className="overflow-x-auto max-h-80">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 sticky top-0">
            {table.getHeaderGroups().map(headerGroup => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map(header => (
                  <th
                    key={header.id}
                    className="px-3 py-2 text-left font-medium text-gray-700 border-b border-gray-200 whitespace-nowrap"
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map(row => (
              <tr key={row.id} className="hover:bg-gray-50">
                {row.getVisibleCells().map(cell => (
                  <td
                    key={cell.id}
                    className="px-3 py-2 border-b border-gray-100 text-gray-600 whitespace-nowrap"
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {truncated && (
        <div className="px-3 py-1.5 bg-gray-50 text-xs text-gray-500 border-t border-gray-200">
          ⚠️ 结果已被截断，只显示前 {rows.length} 行
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: ThinkingIndicator 组件**

```tsx
import { Brain, Database, Search, Sparkles } from 'lucide-react'
import type { SSEEvent } from '@/lib/types'

interface ThinkingIndicatorProps {
  events: SSEEvent[]
}

const stepIcons: Record<string, any> = {
  intent_analysis: Brain,
  intent_probe: Search,
  sql_generated: Sparkles,
  sql_executing: Database,
  sql_executed: Database,
  reflection: Brain,
}

const stepLabels: Record<string, string> = {
  intent_analysis: '分析意图',
  intent_probe: '探查数据',
  sql_generated: '生成 SQL',
  sql_executing: '执行查询',
  sql_executed: '查询完成',
  reflection: '反思校验',
}

export default function ThinkingIndicator({ events }: ThinkingIndicatorProps) {
  const thinkingEvents = events.filter(e =>
    ['intent_analysis', 'intent_probe', 'sql_generated', 'sql_executing', 'sql_executed', 'reflection'].includes(e.type)
  )

  if (thinkingEvents.length === 0) {
    return (
      <div className="flex items-center gap-2 text-gray-500 text-sm">
        <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
        思考中...
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {thinkingEvents.map((event, idx) => {
        const Icon = stepIcons[event.type] || Brain
        const label = stepLabels[event.type] || event.type
        return (
          <div key={idx} className="flex items-start gap-2 text-sm text-gray-600">
            <Icon className="w-4 h-4 mt-0.5 text-blue-500 flex-shrink-0" />
            <div>
              <span className="font-medium">{label}</span>
              {event.data?.analysis && (
                <p className="text-gray-500 text-xs mt-0.5">{event.data.analysis}</p>
              )}
              {event.type === 'sql_generated' && event.data?.sql && (
                <code className="block mt-1 text-xs bg-gray-100 px-2 py-1 rounded text-gray-600 font-mono truncate max-w-md">
                  {event.data.sql.slice(0, 80)}...
                </code>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 6: ChatMessage 组件**

```tsx
import { User, Bot } from 'lucide-react'
import type { ChatMessage as ChatMessageType } from '@/lib/types'
import SqlDisplay from './SqlDisplay'
import ResultTable from './ResultTable'

interface ChatMessageProps {
  message: ChatMessageType
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
        isUser ? 'bg-blue-100 text-blue-600' : 'bg-green-100 text-green-600'
      }`}>
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>
      <div className={`max-w-3xl ${isUser ? 'text-right' : ''}`}>
        <div className={`inline-block px-4 py-3 rounded-2xl ${
          isUser
            ? 'bg-blue-600 text-white rounded-tr-md'
            : 'bg-gray-100 text-gray-800 rounded-tl-md'
        }`}>
          <div className="whitespace-pre-wrap text-sm leading-relaxed">
            {message.content}
          </div>
        </div>
        {message.sql_text && !isUser && (
          <SqlDisplay sql={message.sql_text} />
        )}
        {message.result && message.result.success && message.result.rows.length > 0 && !isUser && (
          <ResultTable
            columns={message.result.columns}
            rows={message.result.rows}
            truncated={message.result.truncated}
          />
        )}
        {message.result && !message.result.success && !isUser && (
          <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            查询失败: {message.result.error}
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 7: MessageList 组件**

```tsx
import { useEffect, useRef } from 'react'
import ChatMessage from './ChatMessage'
import ThinkingIndicator from './ThinkingIndicator'
import type { ChatMessage as ChatMessageType, SSEEvent } from '@/lib/types'

interface MessageListProps {
  messages: ChatMessageType[]
  events: SSEEvent[]
  isLoading: boolean
}

export default function MessageList({ messages, events, isLoading }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, events])

  if (messages.length === 0 && !isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="text-4xl mb-3">🔍</div>
          <h2 className="text-lg font-semibold text-gray-700 mb-1">开始你的数据分析</h2>
          <p className="text-gray-500 text-sm">输入你的问题，我会帮你生成 SQL 并查询数据</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="max-w-4xl mx-auto space-y-6">
        {messages.map(msg => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
        {isLoading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-green-100 text-green-600 flex items-center justify-center flex-shrink-0">
              <Bot className="w-4 h-4" />
            </div>
            <div className="bg-gray-100 px-4 py-3 rounded-2xl rounded-tl-md">
              <ThinkingIndicator events={events} />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
```

需要在 MessageList 顶部加 Bot 图标 import。

- [ ] **Step 8: ChatPanel 组件**

```tsx
import ChatInput from './ChatInput'
import MessageList from './MessageList'
import { useChat } from '@/hooks/useChat'

interface ChatPanelProps {
  projectId: string | null
  sessionId: string | null
}

export default function ChatPanel({ projectId, sessionId }: ChatPanelProps) {
  const { messages, isLoading, events, sendMessage } = useChat(projectId, sessionId)

  return (
    <div className="h-full flex flex-col bg-white">
      <MessageList messages={messages} events={events} isLoading={isLoading} />
      <ChatInput
        onSend={sendMessage}
        disabled={!sessionId || isLoading}
        placeholder={sessionId ? '输入你的问题...' : '请先选择或创建一个会话'}
      />
    </div>
  )
}
```

- [ ] **Step 9: 更新 ChatPage**

```tsx
import { useState, useEffect } from 'react'
import AppLayout from '@/components/layout/AppLayout'
import ChatPanel from '@/components/chat/ChatPanel'
import { useProject } from '@/context/ProjectContext'

export default function ChatPage() {
  const { currentProject, sessions, createSession } = useProject()
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)

  // 自动选择第一个会话
  useEffect(() => {
    if (sessions.length > 0 && !currentSessionId) {
      setCurrentSessionId(sessions[0].id)
    }
  }, [sessions, currentSessionId])

  const handleNewSession = async () => {
    // 新建后选中新会话
    const session = await createSession()
    if (session) {
      setCurrentSessionId(session.id)
    }
  }

  return (
    <AppLayout
      currentSessionId={currentSessionId}
      onSelectSession={setCurrentSessionId}
      onNewSession={handleNewSession}
    >
      <ChatPanel
        projectId={currentProject?.id || null}
        sessionId={currentSessionId}
      />
    </AppLayout>
  )
}
```

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/chat/ frontend/src/hooks/useChat.ts
git commit -m "feat: chat components with SSE streaming"
```

---

## Task 5: Schema 面板组件

**Files:**
- Create: `frontend/src/components/schema/SchemaPanel.tsx`
- Create: `frontend/src/components/schema/TableList.tsx`
- Create: `frontend/src/components/schema/TableDetail.tsx`

- [ ] **Step 1: SchemaPanel 组件**

```tsx
import { useState, useEffect } from 'react'
import { ChevronDown, ChevronRight, Database2 } from 'lucide-react'
import { schemaApi } from '@/lib/api'
import { useProject } from '@/context/ProjectContext'
import type { DatasourceSchema } from '@/lib/types'

export default function SchemaPanel() {
  const { currentProject } = useProject()
  const [schemas, setSchemas] = useState<DatasourceSchema[]>([])
  const [expanded, setExpanded] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!currentProject) return
    setLoading(true)
    schemaApi.list(currentProject.id)
      .then(res => setSchemas(res.datasources))
      .catch(e => console.error('Failed to load schema:', e))
      .finally(() => setLoading(false))
  }, [currentProject?.id])

  return (
    <div className="p-2">
      <button
        onClick={() => setExpanded(expanded === '__all__' ? null : '__all__')}
        className="w-full flex items-center gap-2 px-2 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200 rounded-md"
      >
        {expanded === '__all__' ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        <Database2 className="w-4 h-4" />
        Schema 浏览
      </button>

      {expanded === '__all__' && (
        <div className="mt-1 space-y-1 max-h-64 overflow-y-auto">
          {loading ? (
            <div className="text-xs text-gray-400 px-2 py-2">加载中...</div>
          ) : schemas.length === 0 ? (
            <div className="text-xs text-gray-400 px-2 py-2">暂无数据源</div>
          ) : (
            schemas.map(ds => (
              <div key={ds.datasource_id} className="ml-2">
                <div className="text-xs font-medium text-gray-500 px-2 py-1">
                  {ds.datasource_name}
                </div>
                <div className="space-y-0.5">
                  {ds.tables.map(table => (
                    <div
                      key={table.name}
                      className="text-xs text-gray-600 px-3 py-1 hover:bg-gray-200 rounded cursor-pointer truncate"
                      title={table.description}
                    >
                      {table.name}
                      <span className="text-gray-400 ml-1">({table.column_count})</span>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/schema/
git commit -m "feat: schema browser panel"
```

---

## Task 6: 数据源管理弹窗

**Files:**
- Create: `frontend/src/components/datasource/DatasourceModal.tsx`

这个组件要支持：
- 填写数据库连接信息
- 测试连接
- 触发 Schema 导入
- 显示导入进度

V1 先做基本功能，组件代码约 200-300 行。

- [ ] **Step 1: 实现 DatasourceModal**

（代码略，核心功能：表单收集连接信息 → 测试连接 → 保存数据源 → 导入 Schema）

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/datasource/
git commit -m "feat: datasource management modal"
```

---

## Task 7: 项目切换弹窗

**Files:**
- Create: `frontend/src/components/project/ProjectSwitcher.tsx`
- Create: `frontend/src/components/project/ProjectModal.tsx`

- [ ] **Step 1: 实现项目切换和创建弹窗**

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/project/
git commit -m "feat: project switcher and modal"
```

---

## Task 8: 端到端联调 + 样式优化

- [ ] **Step 1: 启动前后端联调**
  - 后端: `uvicorn app.main:app --reload`
  - 前端: `npm run dev`
  - 创建测试项目和 SQLite 数据源
  - 验证完整流程：提问 → 生成 SQL → 执行 → 展示结果

- [ ] **Step 2: 样式细节优化**
  - 响应式布局
  - 深色模式支持（可选）
  - 动画和过渡效果

- [ ] **Step 3: 编写前端 README**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: final polish and e2e testing"
```

---

## Phase 3 完成清单

- [x] Task 1: React + Vite + Tailwind 项目初始化
- [x] Task 2: 类型定义 + API 客户端 + SSE 工具
- [x] Task 3: 布局组件 + 项目上下文
- [x] Task 4: 聊天组件（核心）
- [x] Task 5: Schema 面板组件
- [x] Task 6: 数据源管理弹窗
- [x] Task 7: 项目切换弹窗
- [x] Task 8: 端到端联调 + 样式优化
