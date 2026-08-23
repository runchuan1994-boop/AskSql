/**
 * Schema 记忆管理面板
 *
 * 展示和管理数据源的用户纠错记忆
 */
import { useEffect, useState } from 'react'
import { Plus, Search, Trash2, Edit2, X, Lightbulb, BookOpen, Hash, Link2, BarChart3 } from 'lucide-react'
import { listMemories, createMemory, updateMemory, deleteMemory } from '../../lib/api'
import type { SchemaMemory, MemoryType, EntityType } from '../../lib/types'
import { clsx } from '../../lib/utils'
import { useTranslation } from '../../i18n'

interface MemoryPanelProps {
  datasourceId: string
  tableNames: string[]
}

const MEMORY_TYPE_OPTIONS: { value: MemoryType; label: string; icon: typeof Lightbulb }[] = [
  { value: 'column_description', label: '列描述', icon: Hash },
  { value: 'table_description', label: '表描述', icon: BookOpen },
  { value: 'metric_definition', label: '指标定义', icon: BarChart3 },
  { value: 'term_mapping', label: '术语映射', icon: Lightbulb },
  { value: 'join_hint', label: '关联提示', icon: Link2 },
]

const ENTITY_TYPE_MAP: Record<MemoryType, EntityType | ''> = {
  column_description: 'column',
  table_description: 'table',
  metric_definition: 'metric',
  term_mapping: 'term',
  join_hint: 'table',
}

export function MemoryPanel({ datasourceId, tableNames }: MemoryPanelProps) {
  const { t } = useTranslation()
  const [memories, setMemories] = useState<SchemaMemory[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const pageSize = 20
  const [filter, setFilter] = useState<MemoryType | ''>('')
  const [search, setSearch] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const loadMemories = async () => {
    if (!datasourceId) return
    setLoading(true)
    try {
      const result = await listMemories(datasourceId, {
        memory_type: filter || undefined,
        search: search || undefined,
        page,
        page_size: pageSize,
      })
      setMemories(result.items)
      setTotal(result.total)
    } catch (err) {
      console.error('Failed to load memories:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadMemories()
  }, [datasourceId, page, filter, search])

  const handleDelete = async (id: string) => {
    if (!confirm('确定删除这条记忆吗？')) return
    try {
      await deleteMemory(id)
      loadMemories()
    } catch (err) {
      console.error('Failed to delete memory:', err)
    }
  }

  const handleSave = async (data: {
    memory_type: MemoryType
    entity_name?: string
    content: string
  }) => {
    try {
      await createMemory({
        datasource_id: datasourceId,
        memory_type: data.memory_type,
        entity_type: ENTITY_TYPE_MAP[data.memory_type] || undefined,
        entity_name: data.entity_name,
        content: data.content,
      })
      setShowAddForm(false)
      loadMemories()
    } catch (err) {
      console.error('Failed to create memory:', err)
    }
  }

  const handleUpdate = async (id: string, content: string) => {
    try {
      await updateMemory(id, { content })
      setEditingId(null)
      loadMemories()
    } catch (err) {
      console.error('Failed to update memory:', err)
    }
  }

  const typeLabel = (type: string) =>
    MEMORY_TYPE_OPTIONS.find((o) => o.value === type)?.label || type

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="h-full flex flex-col">
      {/* 顶部操作栏 */}
      <div className="px-3 py-2.5 border-b border-white/30 bg-white/50 backdrop-blur flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
          <Lightbulb size={14} className="text-amber-500" />
          {t('schema.memories')}
        </h3>
        <button
          onClick={() => setShowAddForm(true)}
          className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-white bg-brand-500 hover:bg-brand-600 rounded-lg transition-colors"
        >
          <Plus size={12} />
          {t('schema.addMemory')}
        </button>
      </div>

      {/* 筛选和搜索 */}
      <div className="p-3 border-b border-white/20 space-y-2">
        <div className="flex gap-2">
          <select
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value as MemoryType | '')
              setPage(1)
            }}
            className="flex-1 px-2 py-1.5 text-xs border border-white/40 bg-white/60 rounded-lg text-slate-700 focus:outline-none focus:ring-1 focus:ring-brand-400"
          >
            <option value="">全部类型</option>
            {MEMORY_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div className="relative">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder={t('schema.searchMemories')}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
            }}
            className="w-full pl-8 pr-3 py-1.5 text-xs border border-white/40 bg-white/60 rounded-lg text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-brand-400"
          />
        </div>
      </div>

      {/* 记忆列表 */}
      <div className="flex-1 overflow-y-auto p-3">
        {loading ? (
          <div className="text-center py-8 text-xs text-slate-400">加载中...</div>
        ) : memories.length === 0 ? (
          <div className="text-center py-8 text-xs text-slate-400">
            <Lightbulb size={24} className="mx-auto mb-2 text-slate-300" />
            暂无记忆记录
            <div className="mt-1 text-[10px] text-slate-300">
              添加手动记忆，或在对话中纠正时自动生成
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            {memories.map((mem) => (
              <div
                key={mem.id}
                className="p-3 border border-white/40 bg-white/60 backdrop-blur-sm rounded-xl shadow-sm"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 text-[10px] text-slate-500 mb-1 flex-wrap">
                      <span
                        className={clsx(
                          'px-1.5 py-0.5 rounded-md font-medium',
                          mem.source === 'manual_add'
                            ? 'bg-emerald-500/10 text-emerald-600'
                            : 'bg-amber-500/10 text-amber-600',
                        )}
                      >
                        {typeLabel(mem.memory_type)}
                      </span>
                      {mem.entity_name && (
                        <span className="font-mono bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">
                          {mem.entity_name}
                        </span>
                      )}
                      <span className="text-slate-400">
                        {mem.created_at?.split('T')[0] || mem.created_at?.split(' ')[0]}
                      </span>
                      <span className="text-slate-400">访问 {mem.access_count} 次</span>
                    </div>
                    {editingId === mem.id ? (
                      <div className="space-y-1.5">
                        <textarea
                          defaultValue={mem.content}
                          id={`edit-${mem.id}`}
                          className="w-full px-2 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-brand-400"
                          rows={2}
                        />
                        <div className="flex gap-2">
                          <button
                            onClick={() => {
                              const el = document.getElementById(
                                `edit-${mem.id}`,
                              ) as HTMLTextAreaElement
                              if (el) handleUpdate(mem.id, el.value)
                            }}
                            className="px-2 py-1 text-[10px] font-medium text-white bg-brand-500 hover:bg-brand-600 rounded-md"
                          >
                            保存
                          </button>
                          <button
                            onClick={() => setEditingId(null)}
                            className="px-2 py-1 text-[10px] text-slate-500 hover:text-slate-700 border border-slate-200 rounded-md"
                          >
                            取消
                          </button>
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-slate-700 leading-relaxed">{mem.content}</p>
                    )}
                  </div>
                  <div className="flex gap-0.5 shrink-0">
                    <button
                      onClick={() => setEditingId(mem.id)}
                      className="p-1 text-slate-400 hover:text-brand-500 hover:bg-brand-50 rounded transition-colors"
                      title="编辑"
                    >
                      <Edit2 size={12} />
                    </button>
                    <button
                      onClick={() => handleDelete(mem.id)}
                      className="p-1 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors"
                      title="删除"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="px-3 py-2 border-t border-white/20 flex items-center justify-between text-xs text-slate-500">
          <button
            disabled={page === 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="px-2 py-1 border border-white/40 rounded-md disabled:opacity-40 hover:bg-white/60 transition-colors"
          >
            上一页
          </button>
          <span>
            {page} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            className="px-2 py-1 border border-white/40 rounded-md disabled:opacity-40 hover:bg-white/60 transition-colors"
          >
            下一页
          </button>
        </div>
      )}

      {/* 添加记忆弹窗 */}
      {showAddForm && (
        <AddMemoryModal
          tableNames={tableNames}
          onSave={handleSave}
          onCancel={() => setShowAddForm(false)}
        />
      )}
    </div>
  )
}

// ---------- 添加记忆弹窗 ----------

function AddMemoryModal({
  tableNames,
  onSave,
  onCancel,
}: {
  tableNames: string[]
  onSave: (data: { memory_type: MemoryType; entity_name?: string; content: string }) => void
  onCancel: () => void
}) {
  const [memoryType, setMemoryType] = useState<MemoryType>('column_description')
  const [entityName, setEntityName] = useState('')
  const [content, setContent] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!content.trim()) return
    onSave({
      memory_type: memoryType,
      entity_name: entityName.trim() || undefined,
      content: content.trim(),
    })
  }

  const needsTable = memoryType === 'table_description' || memoryType === 'join_hint'
  const needsColumn = memoryType === 'column_description'
  const needsTerm = memoryType === 'term_mapping' || memoryType === 'metric_definition'

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white/95 backdrop-blur rounded-2xl shadow-2xl w-full max-w-sm p-5 border border-white/50">
        <div className="flex items-center justify-between mb-4">
          <h4 className="text-sm font-semibold text-slate-800">添加记忆</h4>
          <button
            onClick={onCancel}
            className="p-1 text-slate-400 hover:text-slate-600 rounded-md hover:bg-slate-100"
          >
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">记忆类型</label>
            <select
              value={memoryType}
              onChange={(e) => setMemoryType(e.target.value as MemoryType)}
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-400/50 focus:border-brand-400"
            >
              {MEMORY_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {needsTable && (
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">关联表</label>
              <select
                value={entityName}
                onChange={(e) => setEntityName(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-400/50 focus:border-brand-400"
              >
                <option value="">请选择表</option>
                {tableNames.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {needsColumn && (
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">
                列名（格式：表名.列名）
              </label>
              <input
                type="text"
                value={entityName}
                onChange={(e) => setEntityName(e.target.value)}
                placeholder="orders.total_amount"
                className="w-full px-3 py-2 text-sm font-mono border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-400/50 focus:border-brand-400"
              />
            </div>
          )}

          {needsTerm && (
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">
                {memoryType === 'metric_definition' ? '指标名称' : '术语名称'}
              </label>
              <input
                type="text"
                value={entityName}
                onChange={(e) => setEntityName(e.target.value)}
                placeholder={memoryType === 'metric_definition' ? '如：GMV、转化率' : '如：流水、客单价'}
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-400/50 focus:border-brand-400"
              />
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">记忆内容</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="描述这条记忆的内容..."
              rows={3}
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-400/50 focus:border-brand-400 resize-none"
              required
            />
          </div>

          <div className="flex gap-2 justify-end pt-1">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
            >
              取消
            </button>
            <button
              type="submit"
              className="px-4 py-2 text-sm font-medium text-white bg-brand-500 hover:bg-brand-600 rounded-lg transition-colors"
            >
              添加
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
