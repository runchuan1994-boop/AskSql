/**
 * 指标卡片组件
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
    <div className="w-full h-40 rounded-lg border border-gray-200 bg-gradient-to-b from-indigo-50 to-white p-5 flex flex-col justify-center">
      <div className="text-sm text-gray-500 font-medium">{chart.title}</div>
      <div className="text-4xl font-bold text-indigo-600 mt-2">{displayValue}</div>
      {chart.description && (
        <div className="text-xs text-gray-400 mt-2">{chart.description}</div>
      )}
    </div>
  )
}
