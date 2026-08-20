/**
 * 查询结果表格
 * 使用 @tanstack/react-table，支持服务端分页
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from '@tanstack/react-table'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { QueryResult } from '../../lib/types'
import { getResultPage } from '../../lib/api'

interface ResultTableProps {
  result: QueryResult
  messageId?: string
  defaultPageSize?: number
}

const PREVIEW_ROWS = 100

export function ResultTable({ result, messageId, defaultPageSize = 100 }: ResultTableProps) {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(defaultPageSize)
  const [pageData, setPageData] = useState<unknown[][]>(
    result.rows.slice(0, Math.min(PREVIEW_ROWS, pageSize)),
  )
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(result.row_count)

  useEffect(() => {
    setPage(1)
    setPageData(result.rows.slice(0, Math.min(PREVIEW_ROWS, pageSize)))
    setTotal(result.row_count)
  }, [result, pageSize])

  const loadPage = useCallback(
    async (targetPage: number) => {
      // 如果没有 messageId，只能前端切片
      if (!messageId) {
        const allRows = result.rows
        const start = (targetPage - 1) * pageSize
        const end = start + pageSize
        setPageData(allRows.slice(start, end))
        setPage(targetPage)
        return
      }
      // 第一页且数据量小，直接用已有的
      if (targetPage === 1 && result.row_count <= PREVIEW_ROWS) {
        setPageData(result.rows)
        setPage(1)
        return
      }
      setLoading(true)
      try {
        const res = await getResultPage(messageId, targetPage, pageSize)
        setPageData(res.rows)
        setTotal(res.total)
        setPage(targetPage)
      } catch {
        // 失败保留当前页
      } finally {
        setLoading(false)
      }
    },
    [messageId, pageSize, result],
  )

  const data = useMemo(() => {
    return pageData.map((row, idx) => {
      const obj: Record<string, unknown> = {
        __index: (page - 1) * pageSize + idx + 1,
      }
      result.columns.forEach((col, i) => {
        obj[col] = row[i]
      })
      return obj
    })
  }, [pageData, result.columns, page, pageSize])

  const columnHelper = createColumnHelper<Record<string, unknown>>()

  const columns = useMemo(() => {
    return [
      columnHelper.display({
        id: 'index',
        header: '#',
        cell: (info) => info.row.original.__index,
        size: 50,
      }),
      ...result.columns.map((col) =>
        columnHelper.accessor(col, {
          header: col,
          cell: (info) => {
            const val = info.getValue()
            if (val === null || val === undefined) {
              return <span className="text-gray-400">NULL</span>
            }
            if (typeof val === 'object') {
              return JSON.stringify(val)
            }
            return String(val)
          },
        }),
      ),
    ]
  }, [result.columns, columnHelper])

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    enableColumnResizing: true,
  })

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const canPrev = page > 1
  const canNext = page < totalPages
  const showPagination = total > pageSize

  const showLimitedWarning =
    !messageId && result.row_count > PREVIEW_ROWS && result.rows.length <= PREVIEW_ROWS

  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
      <div className="px-3 py-1.5 bg-gray-50 border-b border-gray-200 flex items-center justify-between text-xs">
        <span className="text-gray-600 font-medium">查询结果</span>
        <span className="text-gray-400">
          共 {total.toLocaleString()} 行
          {result.duration_ms !== undefined &&
            ` · ${result.duration_ms}ms`}
        </span>
      </div>

      <div className="overflow-x-auto max-h-80 overflow-y-auto">
        {loading ? (
          <div className="h-40 flex items-center justify-center text-gray-400 text-sm">
            加载中...
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 sticky top-0 z-10">
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th
                      key={header.id}
                      className="px-3 py-2 text-left text-xs font-medium text-gray-600 border-b border-gray-200 whitespace-nowrap"
                      style={{ width: header.getSize() }}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row, rowIdx) => (
                <tr
                  key={row.id}
                  className={
                    rowIdx % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'
                  }
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className="px-3 py-1.5 text-gray-700 border-b border-gray-100 font-mono text-xs"
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showLimitedWarning && (
        <div className="px-3 py-2 bg-amber-50 border-t border-amber-100 text-xs text-amber-700">
          仅显示前 {PREVIEW_ROWS} 行，更多数据请刷新后查看
        </div>
      )}

      {showPagination && (
        <div className="px-3 py-2 bg-gray-50 border-t border-gray-200 flex items-center justify-between text-xs">
          <div className="text-gray-500">
            第 {page} / {totalPages} 页
          </div>
          <div className="flex items-center gap-1">
            <button
              className="px-2 py-1 rounded border border-gray-300 text-gray-600 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-white transition-colors"
              onClick={() => loadPage(page - 1)}
              disabled={!canPrev || loading}
            >
              <ChevronLeft size={14} />
            </button>
            <select
              className="px-2 py-1 rounded border border-gray-300 text-gray-600 bg-white"
              value={pageSize}
              onChange={(e) => {
                const newSize = Number(e.target.value)
                setPageSize(newSize)
                setPage(1)
              }}
            >
              <option value={50}>50 条/页</option>
              <option value={100}>100 条/页</option>
              <option value={200}>200 条/页</option>
              <option value={500}>500 条/页</option>
            </select>
            <button
              className="px-2 py-1 rounded border border-gray-300 text-gray-600 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-white transition-colors"
              onClick={() => loadPage(page + 1)}
              disabled={!canNext || loading}
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
