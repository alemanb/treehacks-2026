import { useCallback, useRef, useState } from "react"
import type { IntelligentSearchResponse, SearchResult } from "@/types/search"

const BACKEND_URL = "https://alemanb--treehacks-vector-search-web.modal.run"

interface UseSearchReturn {
  search: (query: string, maxResults?: number) => void
  results: SearchResult[]
  totalResults: number
  isLoading: boolean
  error: string | null
}

export function useSearch(onComplete?: () => void): UseSearchReturn {
  const [results, setResults] = useState<SearchResult[]>([])
  const [totalResults, setTotalResults] = useState<number>(0)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const search = useCallback(
    async (query: string, maxResults: number = 10) => {
      const effectiveLimit = maxResults

      setIsLoading(true)
      setError(null)

      // Cancel previous request if still pending
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }

      abortControllerRef.current = new AbortController()

      try {
        // Call intelligent search - AI returns results ranked by likelihood
        const response = await fetch(`${BACKEND_URL}/search/intelligent`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query,
            max_results: effectiveLimit, // Request only the top N results from AI
          }),
          signal: abortControllerRef.current.signal,
        })

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          throw new Error(
            errorData.detail || `Search failed: ${response.statusText}`,
          )
        }

        const data: IntelligentSearchResponse = await response.json()

        // Convert IntelligentSearchResult to SearchResult format
        const convertedResults: SearchResult[] = data.results.map(result => ({
          id: result.id,
          content: result.content,
          score: result.likelihood_score / 100, // Convert 0-100 to 0-1 for compatibility
          metadata: result.metadata,
        }))

        // Sort by likelihood score (highest to lowest)
        const sortedResults = convertedResults.sort((a, b) => b.score - a.score)

        setResults(sortedResults)
        setTotalResults(data.total_count)

        onComplete?.()
      } catch (err) {
        // Don't set error if request was aborted (user started new search)
        if (err instanceof Error && err.name !== "AbortError") {
          setError(err.message || "An unknown error occurred")
        }
      } finally {
        setIsLoading(false)
        abortControllerRef.current = null
      }
    },
    [onComplete],
  )

  return {
    search,
    results,
    totalResults,
    isLoading,
    error
  }
}
