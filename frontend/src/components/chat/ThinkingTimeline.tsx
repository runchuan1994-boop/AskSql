/**
 * 思考过程时间线
 * 玻璃质感风格
 *
 * 以垂直时间线形式展示 Agent 每个步骤的状态和详情：
 * - 流式中默认展开，显示完整时间线
 * - 完成后折叠为一行摘要，点击可展开查看
 * - 每个步骤可单独展开/收起查看详情
 */
import { useState } from 'react'
import { Sparkles, ChevronDown, ChevronRight, CheckCircle2, Circle, XCircle } from 'lucide-react'
import type { ThinkingStep } from '../../lib/types'
import { StepDetailRenderer } from './StepDetailRenderer'
import { clsx } from '../../lib/utils'
import { useTranslation } from '../../i18n'

interface ThinkingTimelineProps {
  steps: ThinkingStep[]
  isStreaming: boolean
}

// 状态图标
function StepIcon({ status }: { status: ThinkingStep['status'] }) {
  switch (status) {
    case 'completed':
      return <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
    case 'active':
      return (
        <div className="flex items-center gap-0.5 shrink-0">
          <span className="thinking-dot w-1.5 h-1.5 rounded-full bg-brand-500" />
          <span className="thinking-dot w-1.5 h-1.5 rounded-full bg-brand-500" />
          <span className="thinking-dot w-1.5 h-1.5 rounded-full bg-brand-500" />
        </div>
      )
    case 'error':
      return <XCircle size={14} className="text-red-500 shrink-0" />
    case 'pending':
    default:
      return <Circle size={14} className="text-slate-300 shrink-0" />
  }
}

// 单个步骤行
function StepRow({ step }: { step: ThinkingStep }) {
  const [expanded, setExpanded] = useState(false)
  const hasDetail = !!step.detail || step.status === 'error'
  const isDone = step.status === 'completed'
  const isActive = step.status === 'active'
  const isError = step.status === 'error'

  const canExpand = hasDetail && (isDone || isError)
  // active 状态如果有 detail 也可以展开
  const shouldExpand = expanded || isActive // active 状态自动展开

  const toggleExpand = () => {
    if (canExpand || isActive) {
      setExpanded(!expanded)
    }
  }

  return (
    <div>
      <div
        className={clsx(
          'flex items-center gap-2 text-sm leading-5',
          canExpand && 'cursor-pointer hover:bg-white/50 -mx-1 px-1 py-0.5 rounded-xl transition-all',
          isError && 'text-red-600',
          isDone && 'text-slate-500',
          isActive && 'text-brand-600 font-medium',
          step.status === 'pending' && 'text-slate-300',
        )}
        onClick={toggleExpand}
      >
        <StepIcon status={step.status} />
        <span className="flex-1 truncate">{step.name}</span>
        {step.duration_ms !== undefined && isDone && (
          <span className="text-[11px] text-slate-400 font-normal shrink-0">
            {step.duration_ms} ms
          </span>
        )}
        {canExpand && (
          <span className="text-slate-300 shrink-0">
            {shouldExpand ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        )}
      </div>

      {/* 详情面板 */}
      {shouldExpand && hasDetail && (
        <div className="ml-6 mt-2 mb-2 pl-3 border-l-2 border-brand-100">
          <StepDetailRenderer step={step} />
        </div>
      )}
    </div>
  )
}

// 计算统计信息
function getStats(steps: ThinkingStep[]) {
  const completed = steps.filter((s) => s.status === 'completed')
  const totalMs = completed.reduce((sum, s) => sum + (s.duration_ms || 0), 0)
  return {
    totalSteps: steps.length,
    completedSteps: completed.length,
    totalMs,
  }
}

export function ThinkingTimeline({ steps, isStreaming }: ThinkingTimelineProps) {
  const { t } = useTranslation()
  // 流式中：展开；完成后：折叠为摘要
  const [collapsed, setCollapsed] = useState(false)

  const { totalSteps, completedSteps, totalMs } = getStats(steps)
  const hasSteps = steps.length > 0

  // 折叠状态下显示摘要条
  if (!isStreaming && collapsed && hasSteps) {
    return (
      <div className="flex gap-3">
        {/* 头像占位 */}
        <div className="w-8 h-8 rounded-2xl bg-gradient-to-br from-emerald-500/10 to-teal-500/10 text-emerald-600 flex items-center justify-center shrink-0">
          <Sparkles size={16} />
        </div>
        <div className="flex-1 max-w-[85%]">
          <button
            onClick={() => setCollapsed(false)}
            className="w-full text-left bg-white/70 backdrop-blur-xl border border-white/60 rounded-2xl px-4 py-2.5 text-sm text-slate-500 hover:bg-white/90 hover:border-white/80 transition-all flex items-center gap-2 shadow-glass"
          >
            <CheckCircle2 size={14} className="text-emerald-500" />
            <span>
              {t('thinking.summary')} · {completedSteps} {t('thinking.steps')} ·{' '}
              {totalMs >= 1000 ? `${(totalMs / 1000).toFixed(1)}s` : `${totalMs}ms`}
            </span>
            <ChevronDown size={14} className="ml-auto text-slate-400" />
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-3">
      {/* 头像占位 */}
      <div className="w-8 h-8 rounded-2xl bg-gradient-to-br from-emerald-500/10 to-teal-500/10 text-emerald-600 flex items-center justify-center shrink-0">
        <Sparkles size={16} />
      </div>

      <div className="flex-1 max-w-[85%]">
        <div className="flex items-center justify-between mb-1">
          <div className="text-xs text-slate-400">
            {isStreaming ? t('thinking.thinking') : t('thinking.title')}
          </div>
          {!isStreaming && hasSteps && (
            <button
              onClick={() => setCollapsed(true)}
              className="text-xs text-slate-400 hover:text-slate-600 transition-colors"
            >
              {t('thinking.collapse')}
            </button>
          )}
        </div>

        <div className="bg-white/70 backdrop-blur-xl border border-white/60 rounded-2xl p-3.5 shadow-glass">
          {/* 步骤时间线 */}
          {hasSteps ? (
            <div className="space-y-1.5">
              {steps.map((step) => (
                <StepRow key={step.step} step={step} />
              ))}
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <StepIcon status="active" />
              <span>{t('thinking.prep')}</span>
            </div>
          )}

          {/* 进度统计 */}
          {hasSteps && isStreaming && (
            <div className="mt-3 pt-2.5 border-t border-white/40 flex items-center justify-between text-xs text-slate-400">
              <span>
                {completedSteps}/{totalSteps} {t('thinking.steps')}
              </span>
              {totalMs > 0 && (
                <span>
                  {t('thinking.elapsed')}{' '}
                  {totalMs >= 1000 ? `${(totalMs / 1000).toFixed(1)}s` : `${totalMs}ms`}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
