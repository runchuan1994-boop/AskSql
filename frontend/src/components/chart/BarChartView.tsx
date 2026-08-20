/**
 * 柱状图组件
 */
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import type { ChartSpec } from '../../lib/types'
import { rowsToObjects, resolveXField, resolveYFields, getChartColor } from './chartUtils'

interface BarChartViewProps {
  chart: ChartSpec
  columns: string[]
  rows: unknown[][]
}

export function BarChartView({ chart, columns, rows }: BarChartViewProps) {
  const data = rowsToObjects(columns, rows, chart.limit)
  const xField = resolveXField(chart, columns)
  const yFields = resolveYFields(chart, columns)
  const stacked = chart.stacked ?? false

  if (!xField || yFields.length === 0) {
    return null
  }

  const isMultiSeries = yFields.length > 1
  const shouldRotate = data.length > 8

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
          <XAxis
            dataKey={xField}
            tick={{ fontSize: 11, fill: '#94a3b8' }}
            tickLine={false}
            axisLine={{ stroke: '#e2e8f0' }}
            angle={shouldRotate ? -30 : 0}
            textAnchor={shouldRotate ? 'end' : 'middle'}
            height={shouldRotate ? 60 : 30}
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
            <Bar
              key={field}
              dataKey={field}
              fill={getChartColor(index)}
              radius={[4, 4, 0, 0]}
              name={field}
              stackId={stacked ? 'stack' : undefined}
            >
              {!isMultiSeries &&
                data.map((_, idx) => (
                  <Cell key={idx} fill={getChartColor(idx)} />
                ))}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
