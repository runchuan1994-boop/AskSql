/**
 * 面积图组件
 */
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import type { ChartSpec } from '../../lib/types'
import { rowsToObjects, resolveXField, resolveYFields, getChartColor } from './chartUtils'

interface AreaChartViewProps {
  chart: ChartSpec
  columns: string[]
  rows: unknown[][]
}

export function AreaChartView({ chart, columns, rows }: AreaChartViewProps) {
  const data = rowsToObjects(columns, rows, chart.limit)
  const xField = resolveXField(chart, columns)
  const yFields = resolveYFields(chart, columns)
  const stacked = chart.stacked ?? false

  if (!xField || yFields.length === 0) {
    return null
  }

  const isMultiSeries = yFields.length > 1

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <defs>
            {yFields.map((field, index) => (
              <linearGradient
                key={`gradient-${field}`}
                id={`color${index}`}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop offset="0%" stopColor={getChartColor(index)} stopOpacity={0.3} />
                <stop offset="100%" stopColor={getChartColor(index)} stopOpacity={0.02} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
          <XAxis
            dataKey={xField}
            tick={{ fontSize: 11, fill: '#94a3b8' }}
            tickLine={false}
            axisLine={{ stroke: '#e2e8f0' }}
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#94a3b8' }}
            tickLine={false}
            axisLine={false}
            width={48}
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
            <Area
              key={field}
              type="monotone"
              dataKey={field}
              stroke={getChartColor(index)}
              strokeWidth={2}
              fill={`url(#color${index})`}
              name={field}
              stackId={stacked ? 'stack' : undefined}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
