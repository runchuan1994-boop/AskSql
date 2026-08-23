/**
 * 消息列表
 */
import { useEffect, useRef } from 'react'
import { ChatMessage } from './ChatMessage'
import { ThinkingTimeline } from './ThinkingTimeline'
import type { Message, ThinkingStep } from '../../lib/types'

interface MessageListProps {
  messages: Message[]
  isLoading: boolean
  isStreaming: boolean
  thinkingSteps: ThinkingStep[]
}

export function MessageList({
  messages,
  isLoading,
  isStreaming,
  thinkingSteps,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming, thinkingSteps])

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
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}

        {isStreaming && (
          <ThinkingTimeline steps={thinkingSteps} isStreaming={isStreaming} />
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
