/**
 * 思考过程时间线
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
          <span className="thinking-dot w-1.5 h-1.5 rounded-full bg-indigo-500" />
          <span className="thinking-dot w-1.5 h-1.5 rounded-full bg-indigo-500" />
          <span className="thinking-dot w-1.5 h-1.5 rounded-full bg-indigo-500" />
        </div>
      )
    case 'error':
      return <XCircle size={14} className="text-red-500 shrink-0" />
    case 'pending':
    default:
      return <Circle size={14} className="text-gray-300 shrink-0" />
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
          canExpand && 'cursor-pointer hover:bg-gray-50 -mx-1 px-1 py-0.5 rounded-md transition-colors',
          isError && 'text-red-600',
          isDone && 'text-gray-500',
          isActive && 'text-indigo-600 font-medium',
          step.status === 'pending' && 'text-gray-300',
        )}
        onClick={toggleExpand}
      >
        <StepIcon status={step.status} />
        <span className="flex-1 truncate">{step.name}</span>
        {step.duration_ms !== undefined && isDone && (
          <span className="text-[11px] text-gray-400 font-normal shrink-0">
            {step.duration_ms} ms
          </span>
        )}
        {canExpand && (
          <span className="text-gray-300 shrink-0">
            {shouldExpand ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        )}
      </div>

      {/* 详情面板 */}
      {shouldExpand && hasDetail && (
        <div className="ml-6 mt-2 mb-2 pl-3 border-l-2 border-gray-100">
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
  // 流式中：展开；完成后：折叠为摘要
  const [collapsed, setCollapsed] = useState(false)

  // 当从流式切换到完成时，自动折叠
  // 但要等内容稳定后再折叠，给用户一点时间看
  // 这里用一个简单策略：isStreaming 变 false 时 collapsed 自动变 true
  // 用户可以手动展开查看

  const { totalSteps, completedSteps, totalMs } = getStats(steps)
  const hasSteps = steps.length > 0

  // 折叠状态下显示摘要条
  if (!isStreaming && collapsed && hasSteps) {
    return (
      <div className="flex gap-3">
        {/* 头像占位 */}
        <div className="w-8 h-8 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center shrink-0">
          <Sparkles size={16} />
        </div>
        <div className="flex-1 max-w-[85%]">
          <button
            onClick={() => setCollapsed(false)}
            className="w-full text-left bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-500 hover:border-gray-300 hover:text-gray-700 transition-colors flex items-center gap-2"
          >
            <CheckCircle2 size={14} className="text-emerald-500" />
            <span>
              思考完成 · {completedSteps} 步 ·{' '}
              {totalMs >= 1000 ? `${(totalMs / 1000).toFixed(1)}s` : `${totalMs}ms`}
            </span>
            <ChevronDown size={14} className="ml-auto text-gray-400" />
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-3">
      {/* 头像占位 */}
      <div className="w-8 h-8 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center shrink-0">
        <Sparkles size={16} />
      </div>

      <div className="flex-1 max-w-[85%]">
        <div className="flex items-center justify-between mb-1">
          <div className="text-xs text-gray-400">
            {isStreaming ? '助手思考中...' : '思考过程'}
          </div>
          {!isStreaming && hasSteps && (
            <button
              onClick={() => setCollapsed(true)}
              className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
            >
              收起
            </button>
          )}
        </div>

        <div className="bg-white border border-gray-200 rounded-lg p-3">
          {/* 步骤时间线 */}
          {hasSteps ? (
            <div className="space-y-1.5">
              {steps.map((step) => (
                <StepRow key={step.step} step={step} />
              ))}
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <StepIcon status="active" />
              <span>准备中...</span>
            </div>
          )}

          {/* 进度统计 */}
          {hasSteps && isStreaming && (
            <div className="mt-3 pt-2 border-t border-gray-100 flex items-center justify-between text-xs text-gray-400">
              <span>
                {completedSteps}/{totalSteps} 步
              </span>
              {totalMs > 0 && (
                <span>
                  已用{' '}
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
