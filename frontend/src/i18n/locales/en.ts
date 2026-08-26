/**
 * English translations
 */
import type { TranslationKey } from './zh-CN'

export const en: Record<TranslationKey, string> = {
  // App
  'app.loading': 'Loading...',
  'app.error': 'Error',
  'app.noProject': 'No projects yet. Please create a project and configure data sources in the backend.',

  // Layout
  'layout.toggleSidebar': 'Collapse sidebar',
  'layout.expandSidebar': 'Expand sidebar',
  'layout.appName': 'AskSql',
  'layout.schema': 'Schema',

  // Sidebar
  'sidebar.newChat': 'New Chat',
  'sidebar.loading': 'Loading...',
  'sidebar.noSessions': 'No sessions',
  'sidebar.newChatDefault': 'New chat',

  // Chat
  'chat.emptyTitle': 'Start your first AskSql conversation',
  'chat.emptySubtitle': 'Type a question below and AI will generate SQL automatically',
  'chat.sessionTitle': 'Session title',
  'chat.errorPrefix': 'Error',
  'chat.placeholder.default': 'Type your question, press Enter to send...',
  'chat.placeholder.noDatasource': 'Connect a data source first...',
  'chat.placeholder.clarification': 'Answer the clarification, press Enter to send...',
  'chat.send': 'Send',
  'chat.shortcutHint': 'Enter to send, Shift + Enter for new line',

  // Messages
  'message.you': 'You',
  'message.assistant': 'Assistant',
  'message.assumptions.title': '💡 Based on the following assumptions',
  'message.assumptions.hint': 'Let me know if any assumptions are incorrect.',

  // SQL
  'sql.label': 'SQL',
  'sql.copy': 'Copy',
  'sql.copied': 'Copied',

  // Thinking
  'thinking.thinking': 'Thinking...',
  'thinking.title': 'Thought process',
  'thinking.collapse': 'Collapse',
  'thinking.summary': 'Thinking complete',
  'thinking.steps': 'steps',
  'thinking.elapsed': 'Elapsed',
  'thinking.prep': 'Preparing...',

  // Result Table
  'result.title': 'Query Result',
  'result.totalRows': '{count} rows',
  'result.loading': 'Loading...',
  'result.null': 'NULL',
  'result.page': 'Page {current} / {total}',
  'result.prev': 'Previous',
  'result.next': 'Next',
  'result.pageSize': '{size} / page',
  'result.limitedWarning': 'Showing first {count} rows only. Refresh to see more data.',

  // Schema
  'schema.title': 'Schema Explorer',
  'schema.loading': 'Loading...',
  'schema.noData': 'No data source schema',
  'schema.noTables': 'No tables',
  'schema.columns': 'cols',
  'schema.memories': 'Memories',
  'schema.addMemory': 'Add Memory',
  'schema.searchMemories': 'Search memories',

  // Datasource
  'datasource.loading': 'Loading...',
  'datasource.noData': 'No data sources',
  'datasource.select': 'Select data source',

  // Clarification
  'clarification.needConfirm': 'Need to confirm a few questions',
  'clarification.resolved': 'Clarified',
  'clarification.hint': 'Please reply in the input box below and I will continue the query.',

  // Language
  'lang.zh': '简体中文',
  'lang.en': 'English',
  'lang.switch': 'Switch language',

  // Sample questions (empty state)
  'samples.totalUsers': 'Total user count',
  'samples.dau7d': 'DAU in last 7 days',
  'samples.top10Orders': 'Top 10 orders by amount',
  'samples.deptHeadcount': 'Headcount by department',

  // Time
  'time.justNow': 'Just now',
  'time.minutesAgo': '{n}m ago',
  'time.hoursAgo': '{n}h ago',
  'time.daysAgo': '{n}d ago',
  'time.yesterday': 'Yesterday',
}
