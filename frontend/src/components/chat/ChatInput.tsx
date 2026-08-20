/**
 * 聊天输入框
 */
import { useState, KeyboardEvent } from 'react'
import { Send } from 'lucide-react'
import { clsx } from '../../lib/utils'

interface ChatInputProps {
  onSend: (content: string) => void | Promise<void>
  disabled?: boolean
  placeholder?: string
}

export function ChatInput({
  onSend,
  disabled = false,
  placeholder = '输入你的问题，按 Enter 发送...',
}: ChatInputProps) {
  const [value, setValue] = useState('')
  const [sending, setSending] = useState(false)

  const handleSend = async () => {
    const content = value.trim()
    if (!content || disabled || sending) return
    setSending(true)
    try {
      await onSend(content)
      setValue('')
    } finally {
      setSending(false)
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="border-t border-gray-200 bg-white p-3 shrink-0">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-end gap-2 border border-gray-300 rounded-xl p-2 focus-within:border-indigo-400 focus-within:ring-2 focus-within:ring-indigo-100 transition-colors">
          <textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled || sending}
            rows={1}
            className="flex-1 resize-none bg-transparent outline-none text-sm py-1.5 px-1 max-h-32 disabled:opacity-50"
            style={{ minHeight: '32px' }}
          />
          <button
            onClick={handleSend}
            disabled={disabled || sending || !value.trim()}
            className={clsx(
              'p-2 rounded-lg text-white transition-colors shrink-0',
              disabled || sending || !value.trim()
                ? 'bg-gray-300 cursor-not-allowed'
                : 'bg-indigo-600 hover:bg-indigo-700',
            )}
            title="发送"
          >
            <Send size={16} />
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-1.5 text-center">
          Enter 发送，Shift + Enter 换行
        </p>
      </div>
    </div>
  )
}
