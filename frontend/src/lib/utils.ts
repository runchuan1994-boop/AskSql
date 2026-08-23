/**
 * 工具函数
 */

/** 合并类名 */
export function clsx(...args: (string | false | null | undefined)[]): string {
  return args.filter(Boolean).join(' ')
}

/** 格式化时间戳 — 使用浏览器语言 */
export function formatTime(isoString?: string): string {
  if (!isoString) return ''
  try {
    const d = new Date(isoString)
    const now = new Date()
    const sameDay =
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate()
    const locale = navigator.language
    if (sameDay) {
      return d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })
    }
    return d.toLocaleDateString(locale, { month: '2-digit', day: '2-digit' })
  } catch {
    return isoString
  }
}

/** 复制到剪贴板 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // fallback
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.left = '-9999px'
    document.body.appendChild(ta)
    ta.select()
    try {
      document.execCommand('copy')
      document.body.removeChild(ta)
      return true
    } catch {
      document.body.removeChild(ta)
      return false
    }
  }
}

/** 截取字符串（中英文混合） */
export function truncate(str: string, maxLen: number): string {
  if (str.length <= maxLen) return str
  return str.slice(0, maxLen) + '...'
}
