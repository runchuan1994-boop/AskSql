/**
 * 图表工具函数
 */
import type { ChartSpec } from '../../lib/types'

/** 8 色高级感色板 */
export const CHART_COLORS: string[] = [
  '#6366f1', // indigo-500
  '#10b981', // emerald-500
  '#f59e0b', // amber-500
  '#ef4444', // red-500
  '#8b5cf6', // violet-500
  '#06b6d4', // cyan-500
  '#ec4899', // pink-500
  '#84cc16', // lime-500
]

/** 按索引取色，超出则循环 */
export function getChartColor(index: number): string {
  return CHART_COLORS[index % CHART_COLORS.length]
}

/**
 * 二维行转对象数组（Recharts 需要）
 * @param columns 列名
 * @param rows 二维行数据
 * @param limit 可选限制条数
 */
export function rowsToObjects(
  columns: string[],
  rows: unknown[][],
  limit?: number,
): Record<string, unknown>[] {
  const data = limit !== undefined ? rows.slice(0, limit) : rows
  return data.map((row) => {
    const obj: Record<string, unknown> = {}
    columns.forEach((col, i) => {
      obj[col] = row[i]
    })
    return obj
  })
}

/**
 * 智能解析 X 轴字段
 * 优先级：chart.x_field > 第一列 > ''
 */
export function resolveXField(
  chart: ChartSpec,
  columns: string[],
): string {
  if (chart.x_field && columns.includes(chart.x_field)) {
    return chart.x_field
  }
  return columns[0] ?? ''
}

/**
 * 智能解析 Y 轴字段
 * 优先级：chart.y_fields > chart.y_field > 除第一列外所有数值列 > 除第一列外所有列
 */
export function resolveYFields(
  chart: ChartSpec,
  columns: string[],
): string[] {
  if (chart.y_fields && chart.y_fields.length > 0) {
    return chart.y_fields.filter((f) => columns.includes(f))
  }
  if (chart.y_field && columns.includes(chart.y_field)) {
    return [chart.y_field]
  }
  // 默认取除第一列（通常是类别/时间）以外的所有列
  if (columns.length > 1) {
    return columns.slice(1)
  }
  return columns
}
