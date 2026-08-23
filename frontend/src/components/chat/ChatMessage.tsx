/**
 * 单条聊天消息
 */
import { User, Bot } from 'lucide-react'
import type { Message } from '../../lib/types'
import { SqlDisplay } from './SqlDisplay'
import { ResultTable } from './ResultTable'
import { ChartGrid } from '../chart/ChartGrid'
import { ClarificationCard } from './ClarificationCard'
import { clsx, formatTime } from '../../lib/utils'

interface ChatMessageProps {
  message: Message
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user'

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
          'w-8 h-8 rounded-full flex items-center justify-center shrink-0',
          isUser
            ? 'bg-indigo-100 text-indigo-600'
            : 'bg-emerald-100 text-emerald-600',
        )}
      >
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>

      {/* 内容 */}
      <div
        className={clsx(
          'flex-1 min-w-0 max-w-[85%]',
          isUser ? 'flex flex-col items-end' : '',
        )}
      >
        <div className="text-xs text-gray-400 mb-1">
          {isUser ? '你' : '助手'}
          <span className="ml-2">{formatTime(message.created_at)}</span>
        </div>

        {message.content && (
          <div
            className={clsx(
              'rounded-lg px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words',
              isUser
                ? 'bg-indigo-600 text-white'
                : 'bg-white border border-gray-200 text-gray-800',
            )}
          >
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

        {/* 查询假设说明 */}
        {message.query_assumptions && message.query_assumptions.length > 0 && (
          <div className="mt-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-md text-xs text-amber-800">
            <div className="font-medium mb-1 text-amber-700">💡 基于以下假设分析</div>
            <ul className="list-disc list-inside space-y-0.5">
              {message.query_assumptions.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
            <div className="mt-1 text-amber-600">如果假设不对，可以告诉我调整。</div>
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
