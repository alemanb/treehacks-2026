import { useCallback, useRef, useState } from "react"
import type { SearchResponse, SearchResult } from "@/types/search"

const BACKEND_URL = "https://alemanb--treehacks-vector-search-web.modal.run"

interface UseSearchReturn {
  search: (query: string, includeMotion: boolean) => void
  results: SearchResult[]
  isLoading: boolean
  error: string | null
}

export function useSearch(onComplete?: () => void): UseSearchReturn {
  const [results, setResults] = useState<SearchResult[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const search = useCallback(
    async (query: string, includeMotion: boolean) => {
      setIsLoading(true)
      setResults([])
      setError(null)

      // Cancel previous request if still pending
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }

      abortControllerRef.current = new AbortController()

      try {
        const response = await fetch(`${BACKEND_URL}/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query }),
          signal: abortControllerRef.current.signal,
        })

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          throw new Error(
            errorData.detail || `Search failed: ${response.statusText}`,
          )
        }

        const data: SearchResponse = await response.json()

        // Filter to only show observations with motion data
        const filteredResults = data.results.filter(
          (r) => r.metadata.motion_vector !== null
        )

        setResults(filteredResults)
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

  return { search, results, isLoading, error }
}
