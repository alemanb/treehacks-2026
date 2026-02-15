import { useCallback, useEffect, useState } from "react"

interface UrlState {
  query: string
  page: number
  pageSize: number
}

interface UseUrlStateReturn {
  urlState: UrlState
  updateUrlState: (updates: Partial<UrlState>) => void
  restoreFromUrl: () => UrlState
}

/**
 * Custom hook for managing URL query parameters for pagination state.
 * Enables bookmarkable and shareable search results.
 */
export function useUrlState(): UseUrlStateReturn {
  const [urlState, setUrlState] = useState<UrlState>({
    query: "",
    page: 1,
    pageSize: 10,
  })

  // Parse URL parameters and return state object
  const restoreFromUrl = useCallback((): UrlState => {
    const params = new URLSearchParams(window.location.search)

    const query = params.get("q") || ""
    const page = parseInt(params.get("page") || "1", 10)
    const pageSize = parseInt(params.get("size") || "10", 10)

    // Validate parameters
    const validatedPage = isNaN(page) || page < 1 ? 1 : page
    const validatedPageSize = isNaN(pageSize) || pageSize < 1 ? 10 :
                               pageSize > 100 ? 100 : pageSize

    return {
      query,
      page: validatedPage,
      pageSize: validatedPageSize,
    }
  }, [])

  // Update URL parameters without page reload
  const updateUrlState = useCallback((updates: Partial<UrlState>) => {
    setUrlState((prev) => {
      const newState = { ...prev, ...updates }

      // Build URL search params
      const params = new URLSearchParams()
      if (newState.query) params.set("q", newState.query)
      if (newState.page !== 1) params.set("page", newState.page.toString())
      if (newState.pageSize !== 10) params.set("size", newState.pageSize.toString())

      // Update URL without page reload
      const newUrl = params.toString()
        ? `${window.location.pathname}?${params.toString()}`
        : window.location.pathname

      window.history.pushState({}, "", newUrl)

      return newState
    })
  }, [])

  // Restore state from URL on mount
  useEffect(() => {
    const initialState = restoreFromUrl()
    setUrlState(initialState)
  }, [restoreFromUrl])

  // Handle browser back/forward navigation
  useEffect(() => {
    const handlePopState = () => {
      const restoredState = restoreFromUrl()
      setUrlState(restoredState)
    }

    window.addEventListener("popstate", handlePopState)
    return () => window.removeEventListener("popstate", handlePopState)
  }, [restoreFromUrl])

  return {
    urlState,
    updateUrlState,
    restoreFromUrl,
  }
}
