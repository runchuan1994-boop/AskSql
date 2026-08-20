/**
 * 图表网格容器
 * 排列多个图表
 */
import { BarChart3 } from 'lucide-react'
import type { VizSpec, QueryResult } from '../../lib/types'
import { ChartRenderer, CHART_TYPE_LABELS } from './ChartRenderer'

interface ChartGridProps {
  viz: VizSpec
  result: QueryResult
}

export function ChartGrid({ viz, result }: ChartGridProps) {
  // 过滤掉 table 类型的图表（由 ResultTable 单独展示）
  const charts = viz.charts.filter((c) => c.type !== 'table')

  if (charts.length === 0) {
    return null
  }

  const rowCount = result.rows.length
  const isLargeDataset = rowCount > 1000

  return (
    <div className="space-y-3">
      {isLargeDataset && (
        <div className="flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-700">
          <BarChart3 size={14} />
          <span>
            数据量较大（{rowCount.toLocaleString()} 行），图表仅展示部分数据，以表格为准
          </span>
        </div>
      )}
      <div
        className={
          'grid gap-4 ' +
          // 1 个：全宽；2 个：md 以上各 1/2；3+ 个：lg 以上各 1/3
          (charts.length === 1
            ? 'grid-cols-1'
            : charts.length === 2
              ? 'grid-cols-1 md:grid-cols-2'
              : 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3')
        }
      >
        {charts.map((chart, index) => (
          <div
            key={index}
            className="rounded-lg border border-gray-200 bg-white overflow-hidden shadow-sm"
          >
            <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <BarChart3 size={14} className="text-gray-400" />
                <h3 className="text-sm font-medium text-gray-700">{chart.title}</h3>
              </div>
              <span className="text-xs text-gray-400">
                {CHART_TYPE_LABELS[chart.type]}
              </span>
            </div>
            <div className="p-3">
              <ChartRenderer
                chart={chart}
                columns={result.columns}
                rows={result.rows}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
