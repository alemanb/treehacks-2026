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

  const { search, results, totalResults, isLoading, error } = useSearch(handleSearchComplete)

  // Restore search from URL on mount
  useEffect(() => {
    if (isInitialMount.current && urlState.query) {
      isInitialMount.current = false
      setQuery(urlState.query)
      setPhase("processing")
      setSearchDone(false)
      // Execute search with URL parameters
      search(urlState.query, urlState.resultLimit)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlState])

  // Update URL when search state changes
  const updateUrl = useCallback((q: string, limit: number) => {
    updateUrlState({ query: q, resultLimit: limit })
  }, [updateUrlState])

  function handleSubmit(q: string) {
    setQuery(q)
    setPhase("processing")
    setSearchDone(false)
    search(q, 10) // Default to 10 results
    updateUrl(q, 10)
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
      search(query, 10)
      updateUrl(query, 10)
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
              totalResults={totalResults}
              isLoading={isLoading}
              onReset={handleReset}
            />
          )}
        </div>
      )}
    </main>
  )
}
