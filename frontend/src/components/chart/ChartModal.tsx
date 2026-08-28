/**
 * 图表放大弹窗
 * 点击图表卡片后弹出大图，便于查看细节
 */
import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import type { ChartSpec, QueryResult } from '../../lib/types'
import { ChartRenderer, CHART_TYPE_LABELS } from './ChartRenderer'

interface ChartModalProps {
  chart: ChartSpec | null
  columns: string[]
  rows: unknown[][]
  onClose: () => void
}

export function ChartModal({ chart, columns, rows, onClose }: ChartModalProps) {
  const modalRef = useRef<HTMLDivElement>(null)

  // ESC 键关闭
  useEffect(() => {
    if (!chart) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    // 锁定 body 滚动
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', handleKey)
      document.body.style.overflow = prevOverflow
    }
  }, [chart, onClose])

  if (!chart) return null

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose()
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm animate-fade-in"
      onClick={handleBackdropClick}
      ref={modalRef}
    >
      <div
        className="relative w-[min(90vw,880px)] max-h-[85vh] flex flex-col
                   bg-white/90 backdrop-blur-xl border border-white/60
                   rounded-2xl shadow-glass-lg overflow-hidden animate-scale-in"
      >
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/40 bg-white/30">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-brand-500/10 to-violet-500/10 flex items-center justify-center">
              <svg
                className="w-4 h-4 text-brand-500"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M3 3v18h18" />
                <path d="M7 14l4-4 4 4 6-6" />
              </svg>
            </div>
            <div>
              <h3 className="text-base font-medium text-slate-700">{chart.title}</h3>
              <p className="text-xs text-slate-400">
                {CHART_TYPE_LABELS[chart.type]} · {rows.length} 条数据
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-xl flex items-center justify-center
                       text-slate-400 hover:text-slate-600 hover:bg-white/60
                       transition-colors"
            aria-label="关闭"
          >
            <X size={16} />
          </button>
        </div>

        {/* 图表面板 */}
        <div className="flex-1 overflow-y-auto p-6">
          <div className="w-full" style={{ height: '480px' }}>
            <ChartRenderer chart={chart} columns={columns} rows={rows} />
          </div>
        </div>
      </div>
    </div>
  )
}
