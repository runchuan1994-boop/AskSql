/**
 * 国际化 Context + Provider
 * 轻量实现：不引入 i18next 等第三方库
 */
import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react'
import { zhCN, TranslationKey } from './locales/zh-CN'
import { en } from './locales/en'

export type Locale = 'zh-CN' | 'en'

const translations: Record<Locale, Record<TranslationKey, string>> = {
  'zh-CN': zhCN,
  'en': en,
}

const STORAGE_KEY = 'asksql-locale'

// 自动检测浏览器语言
function detectLocale(): Locale {
  const saved = localStorage.getItem(STORAGE_KEY) as Locale | null
  if (saved && translations[saved]) {
    return saved
  }
  const browserLang = navigator.language.toLowerCase()
  if (browserLang.startsWith('zh')) {
    return 'zh-CN'
  }
  return 'en'
}

interface I18nContextValue {
  locale: Locale
  setLocale: (locale: Locale) => void
  t: (key: TranslationKey, params?: Record<string, string | number>) => string
}

const I18nContext = createContext<I18nContextValue | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => detectLocale())

  const setLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale)
    localStorage.setItem(STORAGE_KEY, newLocale)
    // 更新 HTML lang 属性
    document.documentElement.lang = newLocale
  }, [])

  useEffect(() => {
    document.documentElement.lang = locale
  }, [locale])

  const t = useCallback(
    (key: TranslationKey, params?: Record<string, string | number>): string => {
      let text = translations[locale][key] || translations['en'][key] || key
      if (params) {
        Object.entries(params).forEach(([k, v]) => {
          text = text.replace(`{${k}}`, String(v))
        })
      }
      return text
    },
    [locale],
  )

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  )
}

export function useTranslation() {
  const ctx = useContext(I18nContext)
  if (!ctx) {
    throw new Error('useTranslation must be used within I18nProvider')
  }
  return ctx
}
