/**
 * 澄清问题卡片
 * 玻璃质感风格
 *
 * 当 agent 需要向用户澄清问题时展示，列出所有待确认的问题。
 */
import { HelpCircle, CheckCircle2 } from 'lucide-react'
import { clsx } from '../../lib/utils'
import { useTranslation } from '../../i18n'

interface ClarificationCardProps {
  questions: string[]
  resolved?: boolean
}

export function ClarificationCard({ questions, resolved = false }: ClarificationCardProps) {
  const { t } = useTranslation()
  return (
    <div
      className={clsx(
        'rounded-2xl border px-4 py-3.5 space-y-2.5',
        resolved
          ? 'bg-slate-50/80 backdrop-blur border-slate-200/60 opacity-70'
          : 'bg-amber-50/80 backdrop-blur border-amber-200/60',
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
            resolved ? 'text-slate-500' : 'text-amber-800',
          )}
        >
          {resolved ? t('clarification.resolved') : t('clarification.needConfirm')}
        </span>
      </div>

      {/* 问题列表 */}
      <ol className="space-y-1.5 list-decimal list-inside pl-1">
        {questions.map((q, i) => (
          <li
            key={i}
            className={clsx(
              'text-sm leading-relaxed',
              resolved ? 'text-slate-500' : 'text-amber-900',
            )}
          >
            {q}
          </li>
        ))}
      </ol>

      {/* 提示 */}
      {!resolved && (
        <p className="text-xs text-amber-600 pt-1">
          {t('clarification.hint')}
        </p>
      )}
    </div>
  )
}
