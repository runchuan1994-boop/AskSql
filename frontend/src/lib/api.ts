/**
 * API 客户端
 */
import type {
  Project,
  Session,
  Message,
  Datasource,
  DatasourceSchemaOverview,
  TableDetail,
  PaginatedResult,
  SchemaMemory,
  MemoryType,
  EntityType,
  MemoryListResult,
  ProfilingStatus,
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
  datasourceId?: string,
): Promise<{ session_id: string; status: string }> {
  const body: Record<string, unknown> = { session_id: sessionId, message }
  if (datasourceId) {
    body.datasource_id = datasourceId
  }
  return request<{ session_id: string; status: string }>('/chat', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

// ---------- 数据源 ----------
export function listDatasources(projectId: string): Promise<Datasource[]> {
  return request<Datasource[]>(`/datasources?project_id=${encodeURIComponent(projectId)}`)
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

// ---------- Schema 探测 ----------

export function startProfiling(datasourceId: string): Promise<{ status: string; message?: string }> {
  return request<{ status: string; message?: string }>(
    `/schema/profile/${encodeURIComponent(datasourceId)}`,
    { method: 'POST' },
  )
}

export function getProfilingStatus(datasourceId: string): Promise<ProfilingStatus> {
  return request<ProfilingStatus>(
    `/schema/profile/${encodeURIComponent(datasourceId)}/status`,
  )
}

// ---------- Schema 记忆 ----------
export function listMemories(
  datasourceId: string,
  params: {
    memory_type?: MemoryType
    entity_type?: EntityType
    search?: string
    page?: number
    page_size?: number
  } = {},
): Promise<MemoryListResult> {
  const searchParams = new URLSearchParams()
  searchParams.set('datasource_id', datasourceId)
  if (params.memory_type) searchParams.set('memory_type', params.memory_type)
  if (params.entity_type) searchParams.set('entity_type', params.entity_type)
  if (params.search) searchParams.set('search', params.search)
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  return request<MemoryListResult>(`/memories?${searchParams.toString()}`)
}

export function createMemory(data: {
  datasource_id: string
  memory_type: MemoryType
  entity_type?: EntityType
  entity_name?: string
  content: string
}): Promise<SchemaMemory> {
  return request<SchemaMemory>('/memories', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateMemory(
  memoryId: string,
  data: Partial<{
    content: string
    memory_type: MemoryType
    entity_type: EntityType
    entity_name: string
    confidence: number
  }>,
): Promise<SchemaMemory> {
  return request<SchemaMemory>(`/memories/${encodeURIComponent(memoryId)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function deleteMemory(memoryId: string): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(`/memories/${encodeURIComponent(memoryId)}`, {
    method: 'DELETE',
  })
}
