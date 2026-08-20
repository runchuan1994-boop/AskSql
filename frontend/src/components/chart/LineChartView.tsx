/**
 * 折线图组件
 */
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
import { rowsToObjects, resolveXField, resolveYFields, getChartColor } from './chartUtils'

interface LineChartViewProps {
  chart: ChartSpec
  columns: string[]
  rows: unknown[][]
}

export function LineChartView({ chart, columns, rows }: LineChartViewProps) {
  const data = rowsToObjects(columns, rows, chart.limit)
  const xField = resolveXField(chart, columns)
  const yFields = resolveYFields(chart, columns)

  if (!xField || yFields.length === 0) {
    return null
  }

  const isMultiSeries = yFields.length > 1

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
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
