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
  /** 澄清相关（仅 assistant 消息，处于澄清状态时有） */
  clarification?: {
    questions: string[]
    resolved?: boolean
  }
  /** 查询改写时做出的合理假设列表（减少澄清时展示） */
  query_assumptions?: string[]
}

// ---------- 数据源 ----------
export interface Datasource {
  id: string
  project_id: string
  name: string
  type: string
  host: string
  port: number | null
  database: string
  username: string
  schema_file: string
  created_at?: string
  updated_at?: string
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
  host: string
  port: number | null
  database: string
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
  | 'dispatch_started'
  | 'dispatch_result'
  | 'intent_analysis'
  | 'intent_probe'
  | 'query_rewrite'
  | 'clarification_needed'
  | 'sql_generated'
  | 'sql_executing'
  | 'sql_executed'
  | 'sql_execution_error'
  | 'sql_execution_failed'
  | 'ds_creating'
  | 'ds_created'
  | 'ds_create_failed'
  | 'ds_testing'
  | 'ds_connected'
  | 'ds_connection_failed'
  | 'ds_importing'
  | 'ds_imported'
  | 'ds_import_failed'
  | 'ds_connect_started'
  | 'schema_exploring'
  | 'schema_tool_call'
  | 'schema_tool_result'
  | 'schema_explore_done'
  | 'reflection'
  | 'final_result'
  | 'error'
  | 'done'
  | 'chat_done'
  | 'heartbeat'
  | 'viz_ready'
  | 'step_detail'

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
  | 'dispatching'
  | 'intent_analysis'
  | 'intent_probe'
  | 'query_rewrite'
  | 'clarification_needed'
  | 'sql_generated'
  | 'sql_executing'
  | 'sql_executed'
  | 'connecting_datasource'
  | 'importing_schema'
  | 'schema_exploring'
  | 'visualizing'
  | 'reflection'
  | 'done'

export const THINKING_STAGES: { key: ThinkingStage; label: string }[] = [
  { key: 'dispatching', label: '分析任务' },
  { key: 'intent_analysis', label: '分析意图' },
  { key: 'intent_probe', label: '探查数据' },
  { key: 'query_rewrite', label: '查询改写' },
  { key: 'clarification_needed', label: '需要澄清' },
  { key: 'sql_generated', label: '生成 SQL' },
  { key: 'sql_executing', label: '执行查询' },
  { key: 'sql_executed', label: '查询完成' },
  { key: 'connecting_datasource', label: '连接数据源' },
  { key: 'importing_schema', label: '导入 Schema' },
  { key: 'schema_exploring', label: '探索 Schema' },
  { key: 'visualizing', label: '生成图表' },
  { key: 'reflection', label: '反思优化' },
  { key: 'done', label: '完成' },
]

// ---------- 思考步骤（时间线展示） ----------
export type StepStatus = 'pending' | 'active' | 'completed' | 'error'

export interface ThinkingStep {
  step: string
  name: string
  status: StepStatus
  duration_ms?: number
  detail?: Record<string, unknown>
  error_message?: string
}

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

// ---------- Schema 记忆 ----------
export type MemoryType =
  | 'column_description'
  | 'table_description'
  | 'metric_definition'
  | 'term_mapping'
  | 'join_hint'

export type EntityType = 'table' | 'column' | 'metric' | 'term'

export interface SchemaMemory {
  id: string
  datasource_id: string
  memory_type: MemoryType
  entity_type: EntityType | null
  entity_name: string | null
  content: string
  raw_content: string | null
  source: string
  source_session_id: string | null
  source_message_id: string | null
  confidence: number
  access_count: number
  created_at: string
  updated_at: string
  is_active: number
}

export interface MemoryListResult {
  items: SchemaMemory[]
  total: number
  page: number
  page_size: number
  has_more: boolean
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
