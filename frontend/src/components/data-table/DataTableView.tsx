import { useMemo, useState } from "react"
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
import { Button } from "@/components/ui/button"
import { createColumns } from "./columns"

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
  const [selectedImageUrl, setSelectedImageUrl] = useState<string | null>(null)
  const [selectedTimestamp, setSelectedTimestamp] = useState<string | null>(null)
  const [imageLoadFailed, setImageLoadFailed] = useState(false)

  const closeModal = () => {
    setSelectedImageUrl(null)
    setSelectedTimestamp(null)
    setImageLoadFailed(false)
  }

  const columns = useMemo(
    () =>
      createColumns((frameUuid: string, timestamp: string) => {
        if (!frameUuid || !timestamp) return

        const matchingResult = results.find(
          (result) => result.metadata.frame_uuid === frameUuid,
        )
        const rawFrameLink = matchingResult?.metadata.frame_link?.trim() ?? ""
        if (!rawFrameLink) {
          throw new Error(
            `Missing frame_link for search result frame_uuid: ${frameUuid}`,
          )
        }
        const resolvedUrl =
          rawFrameLink.startsWith("http://") || rawFrameLink.startsWith("https://")
            ? rawFrameLink
            : `http://${rawFrameLink}`

        setSelectedTimestamp(timestamp)
        setImageLoadFailed(false)
        setSelectedImageUrl(resolvedUrl)
      }),
    [results],
  )

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

      {selectedImageUrl && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          role="dialog"
          aria-modal="true"
          aria-label="Frame image viewer"
          onClick={closeModal}
        >
          <div
            className="w-full max-w-5xl rounded-lg bg-background border shadow-xl p-4 space-y-3"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm text-muted-foreground truncate">
                {selectedTimestamp}
              </p>
              <Button variant="outline" size="sm" onClick={closeModal}>
                Close
              </Button>
            </div>

            {imageLoadFailed ? (
              <p className="text-sm text-destructive">
                Could not load image for this event.
              </p>
            ) : (
              <img
                src={selectedImageUrl}
                alt={selectedTimestamp ?? "Frame image"}
                className="w-full h-auto max-h-[75vh] object-contain rounded-md border"
                onError={() => setImageLoadFailed(true)}
              />
            )}
          </div>
        </div>
      )}
    </div>
  )
}
