/**
 * 中文翻译
 */
export const zhCN = {
  // App
  'app.loading': '加载中...',
  'app.error': '错误',
  'app.noProject': '暂无项目，请先在后端创建项目并配置数据源。',

  // Layout
  'layout.toggleSidebar': '收起侧边栏',
  'layout.expandSidebar': '展开侧边栏',
  'layout.appName': 'AskSql',
  'layout.schema': 'Schema',

  // Sidebar
  'sidebar.newChat': '新建会话',
  'sidebar.loading': '加载中...',
  'sidebar.noSessions': '暂无会话',
  'sidebar.newChatDefault': '新对话',

  // Chat
  'chat.emptyTitle': '开始你的第一次 AskSql 对话',
  'chat.emptySubtitle': '在下方输入问题，AI 将自动生成 SQL 并查询',
  'chat.sessionTitle': '会话标题',
  'chat.errorPrefix': '错误',
  'chat.placeholder.default': '输入你的问题，按 Enter 发送...',
  'chat.placeholder.noDatasource': '请先连接数据源...',
  'chat.placeholder.clarification': '请回答澄清问题，按 Enter 发送...',
  'chat.send': '发送',
  'chat.shortcutHint': 'Enter 发送，Shift + Enter 换行',

  // Messages
  'message.you': '你',
  'message.assistant': '助手',
  'message.assumptions.title': '💡 基于以下假设分析',
  'message.assumptions.hint': '如果假设不对，可以告诉我调整。',

  // SQL
  'sql.label': 'SQL',
  'sql.copy': '复制',
  'sql.copied': '已复制',

  // Thinking
  'thinking.thinking': '助手思考中...',
  'thinking.title': '思考过程',
  'thinking.collapse': '收起',
  'thinking.summary': '思考完成',
  'thinking.steps': '步',
  'thinking.elapsed': '已用',
  'thinking.prep': '准备中...',

  // Result Table
  'result.title': '查询结果',
  'result.totalRows': '共 {count} 行',
  'result.loading': '加载中...',
  'result.null': 'NULL',
  'result.page': '第 {current} / {total} 页',
  'result.prev': '上一页',
  'result.next': '下一页',
  'result.pageSize': '{size} 条/页',
  'result.limitedWarning': '仅显示前 {count} 行，更多数据请刷新后查看',

  // Schema
  'schema.title': 'Schema 浏览',
  'schema.loading': '加载中...',
  'schema.noData': '暂无数据源 Schema',
  'schema.noTables': '暂无表',
  'schema.columns': '列',

  // Datasource
  'datasource.loading': '加载中...',
  'datasource.noData': '暂无数据源',
  'datasource.select': '选择数据源',

  // Clarification
  'clarification.needConfirm': '需要向您确认几个问题',
  'clarification.resolved': '已澄清',
  'clarification.hint': '请在下方输入框中回复你的想法，我会根据你的回答继续查询。',

  // Language
  'lang.zh': '简体中文',
  'lang.en': 'English',
  'lang.switch': '切换语言',

  // Sample questions (empty state)
  'samples.totalUsers': '查询总用户数',
  'samples.dau7d': '最近 7 天的日活',
  'samples.top10Orders': '订单金额排名 top10',
  'samples.deptHeadcount': '各部门人数统计',

  // Time
  'time.justNow': '刚刚',
  'time.minutesAgo': '{n} 分钟前',
  'time.hoursAgo': '{n} 小时前',
  'time.daysAgo': '{n} 天前',
  'time.yesterday': '昨天',
} as const

export type TranslationKey = keyof typeof zhCN
