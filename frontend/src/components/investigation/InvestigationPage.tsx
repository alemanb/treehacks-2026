import { useCallback, useEffect, useState, useRef } from "react"
import { useSearch } from "@/hooks/useSearch"
import { useUrlState } from "@/hooks/useUrlState"
import { InputPhase } from "./InputPhase"
import { ProcessingPhase } from "./ProcessingPhase"
import { ResultsPhase } from "./ResultsPhase"
import { Button } from "@/components/ui/button"

type Phase = "input" | "processing" | "results"

export function InvestigationPage() {
  const [phase, setPhase] = useState<Phase>("input")
  const [searchDone, setSearchDone] = useState(false)
  const [query, setQuery] = useState("")
  const isInitialMount = useRef(true)

  const { urlState, updateUrlState } = useUrlState()

  const handleSearchComplete = useCallback(() => {
    setSearchDone(true)
  }, [])

  const { search, results, pagination, isLoading, error, pageSize, setPage, setPageSize } = useSearch(handleSearchComplete)

  // Restore search from URL on mount
  useEffect(() => {
    if (isInitialMount.current && urlState.query) {
      isInitialMount.current = false
      setQuery(urlState.query)
      setPhase("processing")
      setSearchDone(false)
      // Restore page size from URL
      if (urlState.pageSize !== pageSize) {
        setPageSize(urlState.pageSize)
      }
      // Execute search with URL parameters
      search(urlState.query, urlState.page)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlState])

  // Update URL when search state changes
  const updateUrl = useCallback((q: string, p: number, ps: number) => {
    updateUrlState({ query: q, page: p, pageSize: ps })
  }, [updateUrlState])

  // Wrap setPage to update URL
  const handlePageChange = useCallback((page: number) => {
    setPage(page)
    updateUrl(query, page, pageSize)
  }, [setPage, updateUrl, query, pageSize])

  // Wrap setPageSize to update URL
  const handlePageSizeChange = useCallback((size: number) => {
    setPageSize(size)
    updateUrl(query, 1, size) // Reset to page 1 when changing page size
  }, [setPageSize, updateUrl, query])

  function handleSubmit(q: string) {
    setQuery(q)
    setPhase("processing")
    setSearchDone(false)
    search(q, 1)
    updateUrl(q, 1, pageSize)
  }

  function handleTransitionEnd() {
    setPhase("results")
  }

  function handleReset() {
    setPhase("input")
    setSearchDone(false)
    setQuery("")
    // Clear URL parameters
    window.history.pushState({}, "", window.location.pathname)
  }

  function handleRetry() {
    if (query) {
      setPhase("processing")
      setSearchDone(false)
      search(query, 1)
      updateUrl(query, 1, pageSize)
    }
  }

  return (
    <main className="min-h-screen bg-background p-6">
      {phase === "input" && (
        <div className="animate-fade-in">
          <InputPhase onSubmit={handleSubmit} />
        </div>
      )}
      {phase === "processing" && (
        <div className="animate-fade-in">
          <ProcessingPhase
            isComplete={!isLoading && searchDone}
            onTransitionEnd={handleTransitionEnd}
          />
        </div>
      )}
      {phase === "results" && (
        <div className="animate-fade-in">
          {error ? (
            <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
              <p className="text-destructive">{error}</p>
              <div className="flex gap-2">
                <Button variant="outline" onClick={handleReset}>
                  New Search
                </Button>
                <Button onClick={handleRetry}>Retry</Button>
              </div>
            </div>
          ) : results.length === 0 ? (
            <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
              <p className="text-muted-foreground">
                No matching observations found.
              </p>
              <Button variant="outline" onClick={handleReset}>
                New Search
              </Button>
            </div>
          ) : (
            <ResultsPhase
              results={results}
              pagination={pagination}
              onPageChange={handlePageChange}
              pageSize={pageSize}
              onPageSizeChange={handlePageSizeChange}
              isLoading={isLoading}
              onReset={handleReset}
            />
          )}
        </div>
      )}
    </main>
  )
}
