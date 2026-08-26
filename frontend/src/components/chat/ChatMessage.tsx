/**
 * 单条聊天消息
 * 玻璃质感风格
 */
import { User, Bot, AlertCircle } from 'lucide-react'
import type { Message } from '../../lib/types'
import { SqlDisplay } from './SqlDisplay'
import { ResultTable } from './ResultTable'
import { ChartGrid } from '../chart/ChartGrid'
import { ClarificationCard } from './ClarificationCard'
import { ThinkingTimeline } from './ThinkingTimeline'
import { clsx, formatTime } from '../../lib/utils'
import { useTranslation } from '../../i18n'

interface ChatMessageProps {
  message: Message
  /** 是否处于流式生成中（用于思考时间线的交互状态） */
  isStreaming?: boolean
}

export function ChatMessage({ message, isStreaming = false }: ChatMessageProps) {
  const { t } = useTranslation()
  const isUser = message.role === 'user'
  const isError = message.is_error

  return (
    <div
      className={clsx(
        'flex gap-3',
        isUser ? 'flex-row-reverse' : 'flex-row',
      )}
    >
      {/* 头像 */}
      <div
        className={clsx(
          'w-8 h-8 rounded-2xl flex items-center justify-center shrink-0',
          isUser
            ? 'bg-gradient-to-br from-brand-500/10 to-violet-500/10 text-brand-500'
            : isError
              ? 'bg-gradient-to-br from-red-500/10 to-rose-500/10 text-red-500'
              : 'bg-gradient-to-br from-emerald-500/10 to-teal-500/10 text-emerald-600',
        )}
      >
        {isUser ? <User size={16} /> : isError ? <AlertCircle size={16} /> : <Bot size={16} />}
      </div>

      {/* 内容 */}
      <div
        className={clsx(
          'flex-1 min-w-0 max-w-[85%]',
          isUser ? 'flex flex-col items-end' : '',
        )}
      >
        <div className="text-xs text-slate-400 mb-1">
          {isUser ? t('message.you') : t('message.assistant')}
          <span className="ml-2">{formatTime(message.created_at)}</span>
        </div>

        {/* 思考过程时间线 - 显示在内容上方 */}
        {message.thinking_steps && message.thinking_steps.length > 0 && (
          <div className="mb-2">
            <ThinkingTimeline steps={message.thinking_steps} isStreaming={isStreaming} />
          </div>
        )}

        {message.content && (
          <div
            className={clsx(
              'rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words',
              isUser
                ? 'bg-gradient-to-r from-brand-500 to-violet-500 text-white shadow-glass'
                : isError
                  ? 'bg-red-50/80 backdrop-blur-xl border border-red-200/60 text-red-700 shadow-glass'
                  : 'bg-white/80 backdrop-blur-xl border border-white/60 text-slate-800 shadow-glass',
            )}
          >
            {isError && (
              <div className="flex items-center gap-1.5 font-medium mb-1 text-red-600">
                <AlertCircle size={14} />
                <span>出错了</span>
              </div>
            )}
            {message.content}
          </div>
        )}

        {/* 澄清卡片 */}
        {message.clarification && message.clarification.questions.length > 0 && (
          <div className="mt-2">
            <ClarificationCard
              questions={message.clarification.questions}
              resolved={message.clarification.resolved}
            />
          </div>
        )}

        {/* 查询假设说明 - 玻璃质感 */}
        {message.query_assumptions && message.query_assumptions.length > 0 && (
          <div className="mt-2 px-4 py-3 bg-amber-50/80 backdrop-blur border border-amber-200/60 rounded-2xl text-xs text-amber-800">
            <div className="font-medium mb-1.5 text-amber-700">{t('message.assumptions.title')}</div>
            <ul className="list-disc list-inside space-y-0.5">
              {message.query_assumptions.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
            <div className="mt-1.5 text-amber-600">{t('message.assumptions.hint')}</div>
          </div>
        )}

        {/* SQL 代码块 */}
        {message.sql_text && (
          <div className="mt-3 w-full">
            <SqlDisplay sql={message.sql_text} />
          </div>
        )}

        {/* 图表区域 */}
        {message.viz && message.viz.charts.length > 0 && message.result && (
          <div className="mt-3 w-full">
            <ChartGrid viz={message.viz} result={message.result} />
          </div>
        )}

        {/* 查询结果表格 */}
        {message.result && message.result.rows && message.result.rows.length > 0 && (
          <div className="mt-3 w-full">
            <ResultTable result={message.result} messageId={message.id} />
          </div>
        )}
      </div>
    </div>
  )
}
