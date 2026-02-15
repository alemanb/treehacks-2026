import { useEffect } from "react"
import type { SearchResult, PaginationMetadata } from "@/types/search"
import { Button } from "@/components/ui/button"
import { CalendarView } from "@/components/calendar/CalendarView"
import { DataTableView } from "@/components/data-table/DataTableView"

interface ResultsPhaseProps {
  results: SearchResult[]
  pagination: PaginationMetadata | null
  onPageChange: (page: number) => void
  pageSize: number
  onPageSizeChange: (size: number) => void
  isLoading: boolean
  onReset: () => void
}

export function ResultsPhase({
  results,
  pagination,
  onPageChange,
  pageSize,
  onPageSizeChange,
  isLoading,
  onReset,
}: ResultsPhaseProps) {
  // Keyboard navigation: ArrowLeft for previous page, ArrowRight for next page
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Only handle arrow keys when not typing in an input/textarea
      if (
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement
      ) {
        return
      }

      if (!pagination || isLoading) return

      if (event.key === "ArrowLeft" && pagination.page > 1) {
        event.preventDefault()
        onPageChange(pagination.page - 1)
      } else if (event.key === "ArrowRight" && pagination.page < pagination.total_pages) {
        event.preventDefault()
        onPageChange(pagination.page + 1)
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [pagination, onPageChange, isLoading])

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Investigation Results</h2>
        <Button variant="outline" onClick={onReset}>
          New Search
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[auto_minmax(0,_1fr)] gap-6 items-start">
        <CalendarView results={results} />
        <DataTableView
          results={results}
          pagination={pagination}
          onPageChange={onPageChange}
          pageSize={pageSize}
          onPageSizeChange={onPageSizeChange}
          isLoading={isLoading}
        />
      </div>
    </div>
  )
}
