import {
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table"
import type { SearchResult } from "@/types/search"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { columns } from "./columns"

interface DataTableViewProps {
  results: SearchResult[]
  totalResults: number
  isLoading?: boolean
}

export function DataTableView({
  results,
  totalResults,
  isLoading = false,
}: DataTableViewProps) {
  const table = useReactTable({
    data: results,
    columns,
    getCoreRowModel: getCoreRowModel(),
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

      {totalResults > 0 && (
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between px-2">
          <div className="text-sm text-muted-foreground">
            Showing top {results.length} of {totalResults} results
          </div>
          {/* <div className="flex items-center gap-2 text-sm"> */}
            {/* <label htmlFor="resultLimit" className="text-muted-foreground whitespace-nowrap">
              Show top:
            </label>
            <select
              id="resultLimit"
              value={resultLimit}
              onChange={(e) => onResultLimitChange(Number(e.target.value))}
              disabled={isLoading}
              className="h-8 rounded-md border border-input bg-background px-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <option value={10}>10 results</option>
              <option value={25}>25 results</option>
              <option value={50}>50 results</option>
            </select> */}
          {/* </div> */}
        </div>
      )}
    </div>
  )
}
