/**
 * 饼图组件
 */
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import type { ChartSpec } from '../../lib/types'
import { rowsToObjects, getChartColor } from './chartUtils'

interface PieChartViewProps {
  chart: ChartSpec
  columns: string[]
  rows: unknown[][]
}

export function PieChartView({ chart, columns, rows }: PieChartViewProps) {
  const data = rowsToObjects(columns, rows, chart.limit)

  // 解析类别字段和数值字段
  const categoryField =
    chart.category_field && columns.includes(chart.category_field)
      ? chart.category_field
      : columns[0] ?? ''

  const valueField =
    chart.value_field && columns.includes(chart.value_field)
      ? chart.value_field
      : columns[1] ?? ''

  if (!categoryField || !valueField || data.length === 0) {
    return null
  }

  const total = data.reduce((sum, item) => {
    const val = Number(item[valueField])
    return sum + (isNaN(val) ? 0 : val)
  }, 0)

  const renderLabel = (props: {
    name: string
    percent: number
    cx: number
    cy: number
    midAngle: number
    outerRadius: number
  }) => {
    const { name, percent, cx, cy, midAngle, outerRadius } = props
    if (percent < 0.05) return null
    const RADIAN = Math.PI / 180
    const radius = outerRadius + 10
    const x = cx + radius * Math.cos(-midAngle * RADIAN)
    const y = cy + radius * Math.sin(-midAngle * RADIAN)
    return (
      <text
        x={x}
        y={y}
        fill="#64748b"
        fontSize={10}
        textAnchor={x > cx ? 'start' : 'end'}
        dominantBaseline="central"
      >
        {`${name} ${(percent * 100).toFixed(1)}%`}
      </text>
    )
  }

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
          <Pie
            data={data}
            dataKey={valueField}
            nameKey={categoryField}
            cx="40%"
            cy="50%"
            innerRadius={50}
            outerRadius={80}
            paddingAngle={1}
            stroke="#ffffff"
            strokeWidth={1}
            label={renderLabel}
            labelLine={{ stroke: '#cbd5e1', strokeWidth: 1 }}
          >
            {data.map((_, index) => (
              <Cell key={index} fill={getChartColor(index)} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value: unknown) => {
              const num = Number(value)
              const pct = total > 0 ? ((num / total) * 100).toFixed(1) : '0.0'
              return [
                `${isNaN(num) ? value : num.toLocaleString()} (${pct}%)`,
                valueField,
              ]
            }}
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
          <Legend
            layout="vertical"
            align="right"
            verticalAlign="middle"
            iconType="circle"
            iconSize={6}
            wrapperStyle={{ fontSize: '11px', color: '#64748b' }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
