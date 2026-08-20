/**
 * 消息列表
 */
import { useEffect, useRef } from 'react'
import { ChatMessage } from './ChatMessage'
import { ThinkingIndicator } from './ThinkingIndicator'
import type { Message, ThinkingStage } from '../../lib/types'

interface MessageListProps {
  messages: Message[]
  isLoading: boolean
  isStreaming: boolean
  currentStage: ThinkingStage | null
  streamingSql: string | null
}

export function MessageList({
  messages,
  isLoading,
  isStreaming,
  currentStage,
  streamingSql,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming, currentStage, streamingSql])

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
          <ThinkingIndicator stage={currentStage} sql={streamingSql} />
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
