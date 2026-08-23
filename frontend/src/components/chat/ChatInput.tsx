/**
 * 聊天输入框
 * 玻璃质感风格
 */
import { useState, KeyboardEvent } from 'react'
import { Send } from 'lucide-react'
import { clsx } from '../../lib/utils'
import { useTranslation } from '../../i18n'

interface ChatInputProps {
  onSend: (content: string) => void | Promise<void>
  disabled?: boolean
  placeholder?: string
}

export function ChatInput({
  onSend,
  disabled = false,
  placeholder,
}: ChatInputProps) {
  const { t } = useTranslation()
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
    <div className="p-3 shrink-0">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-end gap-2 bg-white/80 backdrop-blur-xl border border-white/60 rounded-2xl p-2.5 focus-within:border-brand-500/40 focus-within:ring-4 focus-within:ring-brand-500/10 focus-within:shadow-glow transition-all">
          <textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled || sending}
            rows={1}
            className="flex-1 resize-none bg-transparent outline-none text-sm py-1.5 px-2 max-h-32 disabled:opacity-50 text-slate-700 placeholder:text-slate-400"
            style={{ minHeight: '32px' }}
          />
          <button
            onClick={handleSend}
            disabled={disabled || sending || !value.trim()}
            className={clsx(
              'p-2.5 rounded-xl text-white transition-all shrink-0',
              disabled || sending || !value.trim()
                ? 'bg-slate-200 cursor-not-allowed'
                : 'bg-gradient-to-r from-brand-500 to-violet-500 hover:from-brand-600 hover:to-violet-600 hover:shadow-glow active:scale-95',
            )}
            title={t('chat.send')}
          >
            <Send size={16} />
          </button>
        </div>
        <p className="text-xs text-slate-400 mt-2 text-center">
          {t('chat.shortcutHint')}
        </p>
      </div>
    </div>
  )
}
