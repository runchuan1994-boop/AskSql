/**
 * 思考过程指示器
 * 显示当前 SSE 事件进度和流式 SQL
 */
import { Sparkles, CheckCircle2, Circle } from 'lucide-react'
import { THINKING_STAGES, type ThinkingStage } from '../../lib/types'
import { SqlDisplay } from './SqlDisplay'
import { clsx } from '../../lib/utils'

interface ThinkingIndicatorProps {
  stage: ThinkingStage | null
  sql: string | null
}

const STAGE_ORDER: ThinkingStage[] = THINKING_STAGES.map((s) => s.key)

export function ThinkingIndicator({ stage, sql }: ThinkingIndicatorProps) {
  const currentIdx = stage ? STAGE_ORDER.indexOf(stage) : -1

  return (
    <div className="flex gap-3">
      {/* 头像占位 */}
      <div className="w-8 h-8 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center shrink-0">
        <Sparkles size={16} />
      </div>

      <div className="flex-1 max-w-[85%]">
        <div className="text-xs text-gray-400 mb-1">助手思考中...</div>

        <div className="bg-white border border-gray-200 rounded-lg p-3 space-y-2">
          {/* 阶段进度 */}
          <div className="space-y-1.5">
            {THINKING_STAGES.map((s, idx) => {
              const isDone = currentIdx > idx
              const isCurrent = currentIdx === idx
              const isPending = currentIdx < idx

              return (
                <div
                  key={s.key}
                  className={clsx(
                    'flex items-center gap-2 text-sm',
                    isPending && 'text-gray-300',
                    isCurrent && 'text-indigo-600 font-medium',
                    isDone && 'text-gray-500',
                  )}
                >
                  {isDone ? (
                    <CheckCircle2 size={14} className="text-emerald-500" />
                  ) : isCurrent ? (
                    <div className="flex items-center gap-1">
                      <span className="thinking-dot w-1.5 h-1.5 rounded-full bg-indigo-500" />
                      <span className="thinking-dot w-1.5 h-1.5 rounded-full bg-indigo-500" />
                      <span className="thinking-dot w-1.5 h-1.5 rounded-full bg-indigo-500" />
                    </div>
                  ) : (
                    <Circle size={14} />
                  )}
                  <span>{s.label}</span>
                </div>
              )
            })}
          </div>
        </div>

        {/* 流式 SQL 预览 */}
        {sql && (
          <div className="mt-3">
            <SqlDisplay sql={sql} />
          </div>
        )}
      </div>
    </div>
  )
}
