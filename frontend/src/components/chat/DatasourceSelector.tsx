/**
 * 数据源选择器
 *
 * 在聊天输入框上方展示，用户可以选择要查询的数据源。
 */
import { useState, useRef, useEffect } from 'react'
import { Database, ChevronDown, Loader2 } from 'lucide-react'
import type { Datasource } from '../../lib/types'
import { clsx } from '../../lib/utils'

function formatConnectionInfo(ds: Datasource): string {
  if (ds.type === 'sqlite') {
    return ds.database || ds.type
  }
  const hostPart = ds.host || 'localhost'
  const portPart = ds.port ? `:${ds.port}` : ''
  const dbPart = ds.database ? `/${ds.database}` : ''
  return `${hostPart}${portPart}${dbPart}`
}

interface DatasourceSelectorProps {
  datasources: Datasource[]
  value: string | null
  onChange: (id: string) => void
  loading?: boolean
  disabled?: boolean
}

export function DatasourceSelector({
  datasources,
  value,
  onChange,
  loading = false,
  disabled = false,
}: DatasourceSelectorProps) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // 点击外部关闭
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    if (open) {
      document.addEventListener('mousedown', handleClick)
      return () => document.removeEventListener('mousedown', handleClick)
    }
  }, [open])

  const selected = datasources.find((d) => d.id === value) || null

  const displayText = loading
    ? '加载中...'
    : datasources.length === 0
      ? '暂无数据源'
      : selected
        ? selected.name
        : '选择数据源'

  const handleSelect = (id: string) => {
    onChange(id)
    setOpen(false)
  }

  return (
    <div
      ref={containerRef}
      className="relative"
    >
      <button
        type="button"
        onClick={() => !disabled && !loading && datasources.length > 0 && setOpen(!open)}
        disabled={disabled || loading || datasources.length === 0}
        className={clsx(
          'flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg border transition-colors w-full',
          disabled || loading || datasources.length === 0
            ? 'bg-gray-50 border-gray-200 text-gray-400 cursor-not-allowed'
            : 'bg-white border-gray-300 text-gray-700 hover:border-indigo-400 hover:ring-2 hover:ring-indigo-100 cursor-pointer',
        )}
      >
        {loading ? (
          <Loader2 size={14} className="animate-spin text-gray-400 shrink-0" />
        ) : (
          <Database
            size={14}
            className={clsx(
              'shrink-0',
              datasources.length === 0 ? 'text-gray-300' : 'text-indigo-500',
            )}
          />
        )}
        <span className="flex-1 text-left truncate">{displayText}</span>
        {selected && (
          <span className="text-[10px] text-gray-400 font-mono truncate max-w-[180px]">
            {formatConnectionInfo(selected)}
          </span>
        )}
        {selected && (
          <span className="text-[10px] bg-gray-100 px-1.5 py-0.5 rounded text-gray-500 font-mono shrink-0">
            {selected.type}
          </span>
        )}
        {!loading && datasources.length > 0 && (
          <ChevronDown
            size={14}
            className={clsx(
              'text-gray-400 shrink-0 transition-transform',
              open && 'rotate-180',
            )}
          />
        )}
      </button>

      {/* 下拉菜单 */}
      {open && datasources.length > 0 && (
        <div className="absolute bottom-full left-0 right-0 mb-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50 max-h-64 overflow-y-auto">
          {datasources.map((ds) => (
            <button
              key={ds.id}
              type="button"
              onClick={() => handleSelect(ds.id)}
              className={clsx(
                'w-full text-left px-3 py-2 text-sm flex items-center gap-2 hover:bg-indigo-50 transition-colors',
                ds.id === value && 'bg-indigo-50 text-indigo-700',
              )}
            >
              <Database size={14} className="text-indigo-500 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="truncate font-medium">{ds.name}</div>
                <div className="text-[11px] text-gray-400 font-mono truncate">
                  {formatConnectionInfo(ds)}
                </div>
              </div>
              <span className="text-[10px] bg-gray-100 px-1.5 py-0.5 rounded text-gray-500 font-mono shrink-0">
                {ds.type}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
