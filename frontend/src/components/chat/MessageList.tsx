/**
 * 消息列表
 */
import { useEffect, useRef } from 'react'
import { ChatMessage } from './ChatMessage'
import type { Message, ThinkingStep } from '../../lib/types'

interface MessageListProps {
  messages: Message[]
  isLoading: boolean
  isStreaming: boolean
  thinkingSteps: ThinkingStep[]
  streamingSql: string | null
}

export function MessageList({
  messages,
  isLoading,
  isStreaming,
  thinkingSteps,
  streamingSql,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming, thinkingSteps, streamingSql])

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center text-gray-400 text-sm">
        加载消息中...
      </div>
    )
  }

  if (messages.length === 0 && !isStreaming) {
    return (
      <div className="h-full flex items-center justify-center text-gray-400 text-sm">
        开始你的第一个问题吧
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto py-6 px-4 space-y-6">
        {messages.map((msg, idx) => {
          // 最后一条空内容的 assistant 消息 + 流式中 → 显示思考过程和流式 SQL
          const isStreamingPlaceholder =
            isStreaming &&
            msg.role === 'assistant' &&
            !msg.content &&
            idx === messages.length - 1

          if (isStreamingPlaceholder) {
            // 流式中的占位消息：展示思考时间线和当前 SQL
            return (
              <ChatMessage
                key={msg.id}
                message={{
                  ...msg,
                  thinking_steps: thinkingSteps.length > 0 ? thinkingSteps : undefined,
                  sql_text: streamingSql || undefined,
                }}
                isStreaming={true}
              />
            )
          }

          return <ChatMessage key={msg.id} message={msg} />
        })}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
