/**
 * 全局类型定义
 */

// ---------- 项目 ----------
export interface Project {
  id: string
  name: string
  description: string
  created_at: string
  updated_at: string
}

// ---------- 会话 ----------
export interface Session {
  id: string
  project_id: string
  title: string
  created_at: string
  updated_at: string
}

// ---------- 消息 ----------
export interface QueryResult {
  columns: string[]
  rows: unknown[][]
  row_count: number
  duration_ms?: number
  truncated?: boolean
}

export interface Message {
  id: string
  session_id: string
  role: 'user' | 'assistant'
  content: string
  sql_text?: string | null
  result?: QueryResult | null
  viz?: VizSpec | null
  created_at?: string
}

// ---------- Schema ----------
export interface SchemaTable {
  name: string
  description: string
  column_count: number
}

export interface DatasourceSchemaOverview {
  datasource_id: string
  datasource_name: string
  datasource_type: string
  tables?: SchemaTable[]
  note?: string
}

export interface ColumnDetail {
  name: string
  type: string
  description: string
  is_primary_key: boolean
  is_foreign_key: boolean
  semantic_type: string | null
  enum_values: string[]
}

export interface TableDetail {
  name: string
  description: string
  columns: ColumnDetail[]
  examples: Record<string, unknown>[]
}

// ---------- SSE 事件 ----------
export type SseEventType =
  | 'start'
  | 'intent_analysis'
  | 'intent_probe'
  | 'clarification_needed'
  | 'sql_generated'
  | 'sql_executing'
  | 'sql_executed'
  | 'sql_execution_error'
  | 'sql_execution_failed'
  | 'reflection'
  | 'final_result'
  | 'error'
  | 'done'
  | 'chat_done'
  | 'heartbeat'
  | 'viz_ready'

export interface SseEvent {
  event: SseEventType
  data: Record<string, unknown>
}

export interface FinalResultData {
  answer: string
  sql: string
  result?: QueryResult
  viz?: VizSpec
}

// ---------- 思考阶段（用于 UI 进度展示） ----------
export type ThinkingStage =
  | 'intent_analysis'
  | 'intent_probe'
  | 'clarification_needed'
  | 'sql_generated'
  | 'sql_executing'
  | 'sql_executed'
  | 'reflection'
  | 'done'

export const THINKING_STAGES: { key: ThinkingStage; label: string }[] = [
  { key: 'intent_analysis', label: '分析意图' },
  { key: 'intent_probe', label: '探查数据' },
  { key: 'clarification_needed', label: '需要澄清' },
  { key: 'sql_generated', label: '生成 SQL' },
  { key: 'sql_executing', label: '执行查询' },
  { key: 'sql_executed', label: '查询完成' },
  { key: 'reflection', label: '反思优化' },
  { key: 'done', label: '完成' },
]

// ---------- 可视化图表 ----------
export type ChartType = 'line' | 'bar' | 'pie' | 'area' | 'metric' | 'table'

export interface ChartSpec {
  type: ChartType
  title: string
  description?: string
  x_field?: string
  y_field?: string
  y_fields?: string[]
  category_field?: string
  value_field?: string
  sort?: 'asc' | 'desc' | null
  limit?: number
  stacked?: boolean
  config?: Record<string, unknown>
}

export interface VizSpec {
  charts: ChartSpec[]
}

// 分页结果
export interface PaginatedResult {
  columns: string[]
  rows: unknown[][]
  page: number
  page_size: number
  total: number
  has_more: boolean
}
