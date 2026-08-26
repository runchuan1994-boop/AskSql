/**
 * 记忆保存提示 Toast
 *
 * 当检测到用户纠错并成功保存记忆时，显示一个轻量的浮动提示。
 * 玻璃拟态风格，4 秒后自动消失。
 */
import { BookMarked } from 'lucide-react'
import type { MemorySavedNotice } from '../../hooks/useChat'
import { truncate } from '../../lib/utils'

interface MemorySavedToastProps {
  notice: MemorySavedNotice | null
}

export function MemorySavedToast({ notice }: MemorySavedToastProps) {
  if (!notice) return null

  const displayContent = notice.entityName
    ? `${notice.entityName}：${notice.content}`
    : notice.content

  return (
    <div className="pointer-events-none fixed bottom-24 left-1/2 -translate-x-1/2 z-50 animate-fade-in-up">
      <div className="flex items-center gap-2.5 px-4 py-2.5 rounded-2xl bg-white/70 backdrop-blur-xl border border-white/60 shadow-glass-lg">
        <div className="w-6 h-6 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center shrink-0">
          <BookMarked size={14} />
        </div>
        <span className="text-sm text-slate-600 max-w-md">
          <span className="font-medium text-emerald-600 mr-1">已记下：</span>
          {truncate(displayContent, 80)}
        </span>
      </div>
    </div>
  )
}
