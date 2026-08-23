/**
 * 澄清问题卡片
 *
 * 当 agent 需要向用户澄清问题时展示，列出所有待确认的问题。
 */
import { HelpCircle, CheckCircle2 } from 'lucide-react'
import { clsx } from '../../lib/utils'

interface ClarificationCardProps {
  questions: string[]
  resolved?: boolean
}

export function ClarificationCard({ questions, resolved = false }: ClarificationCardProps) {
  return (
    <div
      className={clsx(
        'rounded-lg border px-4 py-3 space-y-2',
        resolved
          ? 'bg-gray-50 border-gray-200 opacity-70'
          : 'bg-amber-50 border-amber-200',
      )}
    >
      {/* 标题 */}
      <div className="flex items-center gap-2">
        {resolved ? (
          <CheckCircle2 size={16} className="text-emerald-500 shrink-0" />
        ) : (
          <HelpCircle size={16} className="text-amber-500 shrink-0" />
        )}
        <span
          className={clsx(
            'text-sm font-medium',
            resolved ? 'text-gray-500' : 'text-amber-800',
          )}
        >
          {resolved ? '已澄清' : '需要向您确认几个问题'}
        </span>
      </div>

      {/* 问题列表 */}
      <ol className="space-y-1.5 list-decimal list-inside pl-1">
        {questions.map((q, i) => (
          <li
            key={i}
            className={clsx(
              'text-sm leading-relaxed',
              resolved ? 'text-gray-500' : 'text-amber-900',
            )}
          >
            {q}
          </li>
        ))}
      </ol>

      {/* 提示 */}
      {!resolved && (
        <p className="text-xs text-amber-600 pt-1">
          请在下方输入框中回复你的想法，我会根据你的回答继续查询。
        </p>
      )}
    </div>
  )
}
