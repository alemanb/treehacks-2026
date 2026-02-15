import { useCallback, useState } from "react"
import { useSearch } from "@/hooks/useSearch"
import { InputPhase } from "./InputPhase"
import { ProcessingPhase } from "./ProcessingPhase"
import { ResultsPhase } from "./ResultsPhase"
import { Button } from "@/components/ui/button"

type Phase = "input" | "processing" | "results"

export function InvestigationPage() {
  const [phase, setPhase] = useState<Phase>("input")
  const [searchDone, setSearchDone] = useState(false)
  const [query, setQuery] = useState("")

  const handleSearchComplete = useCallback(() => {
    setSearchDone(true)
  }, [])

  const { search, results, isLoading, error } = useSearch(handleSearchComplete)

  function handleSubmit(q: string, includeMotion: boolean) {
    setQuery(q)
    setPhase("processing")
    setSearchDone(false)
    search(q, includeMotion)
  }

  function handleTransitionEnd() {
    setPhase("results")
  }

  function handleReset() {
    setPhase("input")
    setSearchDone(false)
    setQuery("")
  }

  function handleRetry() {
    if (query) {
      setPhase("processing")
      setSearchDone(false)
      search(query, false)
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
            <ResultsPhase results={results} onReset={handleReset} />
          )}
        </div>
      )}
    </main>
  )
}
