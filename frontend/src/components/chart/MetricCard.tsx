/**
 * 指标卡片组件
 * 玻璃质感风格
 */
import type { ChartSpec } from '../../lib/types'

interface MetricCardProps {
  chart: ChartSpec
  columns: string[]
  rows: unknown[][]
}

export function MetricCard({ chart, columns, rows }: MetricCardProps) {
  // 智能取值：优先 value_field，否则取最后一列的第一行
  let value: unknown = ''

  if (rows.length > 0 && columns.length > 0) {
    if (chart.value_field && columns.includes(chart.value_field)) {
      const idx = columns.indexOf(chart.value_field)
      value = rows[0][idx]
    } else {
      // 取最后一列的第一行
      const lastColIdx = columns.length - 1
      value = rows[0][lastColIdx]
    }
  }

  const displayValue =
    value === null || value === undefined
      ? '--'
      : typeof value === 'number'
        ? value.toLocaleString()
        : String(value)

  return (
    <div className="w-full h-40 rounded-2xl border border-white/60 bg-gradient-to-br from-brand-500/10 via-white/70 to-violet-500/10 backdrop-blur-xl p-6 flex flex-col justify-center shadow-glass hover:shadow-glass-lg transition-all">
      <div className="text-sm text-slate-500 font-medium">{chart.title}</div>
      <div className="text-4xl font-bold bg-gradient-to-r from-brand-600 to-violet-600 bg-clip-text text-transparent mt-2">
        {displayValue}
      </div>
      {chart.description && (
        <div className="text-xs text-slate-400 mt-2">{chart.description}</div>
      )}
    </div>
  )
}
