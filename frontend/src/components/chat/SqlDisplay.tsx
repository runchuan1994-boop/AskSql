/**
 * SQL 代码展示，带复制按钮
 * 玻璃质感风格 - 紫蓝渐变深色代码块
 */
import { useState } from 'react'
import { Copy, Check, Terminal } from 'lucide-react'
import { copyToClipboard } from '../../lib/utils'
import { useTranslation } from '../../i18n'

interface SqlDisplayProps {
  sql: string
  compact?: boolean
}

export function SqlDisplay({ sql, compact = false }: SqlDisplayProps) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    const ok = await copyToClipboard(sql)
    if (ok) {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="rounded-2xl overflow-hidden border border-indigo-900/30 bg-gradient-to-b from-indigo-950 to-slate-900 shadow-glass">
      <div className={`flex items-center justify-between bg-white/5 backdrop-blur ${compact ? 'px-3 py-1.5' : 'px-4 py-2'}`}>
        <div className="flex items-center gap-2">
          <Terminal size={12} className="text-indigo-400" />
          <span className="text-xs text-indigo-300/80 font-medium">{t('sql.label')}</span>
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors px-2 py-1 rounded-lg hover:bg-white/5"
          title={t('sql.copy')}
        >
          {copied ? (
            <>
              <Check size={12} className="text-emerald-400" />
              {!compact && <span className="text-emerald-400">{t('sql.copied')}</span>}
            </>
          ) : (
            <>
              <Copy size={12} />
              {!compact && t('sql.copy')}
            </>
          )}
        </button>
      </div>
      <pre className={`${compact ? 'p-3 text-xs' : 'p-4 text-sm'} text-slate-100 overflow-x-auto font-mono leading-relaxed max-h-48`}>
        <code>{sql}</code>
      </pre>
    </div>
  )
}
