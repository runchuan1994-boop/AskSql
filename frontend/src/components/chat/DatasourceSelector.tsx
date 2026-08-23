/**
 * 数据源选择器
 * 玻璃质感风格
 *
 * 在聊天输入框上方展示，用户可以选择要查询的数据源。
 */
import { useState, useRef, useEffect } from 'react'
import { Database, ChevronDown, Loader2 } from 'lucide-react'
import type { Datasource } from '../../lib/types'
import { clsx } from '../../lib/utils'
import { useTranslation } from '../../i18n'

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
  const { t } = useTranslation()
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
    ? t('datasource.loading')
    : datasources.length === 0
      ? t('datasource.noData')
      : selected
        ? selected.name
        : t('datasource.select')

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
          'flex items-center gap-2 px-3.5 py-2 text-sm rounded-xl border transition-all w-full',
          disabled || loading || datasources.length === 0
            ? 'bg-white/30 border-white/40 text-slate-400 cursor-not-allowed'
            : 'bg-white/70 backdrop-blur border-white/60 text-slate-700 hover:border-brand-400/50 hover:ring-2 hover:ring-brand-500/10 cursor-pointer shadow-glass-sm',
        )}
      >
        {loading ? (
          <Loader2 size={14} className="animate-spin text-slate-400 shrink-0" />
        ) : (
          <Database
            size={14}
            className={clsx(
              'shrink-0',
              datasources.length === 0 ? 'text-slate-300' : 'text-brand-500',
            )}
          />
        )}
        <span className="flex-1 text-left truncate font-medium">{displayText}</span>
        {selected && (
          <span className="text-[10px] text-slate-400 font-mono truncate max-w-[180px]">
            {formatConnectionInfo(selected)}
          </span>
        )}
        {selected && (
          <span className="text-[10px] bg-brand-500/10 text-brand-600 px-2 py-0.5 rounded-xl font-medium font-mono shrink-0">
            {selected.type}
          </span>
        )}
        {!loading && datasources.length > 0 && (
          <ChevronDown
            size={14}
            className={clsx(
              'text-slate-400 shrink-0 transition-transform',
              open && 'rotate-180',
            )}
          />
        )}
      </button>

      {/* 下拉菜单 - 玻璃质感 */}
      {open && datasources.length > 0 && (
        <div className="absolute bottom-full left-0 right-0 mb-2 bg-white/80 backdrop-blur-xl border border-white/60 rounded-2xl shadow-glass-lg z-50 max-h-64 overflow-y-auto p-1">
          {datasources.map((ds) => (
            <button
              key={ds.id}
              type="button"
              onClick={() => handleSelect(ds.id)}
              className={clsx(
                'w-full text-left px-3 py-2.5 text-sm flex items-center gap-2 hover:bg-brand-500/10 transition-all rounded-xl',
                ds.id === value && 'bg-brand-500/10 text-brand-700',
              )}
            >
              <Database size={14} className="text-brand-500 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="truncate font-medium text-slate-700">{ds.name}</div>
                <div className="text-[11px] text-slate-400 font-mono truncate">
                  {formatConnectionInfo(ds)}
                </div>
              </div>
              <span className="text-[10px] bg-brand-500/10 text-brand-600 px-2 py-0.5 rounded-xl font-medium font-mono shrink-0">
                {ds.type}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
