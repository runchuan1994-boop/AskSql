/**
 * 查询结果表格
 * 使用 @tanstack/react-table
 */
import { useMemo } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from '@tanstack/react-table'
import type { QueryResult } from '../../lib/types'

interface ResultTableProps {
  result: QueryResult
  maxRows?: number
}

export function ResultTable({ result, maxRows = 100 }: ResultTableProps) {
  const data = useMemo(() => {
    const rows = result.rows.slice(0, maxRows).map((row, idx) => {
      const obj: Record<string, unknown> = { __index: idx + 1 }
      result.columns.forEach((col, i) => {
        obj[col] = row[i]
      })
      return obj
    })
    return rows
  }, [result, maxRows])

  const columnHelper = createColumnHelper<Record<string, unknown>>()

  const columns = useMemo(() => {
    return [
      columnHelper.display({
        id: 'index',
        header: '#',
        cell: (info) => info.row.original.__index,
        size: 40,
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

  const truncated = result.rows.length > maxRows || result.truncated

  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
      <div className="px-3 py-1.5 bg-gray-50 border-b border-gray-200 flex items-center justify-between text-xs">
        <span className="text-gray-600 font-medium">查询结果</span>
        <span className="text-gray-400">
          共 {result.row_count} 行
          {truncated && `（仅显示前 ${maxRows} 行）`}
          {result.duration_ms !== undefined &&
            ` · ${result.duration_ms}ms`}
        </span>
      </div>
      <div className="overflow-x-auto max-h-80 overflow-y-auto">
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
      </div>
    </div>
  )
}
