import type { SearchResult } from "@/types/search"
import { Button } from "@/components/ui/button"
import { CalendarView } from "@/components/calendar/CalendarView"
import { DataTableView } from "@/components/data-table/DataTableView"

interface ResultsPhaseProps {
  results: SearchResult[]
  totalResults: number
  isLoading: boolean
  onReset: () => void
}

export function ResultsPhase({
  results,
  totalResults,
  isLoading,
  onReset,
}: ResultsPhaseProps) {
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
          totalResults={totalResults}
          isLoading={isLoading}
        />
      </div>
    </div>
  )
}
