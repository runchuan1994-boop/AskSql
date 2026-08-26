/**
 * 图表工具函数
 */
import type { ChartSpec } from '../../lib/types'

/**
 * 8 色玻璃质感色板
 * 以紫蓝为主色调，搭配和谐的辅助色
 */
export const CHART_COLORS: string[] = [
  '#6366F1', // 品牌紫蓝
  '#8B5CF6', // 紫罗兰
  '#06B6D4', // 青蓝
  '#10B981', // 翡翠绿
  '#F59E0B', // 琥珀金
  '#EC4899', // 玫瑰粉
  '#F43F5E', // 珊瑚红
  '#8B5CF6', // 深紫
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
  const data = limit != null && limit > 0 ? rows.slice(0, limit) : rows
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
 * 优先级：chart.x_field > 日期/时间类列 > 第一列 > ''
 */
export function resolveXField(
  chart: ChartSpec,
  columns: string[],
): string {
  if (chart.x_field && columns.includes(chart.x_field)) {
    return chart.x_field
  }
  // 智能寻找日期/时间类列作为 X 轴
  const dateCol = columns.find((c) =>
    /date|time|year|month|day|period|dt|created|updated/i.test(c),
  )
  if (dateCol) return dateCol
  return columns[0] ?? ''
}

/**
 * 判断值是否为日期/时间格式的字符串
 */
export function isDateTimeValue(value: unknown): boolean {
  if (typeof value !== 'string') return false
  // ISO 日期格式: 2024-01-01, 2024-01-01T00:00:00, 2024/01/01 等
  return /^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?$/.test(
    value,
  )
}

/**
 * 友好格式化日期值
 * - 带时间但时分秒都是 0 → 只保留日期
 * - ISO 格式 → 转为 YYYY-MM-DD 或 YYYY-MM
 * - 按粒度自动选择格式
 * - 处理 UTC 日期字符串的时区问题（如 2024-06-01 不应显示时间）
 */
export function formatDateTick(value: unknown): string {
  if (value == null || value === '') return ''
  const str = String(value).trim()

  // 先判断原始字符串是否包含时间部分
  const hasTimeInString = /[ T]\d{1,2}:\d{2}/.test(str)
  // 原始字符串是否是当月第一天的日期（用于月份格式判断）
  const isFirstOfMonthStr = /^\d{4}[-/]\d{1,2}[-/]01$/.test(str)

  // 尝试解析日期（用本地时间解析，避免 UTC 时区偏移）
  // 对于 "YYYY-MM-DD" 格式，new Date 会按 UTC 解析导致时区偏移
  let date: Date
  const pureDateMatch = str.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/)
  if (pureDateMatch) {
    // 纯日期：按本地时间构造
    date = new Date(
      Number(pureDateMatch[1]),
      Number(pureDateMatch[2]) - 1,
      Number(pureDateMatch[3]),
    )
  } else {
    date = new Date(str)
  }
  if (isNaN(date.getTime())) return str

  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  const hh = String(date.getHours()).padStart(2, '0')
  const mm = String(date.getMinutes()).padStart(2, '0')

  const hasTime = hasTimeInString && (
    date.getHours() !== 0 || date.getMinutes() !== 0 || date.getSeconds() !== 0
  )

  // 如果是当月第一天且没有时间 → 显示为月份
  if (!hasTime && (isFirstOfMonthStr || date.getDate() === 1)) {
    return `${y}-${m}`
  }

  if (!hasTime) {
    return `${y}-${m}-${d}`
  }

  return `${y}-${m}-${d} ${hh}:${mm}`
}

/**
 * 友好格式化数值
 * - 大数字添加千分位
 * - 小数控制精度
 */
export function formatNumberTick(value: unknown): string {
  if (value == null || value === '') return ''
  const num = Number(value)
  if (isNaN(num)) return String(value)

  // 整数
  if (Number.isInteger(num)) {
    return num.toLocaleString('en-US')
  }

  // 小数：最多 2 位有效小数，去掉末尾 0
  const fixed = num.toFixed(2)
  const trimmed = fixed.replace(/\.?0+$/, '')
  return Number(trimmed).toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })
}

/**
 * 智能格式化 tick 值
 * 自动识别日期和数值类型
 */
export function smartFormatTick(value: unknown): string {
  if (isDateTimeValue(value)) {
    return formatDateTick(value)
  }
  if (typeof value === 'number' || (typeof value === 'string' && !isNaN(Number(value)))) {
    return formatNumberTick(value)
  }
  return String(value ?? '')
}

/**
 * 智能解析 Y 轴数值字段
 * 优先级：chart.y_fields > chart.y_field > 排除 ID/时间/分类后的列 > 除第一列外所有列
 */
export function resolveYFields(
  chart: ChartSpec,
  columns: string[],
): string[] {
  if (chart.y_fields && chart.y_fields.length > 0) {
    const matched = chart.y_fields.filter((f) => columns.includes(f))
    if (matched.length > 0) {
      return matched
    }
    // 指定的 y_fields 全部不匹配 → 走智能匹配兜底
  }
  if (chart.y_field) {
    if (columns.includes(chart.y_field)) {
      return [chart.y_field]
    }
    // 指定的 y_field 不匹配 → 走智能匹配兜底
  }
  // 排除明显的非数值列（ID、时间、分类、名称类），剩下的作为 Y 轴
  const nonValuePattern = /id|date|time|year|month|day|name|title|category|type|status|code$/i
  const valueCols = columns.filter((c) => !nonValuePattern.test(c))
  if (valueCols.length > 0) {
    return valueCols
  }
  // 兜底：除第一列以外的所有列
  if (columns.length > 1) {
    return columns.slice(1)
  }
  return columns
}
