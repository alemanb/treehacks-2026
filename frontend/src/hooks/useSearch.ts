import { useCallback, useRef, useState } from "react"
import type { SearchResponse, SearchResult, PaginationMetadata } from "@/types/search"

const BACKEND_URL = "https://alemanb--treehacks-vector-search-web.modal.run"

interface UseSearchReturn {
  search: (query: string, page?: number, customPageSize?: number) => void
  results: SearchResult[]
  pagination: PaginationMetadata | null
  isLoading: boolean
  error: string | null
  currentPage: number
  pageSize: number
  setPage: (page: number) => void
  setPageSize: (size: number) => void
}

export function useSearch(onComplete?: () => void): UseSearchReturn {
  const [results, setResults] = useState<SearchResult[]>([])
  const [pagination, setPagination] = useState<PaginationMetadata | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [currentQuery, setCurrentQuery] = useState<string>("")
  const [currentPage, setCurrentPage] = useState<number>(1)
  const [pageSize, setPageSize] = useState<number>(10)
  const abortControllerRef = useRef<AbortController | null>(null)

  const search = useCallback(
    async (query: string, page: number = 1, customPageSize?: number) => {
      // Use customPageSize if provided, otherwise use current pageSize state
      const effectivePageSize = customPageSize ?? pageSize

      setIsLoading(true)
      setError(null)
      setCurrentQuery(query)
      setCurrentPage(page)

      // Cancel previous request if still pending
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }

      abortControllerRef.current = new AbortController()

      try {
        const response = await fetch(`${BACKEND_URL}/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query,
            page,
            page_size: effectivePageSize,
          }),
          signal: abortControllerRef.current.signal,
        })

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          throw new Error(
            errorData.detail || `Search failed: ${response.statusText}`,
          )
        }

        const data: SearchResponse = await response.json()

        setResults(data.results)
        setPagination(data.pagination)
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
    [onComplete, pageSize],
  )

  const setPage = useCallback(
    (page: number) => {
      if (currentQuery && pagination && page >= 1 && page <= pagination.total_pages) {
        search(currentQuery, page)
      }
    },
    [currentQuery, pagination, search]
  )

  const handleSetPageSize = useCallback(
    (size: number) => {
      setPageSize(size)
      // When changing page size, reset to page 1 and pass new size explicitly
      if (currentQuery) {
        setCurrentPage(1)
        search(currentQuery, 1, size)  // Pass the new size explicitly
      }
    },
    [currentQuery, search]
  )

  return {
    search,
    results,
    pagination,
    isLoading,
    error,
    currentPage,
    pageSize,
    setPage,
    setPageSize: handleSetPageSize
  }
}
