# NL2SQL 前端玻璃质感重设计 + i18n 实施计划

> 日期：2026-08-23
> 状态：待审核
> 选择方案：玻璃质感（Depth Glass · 现代玻璃拟态）

---

## 一、设计方向

### 设计理念
通透、层次、灵动 — 像 Apple Vision Pro 界面一样的现代玻璃拟态风格。

### 核心设计 Token

| 类别 | 值 | 用途 |
|---|---|---|
| **背景** | `bg-gradient-to-br from-[#F0F4FF] via-[#F8FAFC] to-[#FDF2F8]` | 页面整体渐变背景 |
| **玻璃表面** | `bg-white/70-90 backdrop-blur-xl` | 卡片、面板、侧边栏 |
| **主色渐变** | `from-[#6366F1] to-[#8B5CF6]` | 按钮、用户气泡、强调元素 |
| **主色浅底** | `from-[#6366F1]/10 to-[#8B5CF6]/10` | Avatar 背景、标签底色 |
| **主色文字** | `text-[#6366F1]` | 链接、强调文字 |
| **边框** | `border-white/60` | 玻璃卡片边框 |
| **主文字** | `text-[#0F172A]` | 标题、主要内容 |
| **次文字** | `text-[#475569]` | 正文、标签 |
| **弱文字** | `text-[#94A3B8]` | 时间戳、辅助信息 |
| **代码背景** | `bg-gradient-to-b from-[#1E1B4B] to-[#0F172A]` | SQL 代码块 |
| **圆角小** | `rounded-2xl`（16px）| 按钮、输入框 |
| **圆角大** | `rounded-3xl`（24px）| 卡片、面板 |
| **阴影** | `shadow-xl shadow-[#152238]/5` | 玻璃卡片悬浮感 |
| **字体** | `Inter` + `JetBrains Mono` | 正文 + 代码 |

### 签名元素
- 淡紫蓝粉渐变背景
- 毛玻璃模糊效果（backdrop-blur-xl）
- 紫蓝渐变主按钮
- 大圆角 + 柔和多层阴影

---

## 二、实施范围与优先级

### P0 — 核心设计系统（必须先做）

| # | 文件 | 改动内容 |
|---|---|---|
| 1 | `tailwind.config.js` | 扩展主题：自定义颜色 palette、字体、圆角、阴影、动画 |
| 2 | `src/index.css` | 全局样式：Inter/JetBrains Mono 字体引入、背景渐变、滚动条美化、动画关键帧、CSS 变量 |

### P1 — 主要界面组件

| # | 文件 | 改动内容 |
|---|---|---|
| 3 | `components/layout/AppLayout.tsx` | Header 玻璃模糊效果、整体渐变背景容器、Schema 按钮玻璃态 |
| 4 | `components/layout/Sidebar.tsx` | 玻璃磨砂侧边栏、渐变新建会话按钮、会话项 hover/active 玻璃态 |
| 5 | `components/chat/ChatPanel.tsx` | 空状态玻璃卡片、会话标题栏玻璃态 |
| 6 | `components/chat/ChatInput.tsx` | 输入框玻璃效果、大圆角、渐变发送按钮、focus 发光效果 |
| 7 | `components/chat/ChatMessage.tsx` | 用户气泡渐变、助手气泡玻璃态、头像渐变背景 |
| 8 | `components/chat/ThinkingTimeline.tsx` | 思考卡片玻璃质感、步骤图标配色 |
| 9 | `components/chat/SqlDisplay.tsx` | 紫蓝渐变深色代码块、玻璃 header |
| 10 | `components/chat/ResultTable.tsx` | 表格玻璃表面、斑马纹半透明、表头毛玻璃 |
| 11 | `components/schema/SchemaPanel.tsx` | Schema 面板玻璃态、树状结构配色调整 |

### P2 — 图表与细节优化

| # | 文件 | 改动内容 |
|---|---|---|
| 12 | `components/chart/chartUtils.ts` | 图表配色更新为紫蓝渐变色系（8 色板） |
| 13 | `components/chart/MetricCard.tsx` | 指标卡玻璃态 + 渐变背景 |
| 14 | `components/chart/BarChartView.tsx` 等 | 图表样式微调（圆角、透明度） |
| 15 | `components/chat/ClarificationCard.tsx` | 澄清卡片玻璃态、琥珀色玻璃质感 |
| 16 | `components/chat/DatasourceSelector.tsx` | 数据源选择器玻璃态 |
| 17 | `components/chat/StepDetailRenderer.tsx` | 步骤详情玻璃态调整 |

### P3 — 国际化 + 品牌改名

#### 3.1 项目改名 AskSql

| # | 文件 | 改动内容 |
|---|---|---|
| 18 | `index.html` | `<title>` 和 `<h1>` 改为 AskSql，favicon 暂保留 |
| 19 | `components/layout/AppLayout.tsx` | Logo 文字改为 AskSql |
| 20 | `package.json` | name 字段改为 `asksql-frontend`（可选，建议改） |
| 21 | `README.md` / `README.zh-CN.md` | 项目名称更新（仅前端涉及部分） |

#### 3.2 中英文切换（i18n）

| # | 文件 | 改动内容 |
|---|---|---|
| 22 | `src/i18n/index.ts` | 新建 i18n 配置（轻量方案：Context + useTranslation hook，不引入 i18next 等第三方库） |
| 23 | `src/i18n/locales/zh-CN.ts` | 中文翻译文件 |
| 24 | `src/i18n/locales/en.ts` | 英文翻译文件 |
| 25 | `src/hooks/useTranslation.ts` | 翻译 hook |
| 26 | `components/layout/AppLayout.tsx` | Header 中添加语言切换按钮（🌐 图标下拉） |
| 27 | 所有含中文字符的组件 | 替换为 `t('key')` 翻译调用 |

**i18n 技术方案选择**：自实现轻量方案（Context + hook + 翻译文件），不引入 `react-i18next` 等重依赖。理由：
- 项目体量小，目前只有中文，未来主要是中英双语
- 自实现代码量 < 100 行，零依赖
- 支持 localStorage 持久化语言偏好
- 如需未来扩展多语言，可平滑迁移

**受影响组件清单**（需要替换文案）：
- `App.tsx` — 加载中/错误/空状态
- `AppLayout.tsx` — Schema 按钮、项目名
- `Sidebar.tsx` — 新建会话、加载中、暂无会话
- `ChatPanel.tsx` — 空状态提示、示例问题、错误前缀
- `ChatInput.tsx` — placeholder、快捷键提示
- `ChatMessage.tsx` — 你/助手
- `ThinkingTimeline.tsx` — 思考中/思考过程、收起、已用时间
- `SqlDisplay.tsx` — SQL/复制/已复制
- `ResultTable.tsx` — 查询结果、共 N 行、加载中、分页文案、条数选择
- `SchemaPanel.tsx` — Schema 浏览、加载中、暂无
- `ClarificationCard.tsx` — 澄清相关文案
- `DatasourceSelector.tsx` — 选择数据源相关文案

**共计约 12-15 个组件需要替换文案**，预计翻译条目 60-80 条。

---

## 三、不改动的部分

- 业务逻辑（hooks、api、types）— 仅改样式和文案
- 后端代码 — 纯前端改动
- 数据结构和 API 契约 — 保持不变
- 图表库选择（Recharts）— 仅改配色

---

## 四、实施顺序

```
P0 设计系统 → P1 核心组件 → P2 图表细节 → P3 改名 + i18n
```

每个阶段完成后可以进行一次验收。

---

## 五、验证方式

1. 启动 `npm run dev` 查看实际效果
2. 检查所有主要页面：空状态、对话中、思考中、SQL 展示、结果表格、Schema 面板
3. 中英文切换功能验证：刷新后语言偏好保留
4. 响应式检查：桌面端正常显示

---

## 六、风险与注意事项

| 风险 | 应对 |
|---|---|
| backdrop-blur 在某些浏览器性能问题 | 降级为半透明白色，现代浏览器均支持 |
| 渐变背景在低端设备卡顿 | 使用静态背景替代，或减少渐变复杂度 |
| i18n 遗漏部分文案 | 实施后进行全文案检查，中英对照验证 |
| 改名影响外部引用 | 先改前端显示层，package.json 等标识性改动单独确认 |
