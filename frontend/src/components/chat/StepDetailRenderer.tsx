/**
 * 步骤详情渲染器
 * 根据不同 step 类型，用不同方式渲染详情内容
 */
import { SqlDisplay } from './SqlDisplay'
import type { ThinkingStep } from '../../lib/types'
import { Copy, Check } from 'lucide-react'
import { useState } from 'react'

interface StepDetailRendererProps {
  step: ThinkingStep
}

// 通用的键值对行
function KVRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 text-xs py-1">
      <span className="text-gray-400 shrink-0 min-w-[60px]">{label}</span>
      <span className="text-gray-700 flex-1 break-all">{value}</span>
    </div>
  )
}

// 表名 tag 列表
function TagList({ items }: { items: string[] }) {
  if (!items?.length) return <span className="text-gray-400 text-xs">无</span>
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item, i) => (
        <span
          key={i}
          className="px-2 py-0.5 bg-indigo-50 text-indigo-600 text-xs rounded-md font-mono"
        >
          {item}
        </span>
      ))}
    </div>
  )
}

// 置信度进度条
function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color =
    pct >= 80 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-500 font-medium w-10 text-right">{pct}%</span>
    </div>
  )
}

// 复制按钮
function CopyText({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // ignore
    }
  }
  return (
    <button
      onClick={handleCopy}
      className="p-1 text-gray-400 hover:text-gray-600 transition-colors"
      title="复制"
    >
      {copied ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
    </button>
  )
}

function DispatchDetail({ detail }: { detail: Record<string, unknown> }) {
  const intent = (detail.intent as string) || ''
  const confidence = (detail.confidence as number) || 0
  const reasoning = (detail.reasoning as string) || ''

  const intentLabel: Record<string, string> = {
    query: '数据查询',
    schema_exploration: 'Schema 探索',
    connect_datasource: '数据源接入',
    chitchat: '闲聊',
  }

  return (
    <div className="space-y-2">
      <KVRow
        label="任务类型"
        value={
          <span className="px-2 py-0.5 bg-indigo-50 text-indigo-600 text-xs rounded-md font-medium">
            {intentLabel[intent] || intent}
          </span>
        }
      />
      <div>
        <div className="text-xs text-gray-400 mb-1">置信度</div>
        <ConfidenceBar value={confidence} />
      </div>
      {reasoning && (
        <div>
          <div className="text-xs text-gray-400 mb-1">判断理由</div>
          <div className="text-xs text-gray-600 bg-gray-50 px-3 py-2 rounded-md leading-relaxed">
            {reasoning}
          </div>
        </div>
      )}
    </div>
  )
}

function IntentDetail({ detail }: { detail: Record<string, unknown> }) {
  const tables = (detail.tables as string[]) || []
  const action = (detail.action as string) || 'query'
  const aggregation = (detail.aggregation as string) || null
  const dimensions = (detail.dimensions as string[]) || []
  const ambiguities = (detail.ambiguities as string[]) || []
  const confidence = (detail.confidence as number) || 0

  return (
    <div className="space-y-1.5">
      <KVRow label="意图类型" value={action === 'query' ? '数据查询' : action} />
      {tables.length > 0 && <KVRow label="涉及表" value={<TagList items={tables} />} />}
      {aggregation && <KVRow label="聚合方式" value={<span className="font-mono">{aggregation}</span>} />}
      {dimensions.length > 0 && <KVRow label="维度" value={<TagList items={dimensions} />} />}
      {ambiguities.length > 0 && (
        <div className="pt-1">
          <div className="text-xs text-gray-400 mb-1">歧义点（{ambiguities.length}）</div>
          <ul className="space-y-0.5">
            {ambiguities.map((a, i) => (
              <li key={i} className="text-xs text-amber-700 flex items-start gap-1.5">
                <span className="text-amber-500">•</span>
                <span>{a}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="pt-1.5">
        <div className="text-xs text-gray-400 mb-1">置信度</div>
        <ConfidenceBar value={confidence} />
      </div>
    </div>
  )
}

function ProbeDetail({ detail }: { detail: Record<string, unknown> }) {
  const probedTables = (detail.probed_tables as string[]) || []
  const findings = (detail.findings as string[]) || []
  const skipped = detail.skipped as boolean
  const reason = detail.reason as string

  if (skipped) {
    return <div className="text-xs text-gray-400">跳过：{reason}</div>
  }

  return (
    <div className="space-y-2">
      {probedTables.length > 0 && <KVRow label="探查表" value={<TagList items={probedTables} />} />}
      {findings.length > 0 && (
        <div>
          <div className="text-xs text-gray-400 mb-1">发现（{findings.length}）</div>
          <ul className="space-y-1">
            {findings.map((f, i) => (
              <li
                key={i}
                className="text-xs text-gray-600 bg-gray-50 px-2 py-1.5 rounded-md break-all"
              >
                {f}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function ClarifyDetail({ detail }: { detail: Record<string, unknown> }) {
  const needsClarification = detail.needs_clarification as boolean
  const questions = (detail.questions as string[]) || []

  if (!needsClarification) {
    return <div className="text-xs text-emerald-600">✓ 无需澄清，直接进入 SQL 生成</div>
  }

  return (
    <div>
      <div className="text-xs text-gray-400 mb-1.5">需要澄清的问题（{questions.length}）</div>
      <ol className="space-y-1 list-decimal list-inside">
        {questions.map((q, i) => (
          <li key={i} className="text-xs text-gray-600 pl-1">
            {q}
          </li>
        ))}
      </ol>
    </div>
  )
}

function SqlGeneratedDetail({ detail }: { detail: Record<string, unknown> }) {
  const sql = (detail.sql as string) || ''
  const iteration = (detail.iteration as number) || 1

  return (
    <div className="space-y-2">
      {iteration > 1 && (
        <div className="text-xs text-amber-600">
          第 {iteration} 轮生成（修正中）
        </div>
      )}
      <div className="relative">
        <div className="absolute top-2 right-2 z-10">
          <CopyText text={sql} />
        </div>
        <SqlDisplay sql={sql} compact />
      </div>
    </div>
  )
}

function SqlExecutedDetail({ detail }: { detail: Record<string, unknown> }) {
  const success = detail.success as boolean
  const rowCount = detail.row_count as number
  const durationMs = detail.duration_ms as number
  const columns = (detail.columns as string[]) || []

  if (!success) {
    return (
      <div className="text-xs text-red-600 bg-red-50 px-3 py-2 rounded-md">
        ✗ 执行失败
      </div>
    )
  }

  return (
    <div className="space-y-1.5">
      <KVRow label="状态" value={<span className="text-emerald-600 font-medium">✓ 执行成功</span>} />
      <KVRow label="返回行数" value={<span className="font-mono">{rowCount} 行</span>} />
      {typeof durationMs === 'number' && (
        <KVRow label="耗时" value={<span className="font-mono">{durationMs} ms</span>} />
      )}
      {columns.length > 0 && (
        <div>
          <div className="text-xs text-gray-400 mb-1">列名（{columns.length}）</div>
          <TagList items={columns} />
        </div>
      )}
    </div>
  )
}

function ReflectDetail({ detail }: { detail: Record<string, unknown> }) {
  const satisfied = detail.satisfied as boolean
  const needsRevision = detail.needs_revision as boolean
  const thought = (detail.thought as string) || ''
  const suggestedFix = (detail.suggested_fix as string) || ''
  const iteration = (detail.iteration as number) || 1

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        {satisfied ? (
          <span className="px-2 py-0.5 bg-emerald-50 text-emerald-600 text-xs rounded-md font-medium">
            ✓ 结果满意
          </span>
        ) : (
          <span className="px-2 py-0.5 bg-amber-50 text-amber-600 text-xs rounded-md font-medium">
            结果不满意
          </span>
        )}
        {needsRevision && (
          <span className="px-2 py-0.5 bg-red-50 text-red-600 text-xs rounded-md font-medium">
            需要修正
          </span>
        )}
        {iteration > 1 && (
          <span className="text-xs text-gray-400">第 {iteration} 轮</span>
        )}
      </div>
      {thought && (
        <div className="text-xs text-gray-600 bg-gray-50 px-3 py-2 rounded-md leading-relaxed">
          {thought}
        </div>
      )}
      {suggestedFix && needsRevision && (
        <div>
          <div className="text-xs text-gray-400 mb-1">修正建议</div>
          <div className="text-xs text-amber-700 bg-amber-50 px-3 py-2 rounded-md">
            {suggestedFix}
          </div>
        </div>
      )}
    </div>
  )
}

function VisualizeDetail({ detail }: { detail: Record<string, unknown> }) {
  const chartCount = (detail.chart_count as number) || 0
  const chartTypes = (detail.chart_types as string[]) || []
  const titles = (detail.titles as string[]) || []
  const note = detail.note as string | undefined
  const skipped = detail.skipped as boolean
  const reason = detail.reason as string

  if (skipped) {
    return <div className="text-xs text-gray-400">跳过：{reason}</div>
  }

  if (note) {
    return (
      <div className="text-xs text-amber-600">
        图表生成结果：{note}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <KVRow label="图表数量" value={<span className="font-medium">{chartCount} 个</span>} />
      {titles.length > 0 && (
        <div>
          <div className="text-xs text-gray-400 mb-1">图表列表</div>
          <ul className="space-y-1">
            {titles.map((title, i) => (
              <li
                key={i}
                className="text-xs text-gray-600 flex items-center gap-2 bg-gray-50 px-2 py-1.5 rounded-md"
              >
                <span className="w-5 h-5 rounded bg-indigo-100 text-indigo-600 flex items-center justify-center text-[10px] font-medium">
                  {chartTypes[i]?.charAt(0).toUpperCase() || '?'}
                </span>
                <span className="flex-1 truncate">{title}</span>
                <span className="text-gray-400 text-[10px]">{chartTypes[i] || ''}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function SummarizeDetail({ detail }: { detail: Record<string, unknown> }) {
  const answerLength = (detail.answer_length as number) || 0
  const status = (detail.status as string) || 'done'
  const rowCount = detail.row_count as number | undefined

  return (
    <div className="space-y-1.5">
      <KVRow
        label="状态"
        value={
          status === 'done' ? (
            <span className="text-emerald-600 font-medium">✓ 完成</span>
          ) : (
            <span className="text-red-500 font-medium">✗ 失败</span>
          )
        }
      />
      <KVRow label="回答长度" value={<span className="font-mono">{answerLength} 字</span>} />
      {typeof rowCount === 'number' && (
        <KVRow label="数据行数" value={<span className="font-mono">{rowCount} 行</span>} />
      )}
    </div>
  )
}

// 通用 JSON 详情（兜底）
function GenericDetail({ detail }: { detail: Record<string, unknown> }) {
  const jsonStr = JSON.stringify(detail, null, 2)
  return (
    <div className="relative">
      <div className="absolute top-2 right-2 z-10">
        <CopyText text={jsonStr} />
      </div>
      <pre className="text-[11px] text-gray-600 bg-gray-50 p-3 rounded-md overflow-x-auto font-mono max-h-48 overflow-y-auto">
        {jsonStr}
      </pre>
    </div>
  )
}

export function StepDetailRenderer({ step }: StepDetailRendererProps) {
  const { step: stepKey, status, detail, error_message } = step

  if (status === 'error' && error_message) {
    return (
      <div className="text-xs text-red-600 bg-red-50 px-3 py-2 rounded-md break-all">
        ✗ {error_message}
      </div>
    )
  }

  if (!detail) return null

  switch (stepKey) {
    case 'dispatch':
      return <DispatchDetail detail={detail} />
    case 'intent_analysis':
      return <IntentDetail detail={detail} />
    case 'intent_probe':
      return <ProbeDetail detail={detail} />
    case 'clarify':
      return <ClarifyDetail detail={detail} />
    case 'sql_generated':
      return <SqlGeneratedDetail detail={detail} />
    case 'sql_executed':
      return <SqlExecutedDetail detail={detail} />
    case 'reflection':
      return <ReflectDetail detail={detail} />
    case 'visualize':
      return <VisualizeDetail detail={detail} />
    case 'summarize':
      return <SummarizeDetail detail={detail} />
    default:
      return <GenericDetail detail={detail} />
  }
}
