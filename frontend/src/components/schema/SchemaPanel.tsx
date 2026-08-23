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
} from 'lucide-react'
import { getSchemaOverview, getTableDetail } from '../../lib/api'
import type {
  DatasourceSchemaOverview,
  TableDetail,
  ColumnDetail,
} from '../../lib/types'
import { clsx } from '../../lib/utils'
import { useTranslation } from '../../i18n'

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

  return (
    <div className="h-full flex flex-col">
      <div className="px-4 py-2.5 border-b border-white/30 bg-white/50 backdrop-blur">
        <h3 className="text-sm font-semibold text-slate-700">{t('schema.title')}</h3>
      </div>

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
                              <ColumnList columns={detail.columns} />
                              {detail.description && (
                                <p className="text-xs text-slate-400 mt-1 px-2">
                                  {detail.description}
                                </p>
                              )}
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
    </div>
  )
}

function ColumnList({ columns }: { columns: ColumnDetail[] }) {
  return (
    <ul className="space-y-0.5">
      {columns.map((col) => (
        <li
          key={col.name}
          className="flex items-start gap-1.5 px-2 py-1 text-xs hover:bg-white/40 rounded-lg transition-colors"
        >
          <Columns
            size={12}
            className={clsx(
              'mt-0.5 shrink-0',
              col.is_primary_key ? 'text-amber-500' : 'text-slate-400',
            )}
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1 flex-wrap">
              <span className="font-mono text-slate-700 truncate">{col.name}</span>
              <span className="text-slate-400 font-mono text-[10px]">{col.type}</span>
              {col.is_primary_key && (
                <Key size={10} className="text-amber-500" aria-label="主键" />
              )}
              {col.is_foreign_key && (
                <span className="text-[10px] text-brand-500 font-medium">FK</span>
              )}
            </div>
            {col.description && (
              <div className="text-slate-400 truncate">{col.description}</div>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}
