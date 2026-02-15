import {
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table"
import type { SearchResult, PaginationMetadata } from "@/types/search"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { columns } from "./columns"

interface DataTableViewProps {
  results: SearchResult[]
  pagination: PaginationMetadata | null
  onPageChange: (page: number) => void
  pageSize: number
  onPageSizeChange: (size: number) => void
  isLoading?: boolean
}

export function DataTableView({
  results,
  pagination,
  onPageChange,
  pageSize,
  onPageSizeChange,
  isLoading = false,
}: DataTableViewProps) {
  const table = useReactTable({
    data: results,
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,  // Server-side pagination
    pageCount: pagination?.total_pages ?? 0,
  })

  return (
    <div className="space-y-4">
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center">
                  {isLoading ? "Loading..." : "No results."}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {pagination && (
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between px-2">
          <div className="flex items-center gap-4 text-sm">
            <div className="text-muted-foreground">
              Showing {((pagination.page - 1) * pagination.page_size) + 1} to{" "}
              {Math.min(pagination.page * pagination.page_size, pagination.total_results)} of{" "}
              {pagination.total_results} results
            </div>
            <div className="flex items-center gap-2">
              <label htmlFor="pageSize" className="text-muted-foreground whitespace-nowrap">
                Show:
              </label>
              <select
                id="pageSize"
                value={pageSize}
                onChange={(e) => onPageSizeChange(Number(e.target.value))}
                disabled={isLoading}
                className="h-8 rounded-md border border-input bg-background px-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
              </select>
            </div>
          </div>
          {pagination.total_pages > 1 && (
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => onPageChange(pagination.page - 1)}
                disabled={pagination.page === 1 || isLoading}
              >
                Previous
              </Button>
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">Page</span>
                <input
                  type="number"
                  min={1}
                  max={pagination.total_pages}
                  value={pagination.page}
                  onChange={(e) => {
                    const page = Number(e.target.value)
                    if (page >= 1 && page <= pagination.total_pages) {
                      onPageChange(page)
                    }
                  }}
                  disabled={isLoading}
                  className="w-16 h-8 rounded-md border border-input bg-background px-2 text-sm text-center ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                />
                <span className="text-sm text-muted-foreground">of {pagination.total_pages}</span>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => onPageChange(pagination.page + 1)}
                disabled={pagination.page === pagination.total_pages || isLoading}
              >
                Next
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
