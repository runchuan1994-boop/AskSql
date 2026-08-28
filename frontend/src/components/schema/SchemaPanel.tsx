/**
 * Schema 浏览面板
 * 玻璃质感风格
 *
 * 展示项目的数据源、表和字段信息
 */
import { useEffect, useState } from 'react'
import {
  ChevronRight,
  ChevronDown,
  Database,
  Table2,
  Columns,
  Key,
  Loader2,
  Lightbulb,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react'
import { getSchemaOverview, getTableDetail, startProfiling, getProfilingStatus } from '../../lib/api'
import type {
  DatasourceSchemaOverview,
  TableDetail,
  ColumnDetail,
  ProfilingStatus,
} from '../../lib/types'
import { clsx } from '../../lib/utils'
import { useTranslation } from '../../i18n'
import { MemoryPanel } from './MemoryPanel'

interface SchemaPanelProps {
  projectId: string
}

export function SchemaPanel({ projectId }: SchemaPanelProps) {
  const { t } = useTranslation()
  const [schemas, setSchemas] = useState<DatasourceSchemaOverview[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedTables, setExpandedTables] = useState<Record<string, boolean>>({})
  const [tableDetails, setTableDetails] = useState<Record<string, TableDetail>>({})
  const [loadingTable, setLoadingTable] = useState<string | null>(null)

  useEffect(() => {
    let mounted = true
    async function load() {
      setLoading(true)
      try {
        const data = await getSchemaOverview(projectId)
        if (mounted) setSchemas(data)
      } finally {
        if (mounted) setLoading(false)
      }
    }
    load()
    return () => {
      mounted = false
    }
  }, [projectId])

  const toggleTable = async (dsId: string, tableName: string) => {
    const key = `${dsId}:${tableName}`
    const isExpanded = expandedTables[key]

    if (!isExpanded && !tableDetails[key]) {
      setLoadingTable(key)
      try {
        const detail = await getTableDetail(dsId, tableName)
        setTableDetails((prev) => ({ ...prev, [key]: detail }))
      } catch {
        // ignore
      } finally {
        setLoadingTable(null)
      }
    }

    setExpandedTables((prev) => ({ ...prev, [key]: !isExpanded }))
  }

  // 收集所有表名（用于记忆面板的下拉选择）
  const allTableNames = schemas.flatMap((ds) =>
    ds.tables ? ds.tables.map((t) => t.name) : [],
  )

  const [activeTab, setActiveTab] = useState<'schema' | 'memory'>('schema')

  // 默认选择第一个数据源用于记忆面板
  const selectedDatasourceId = schemas[0]?.datasource_id || ''

  return (
    <div className="h-full flex flex-col">
      <div className="px-4 py-2.5 border-b border-white/30 bg-white/50 backdrop-blur flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">{t('schema.title')}</h3>
      </div>

      {/* Tab 切换 */}
      <div className="flex border-b border-white/30 bg-white/30">
        <button
          onClick={() => setActiveTab('schema')}
          className={clsx(
            'flex-1 px-3 py-2 text-xs font-medium transition-colors relative',
            activeTab === 'schema'
              ? 'text-brand-600'
              : 'text-slate-500 hover:text-slate-700',
          )}
        >
          <Table2 size={13} className="inline-block mr-1 -mt-0.5" />
          表结构
          {activeTab === 'schema' && (
            <div className="absolute bottom-0 left-2 right-2 h-0.5 bg-brand-500 rounded-t-full" />
          )}
        </button>
        <button
          onClick={() => setActiveTab('memory')}
          className={clsx(
            'flex-1 px-3 py-2 text-xs font-medium transition-colors relative',
            activeTab === 'memory'
              ? 'text-brand-600'
              : 'text-slate-500 hover:text-slate-700',
          )}
        >
          <Lightbulb size={13} className="inline-block mr-1 -mt-0.5" />
          记忆
          {activeTab === 'memory' && (
            <div className="absolute bottom-0 left-2 right-2 h-0.5 bg-brand-500 rounded-t-full" />
          )}
        </button>
      </div>

      {activeTab === 'schema' && (
        <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-4 text-center text-sm text-slate-400">{t('schema.loading')}</div>
        ) : schemas.length === 0 ? (
          <div className="p-4 text-center text-sm text-slate-400">
            {t('schema.noData')}
          </div>
        ) : (
          <div className="py-2">
            {schemas.map((ds) => (
              <div key={ds.datasource_id} className="mb-3">
                {/* 数据源 */}
                <div className="px-3 py-2 flex items-center gap-2 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  <Database size={14} className="text-brand-500" />
                  <div className="flex-1 min-w-0">
                    <div className="truncate text-slate-700">{ds.datasource_name}</div>
                    <div className="text-[10px] font-mono font-normal text-slate-400 normal-case truncate">
                      {ds.datasource_type === 'sqlite'
                        ? ds.database || ds.datasource_type
                        : `${ds.host || 'localhost'}${ds.port ? `:${ds.port}` : ''}${ds.database ? `/${ds.database}` : ''}`}
                    </div>
                  </div>
                  <span className="text-[10px] bg-brand-500/10 text-brand-600 px-2 py-0.5 rounded-xl font-medium">
                    {ds.datasource_type}
                  </span>
                </div>

                {/* 表列表 */}
                {ds.tables && ds.tables.length > 0 ? (
                  <ul className="px-1">
                    {ds.tables.map((table) => {
                      const key = `${ds.datasource_id}:${table.name}`
                      const expanded = expandedTables[key]
                      const detail = tableDetails[key]
                      const isLoadingTable = loadingTable === key

                      return (
                        <li key={key}>
                          <button
                            onClick={() => toggleTable(ds.datasource_id, table.name)}
                            className="w-full text-left px-3 py-2 flex items-center gap-2 hover:bg-white/60 text-sm text-slate-700 rounded-xl transition-all"
                          >
                            {isLoadingTable ? (
                              <Loader2 size={14} className="animate-spin text-slate-400" />
                            ) : expanded ? (
                              <ChevronDown size={14} className="text-slate-400" />
                            ) : (
                              <ChevronRight size={14} className="text-slate-400" />
                            )}
                            <Table2 size={14} className="text-brand-500" />
                            <span className="flex-1 truncate font-mono text-slate-700">
                              {table.name}
                            </span>
                            <span className="text-xs text-slate-400 bg-white/60 px-1.5 py-0.5 rounded-lg">
                              {table.column_count}
                            </span>
                          </button>

                          {/* 字段列表 */}
                          {expanded && detail && (
                            <div className="ml-6 border-l border-brand-100/60 pl-2 py-1">
                              {/* 表级元数据 */}
                              <TableMeta detail={detail} />
                              <ColumnList columns={detail.columns} />
                            </div>
                          )}
                        </li>
                      )
                    })}
                  </ul>
                ) : (
                  <div className="ml-3 text-xs text-slate-400 py-1">
                    {ds.note || t('schema.noTables')}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        </div>
      )}

      {/* 记忆 Tab */}
      {activeTab === 'memory' && (
        <div className="flex-1 overflow-hidden">
          {selectedDatasourceId ? (
            <MemoryPanel
              datasourceId={selectedDatasourceId}
              tableNames={allTableNames}
            />
          ) : (
            <div className="p-4 text-center text-xs text-slate-400">
              暂无数据源
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function TableMeta({ detail }: { detail: TableDetail }) {
  const items: string[] = []
  if (detail.row_count != null) {
    items.push(`${detail.row_count.toLocaleString()} 行`)
  }
  if (detail.aliases && detail.aliases.length > 0) {
    items.push(`别名: ${detail.aliases.join(', ')}`)
  }
  if (detail.business_domain) {
    items.push(`业务域: ${detail.business_domain}`)
  }
  if (detail.update_frequency) {
    items.push(`更新频率: ${detail.update_frequency}`)
  }
  if (detail.description) {
    items.unshift(detail.description)
  }
  if (items.length === 0) return null

  return (
    <div className="px-2 pb-1.5 mb-1 border-b border-white/40 text-[11px] text-slate-400 space-y-0.5">
      {items.map((item, i) => (
        <div key={i} className="leading-snug">{item}</div>
      ))}
    </div>
  )
}

function ColumnList({ columns }: { columns: ColumnDetail[] }) {
  return (
    <ul className="space-y-0.5">
      {columns.map((col) => (
        <li
          key={col.name}
          className="px-2 py-1 text-xs hover:bg-white/40 rounded-lg transition-colors"
        >
          <div className="flex items-start gap-1.5">
            <Columns
              size={12}
              className={clsx(
                'mt-0.5 shrink-0',
                col.is_primary_key ? 'text-amber-500' : 'text-slate-400',
              )}
            />
            <div className="flex-1 min-w-0">
              {/* 列名 + 类型 + 标记 */}
              <div className="flex items-center gap-1 flex-wrap">
                <span className="font-mono text-slate-700 truncate">{col.name}</span>
                {col.business_name && (
                  <span className="text-slate-400 text-[10px] font-normal truncate">
                    · {col.business_name}
                  </span>
                )}
                <span className="text-slate-400 font-mono text-[10px]">{col.type}</span>
                {col.is_primary_key && (
                  <Key size={10} className="text-amber-500" aria-label="主键" />
                )}
                {col.is_foreign_key && (
                  <span className="text-[10px] text-brand-500 font-medium">FK</span>
                )}
              </div>

              {/* 描述 */}
              {col.description && (
                <div className="text-slate-400 truncate">{col.description}</div>
              )}

              {/* Profiling 元数据 */}
              <ColumnProfiling col={col} />
            </div>
          </div>
        </li>
      ))}
    </ul>
  )
}

function ColumnProfiling({ col }: { col: ColumnDetail }) {
  const lines: string[] = []

  // 枚举值
  if (col.enum_values && col.enum_values.length > 0) {
    lines.push(`枚举: ${col.enum_values.slice(0, 5).join(', ')}${col.enum_values.length > 5 ? '...' : ''}`)
  }

  // Top 值（类别列）
  if (col.top_values && col.top_values.length > 0) {
    const topStr = col.top_values
      .slice(0, 3)
      .map((tv) => {
        const pct = tv.ratio != null ? `${(tv.ratio * 100).toFixed(1)}%` : ''
        return `${tv.value}${pct ? `(${pct})` : ''}`
      })
      .join(', ')
    lines.push(`Top值: ${topStr}`)
  }

  // 范围（数值/时间列）
  if (col.value_min != null && col.value_max != null && col.value_min !== '' && col.value_max !== '') {
    lines.push(`范围: ${col.value_min} ~ ${col.value_max}`)
  }

  // 非空率
  if (col.null_rate != null && col.null_rate >= 0) {
    const nonNullRate = ((1 - col.null_rate) * 100).toFixed(1)
    lines.push(`非空率: ${nonNullRate}%`)
  }

  // 去重计数
  if (col.distinct_count != null && col.distinct_count > 0) {
    lines.push(`去重: ${col.distinct_count.toLocaleString()}`)
  }

  // 计算公式
  if (col.calc_formula) {
    lines.push(`公式: ${col.calc_formula}`)
  }

  if (lines.length === 0) return null

  return (
    <div className="text-[10px] text-slate-400/80 mt-0.5 space-y-0.5 leading-tight">
      {lines.map((line, i) => (
        <div key={i} className="truncate">{line}</div>
      ))}
    </div>
  )
}
