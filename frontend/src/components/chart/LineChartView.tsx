/**
 * 折线图组件
 */
import { useRef } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import type { ChartSpec } from '../../lib/types'
import {
  rowsToObjects,
  resolveXField,
  resolveYFields,
  getChartColor,
  formatDateTick,
  formatNumberTick,
  smartFormatTick,
} from './chartUtils'
import { useAutoXInterval } from '../../hooks/useAutoXInterval'

interface LineChartViewProps {
  chart: ChartSpec
  columns: string[]
  rows: unknown[][]
}

export function LineChartView({ chart, columns, rows }: LineChartViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const data = rowsToObjects(columns, rows, chart.limit)
  const xField = resolveXField(chart, columns)
  const yFields = resolveYFields(chart, columns)

  // X 轴标签自适应密度
  const xLabels = data.map((d) => {
    const raw = d[xField]
    if (chart.x_format === 'date' || chart.x_format === 'month' || chart.x_format === 'datetime') {
      return formatDateTick(raw)
    }
    if (chart.x_format === 'number') {
      return formatNumberTick(raw)
    }
    return smartFormatTick(raw)
  })
  const autoX = useAutoXInterval(containerRef, xLabels, {
    fontSize: 11,
    maxRotation: 40,
    minGap: 8,
  })

  // X 轴 tick 格式化
  const formatX = (value: unknown) => {
    if (chart.x_format === 'date' || chart.x_format === 'month' || chart.x_format === 'datetime') {
      return formatDateTick(value)
    }
    if (chart.x_format === 'number') {
      return formatNumberTick(value)
    }
    // 自动识别
    return smartFormatTick(value)
  }

  // Y 轴 tick 格式化
  const formatY = (value: unknown) => {
    if (chart.y_format === 'percent') {
      return `${formatNumberTick(value)}%`
    }
    if (chart.y_format === 'currency' || chart.y_format === 'money') {
      return `¥${formatNumberTick(value)}`
    }
    if (chart.y_format === 'short') {
      return formatNumberTick(value)
    }
    return formatNumberTick(value)
  }

  if (!xField || yFields.length === 0) {
    return (
      <div className="w-full h-64 flex flex-col items-center justify-center text-gray-400 text-xs gap-1">
        <span>无法自动匹配图表字段</span>
        <span className="text-gray-300">列: {columns.join(', ')}</span>
      </div>
    )
  }

  const isMultiSeries = yFields.length > 1

  return (
    <div ref={containerRef} className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
          <XAxis
            dataKey={xField}
            tick={{ fontSize: 11, fill: '#94a3b8' }}
            tickLine={false}
            axisLine={{ stroke: '#e2e8f0' }}
            interval={autoX.interval}
            angle={autoX.angle}
            textAnchor={autoX.textAnchor}
            height={autoX.height}
            tickFormatter={formatX}
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#94a3b8' }}
            tickLine={false}
            axisLine={false}
            width={56}
            tickFormatter={formatY}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'rgba(255, 255, 255, 0.95)',
              border: '1px solid #e2e8f0',
              borderRadius: '8px',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.08)',
              fontSize: '12px',
            }}
            labelStyle={{ fontWeight: 500, color: '#334155', marginBottom: '4px' }}
            itemStyle={{ color: '#475569' }}
          />
          {isMultiSeries && (
            <Legend
              iconType="circle"
              iconSize={6}
              wrapperStyle={{ fontSize: '11px', color: '#64748b' }}
            />
          )}
          {yFields.map((field, index) => (
            <Line
              key={field}
              type="monotone"
              dataKey={field}
              stroke={getChartColor(index)}
              strokeWidth={2}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
              name={field}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
