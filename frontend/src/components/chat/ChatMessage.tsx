/**
 * 单条聊天消息
 */
import { User, Bot } from 'lucide-react'
import type { Message } from '../../lib/types'
import { SqlDisplay } from './SqlDisplay'
import { ResultTable } from './ResultTable'
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

        <div
          className={clsx(
            'rounded-lg px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words',
            isUser
              ? 'bg-indigo-600 text-white'
              : 'bg-white border border-gray-200 text-gray-800',
          )}
        >
          {message.content || (
            <span className="text-gray-400 italic">（无内容）</span>
          )}
        </div>

        {/* SQL 代码块 */}
        {message.sql_text && (
          <div className="mt-3 w-full">
            <SqlDisplay sql={message.sql_text} />
          </div>
        )}

        {/* 查询结果表格 */}
        {message.result && message.result.rows && message.result.rows.length > 0 && (
          <div className="mt-3 w-full">
            <ResultTable result={message.result} />
          </div>
        )}
      </div>
    </div>
  )
}
