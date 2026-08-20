/**
 * API 客户端
 */
import type {
  Project,
  Session,
  Message,
  DatasourceSchemaOverview,
  TableDetail,
  PaginatedResult,
} from './types'

const BASE = '/api'

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const body = await res.json()
      msg = body.detail || body.error || msg
    } catch {
      // ignore
    }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

// ---------- 项目 ----------
export function listProjects(): Promise<Project[]> {
  return request<Project[]>('/projects')
}

export function createProject(name: string, description = ''): Promise<Project> {
  return request<Project>('/projects', {
    method: 'POST',
    body: JSON.stringify({ name, description }),
  })
}

// ---------- 会话 ----------
export function listSessions(projectId: string): Promise<Session[]> {
  return request<Session[]>(`/sessions?project_id=${encodeURIComponent(projectId)}`)
}

export function createSession(projectId: string, title?: string): Promise<Session> {
  return request<Session>('/sessions', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId, title }),
  })
}

export function getMessages(sessionId: string): Promise<Message[]> {
  return request<Message[]>(`/sessions/${encodeURIComponent(sessionId)}/messages`)
}

// ---------- 聊天 ----------
export async function sendChatMessage(
  sessionId: string,
  message: string,
): Promise<{ session_id: string; status: string }> {
  return request<{ session_id: string; status: string }>('/chat', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, message }),
  })
}

// ---------- 分页结果 ----------
export async function getResultPage(
  messageId: string,
  page: number,
  pageSize = 100,
): Promise<PaginatedResult> {
  return request<PaginatedResult>(
    `/chat/messages/${encodeURIComponent(messageId)}/result?page=${page}&page_size=${pageSize}`,
  )
}

// ---------- Schema ----------
export function getSchemaOverview(projectId: string): Promise<DatasourceSchemaOverview[]> {
  return request<DatasourceSchemaOverview[]>(
    `/schema?project_id=${encodeURIComponent(projectId)}`,
  )
}

export function getTableDetail(
  datasourceId: string,
  tableName: string,
): Promise<TableDetail> {
  return request<TableDetail>(
    `/schema/table/${encodeURIComponent(datasourceId)}/${encodeURIComponent(tableName)}`,
  )
}
