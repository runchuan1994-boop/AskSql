/**
 * Schema 浏览面板
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

interface SchemaPanelProps {
  projectId: string
}

export function SchemaPanel({ projectId }: SchemaPanelProps) {
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
      <div className="px-3 py-2 border-b border-gray-200 bg-gray-50">
        <h3 className="text-sm font-semibold text-gray-700">Schema 浏览</h3>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-4 text-center text-sm text-gray-400">加载中...</div>
        ) : schemas.length === 0 ? (
          <div className="p-4 text-center text-sm text-gray-400">
            暂无数据源 Schema
          </div>
        ) : (
          <div className="py-1">
            {schemas.map((ds) => (
              <div key={ds.datasource_id} className="mb-2">
                {/* 数据源 */}
                <div className="px-3 py-1.5 flex items-center gap-2 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  <Database size={14} />
                  <div className="flex-1 min-w-0">
                    <div className="truncate">{ds.datasource_name}</div>
                    <div className="text-[10px] font-mono font-normal text-gray-400 normal-case truncate">
                      {ds.datasource_type === 'sqlite'
                        ? ds.database || ds.datasource_type
                        : `${ds.host || 'localhost'}${ds.port ? `:${ds.port}` : ''}${ds.database ? `/${ds.database}` : ''}`}
                    </div>
                  </div>
                  <span className="text-[10px] bg-gray-100 px-1.5 py-0.5 rounded font-normal">
                    {ds.datasource_type}
                  </span>
                </div>

                {/* 表列表 */}
                {ds.tables && ds.tables.length > 0 ? (
                  <ul>
                    {ds.tables.map((table) => {
                      const key = `${ds.datasource_id}:${table.name}`
                      const expanded = expandedTables[key]
                      const detail = tableDetails[key]
                      const isLoadingTable = loadingTable === key

                      return (
                        <li key={key}>
                          <button
                            onClick={() => toggleTable(ds.datasource_id, table.name)}
                            className="w-full text-left px-3 py-1.5 flex items-center gap-1.5 hover:bg-gray-50 text-sm text-gray-700"
                          >
                            {isLoadingTable ? (
                              <Loader2 size={14} className="animate-spin text-gray-400" />
                            ) : expanded ? (
                              <ChevronDown size={14} className="text-gray-400" />
                            ) : (
                              <ChevronRight size={14} className="text-gray-400" />
                            )}
                            <Table2 size={14} className="text-indigo-500" />
                            <span className="flex-1 truncate font-mono">
                              {table.name}
                            </span>
                            <span className="text-xs text-gray-400">
                              {table.column_count}
                            </span>
                          </button>

                          {/* 字段列表 */}
                          {expanded && detail && (
                            <div className="ml-6 border-l border-gray-100 pl-2 py-1">
                              <ColumnList columns={detail.columns} />
                              {detail.description && (
                                <p className="text-xs text-gray-400 mt-1 px-2">
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
                  <div className="ml-3 text-xs text-gray-400 py-1">
                    {ds.note || '暂无表'}
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
          className="flex items-start gap-1.5 px-2 py-0.5 text-xs"
        >
          <Columns
            size={12}
            className={clsx(
              'mt-0.5 shrink-0',
              col.is_primary_key ? 'text-amber-500' : 'text-gray-400',
            )}
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1">
              <span className="font-mono text-gray-700 truncate">{col.name}</span>
              <span className="text-gray-400 font-mono text-[10px]">{col.type}</span>
              {col.is_primary_key && (
                <Key size={10} className="text-amber-500" aria-label="主键" />
              )}
              {col.is_foreign_key && (
                <span className="text-[10px] text-blue-500">FK</span>
              )}
            </div>
            {col.description && (
              <div className="text-gray-400 truncate">{col.description}</div>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}
