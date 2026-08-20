/**
 * SQL 代码展示，带复制按钮
 */
import { useState } from 'react'
import { Copy, Check } from 'lucide-react'
import { copyToClipboard } from '../../lib/utils'

interface SqlDisplayProps {
  sql: string
}

export function SqlDisplay({ sql }: SqlDisplayProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    const ok = await copyToClipboard(sql)
    if (ok) {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="rounded-lg overflow-hidden border border-gray-200 bg-gray-900">
      <div className="flex items-center justify-between px-3 py-1.5 bg-gray-800">
        <span className="text-xs text-gray-400 font-medium">SQL</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-xs text-gray-400 hover:text-white transition-colors"
          title="复制 SQL"
        >
          {copied ? (
            <>
              <Check size={12} />
              已复制
            </>
          ) : (
            <>
              <Copy size={12} />
              复制
            </>
          )}
        </button>
      </div>
      <pre className="p-3 text-sm text-gray-100 overflow-x-auto font-mono leading-relaxed">
        <code>{sql}</code>
      </pre>
    </div>
  )
}
