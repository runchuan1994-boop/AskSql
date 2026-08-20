/**
 * 图表渲染调度器
 * 根据 chart.type 动态选择渲染组件
 */
import type { ChartSpec } from '../../lib/types'
import { LineChartView } from './LineChartView'
import { BarChartView } from './BarChartView'
import { PieChartView } from './PieChartView'
import { AreaChartView } from './AreaChartView'
import { MetricCard } from './MetricCard'

/** 图表类型显示名称 */
export const CHART_TYPE_LABELS: Record<ChartSpec['type'], string> = {
  line: '折线图',
  bar: '柱状图',
  pie: '饼图',
  area: '面积图',
  metric: '指标卡',
  table: '数据表',
}

interface ChartRendererProps {
  chart: ChartSpec
  columns: string[]
  rows: unknown[][]
}

export function ChartRenderer({ chart, columns, rows }: ChartRendererProps) {
  // table 类型由外部 ResultTable 处理，这里不渲染
  if (chart.type === 'table') {
    return null
  }

  // 无数据显示占位
  if (!rows || rows.length === 0 || !columns || columns.length === 0) {
    return (
      <div className="w-full h-64 flex items-center justify-center text-gray-400 text-sm">
        暂无数据
      </div>
    )
  }

  try {
    switch (chart.type) {
      case 'line':
        return <LineChartView chart={chart} columns={columns} rows={rows} />
      case 'bar':
        return <BarChartView chart={chart} columns={columns} rows={rows} />
      case 'pie':
        return <PieChartView chart={chart} columns={columns} rows={rows} />
      case 'area':
        return <AreaChartView chart={chart} columns={columns} rows={rows} />
      case 'metric':
        return <MetricCard chart={chart} columns={columns} rows={rows} />
      default:
        return (
          <div className="w-full h-64 flex items-center justify-center text-gray-400 text-sm">
            不支持的图表类型
          </div>
        )
    }
  } catch {
    return (
      <div className="w-full h-64 flex items-center justify-center text-gray-400 text-sm">
        图表渲染失败
      </div>
    )
  }
}
