import { useCallback, useEffect, useState } from "react"

interface UrlState {
  query: string
  resultLimit: number
}

interface UseUrlStateReturn {
  urlState: UrlState
  updateUrlState: (updates: Partial<UrlState>) => void
  restoreFromUrl: () => UrlState
}

/**
 * Custom hook for managing URL query parameters for search state.
 * Enables bookmarkable and shareable search results.
 */
export function useUrlState(): UseUrlStateReturn {
  const [urlState, setUrlState] = useState<UrlState>({
    query: "",
    resultLimit: 10,
  })

  // Parse URL parameters and return state object
  const restoreFromUrl = useCallback((): UrlState => {
    const params = new URLSearchParams(window.location.search)

    const query = params.get("q") || ""
    const resultLimit = parseInt(params.get("limit") || "10", 10)

    // Validate parameters
    const validatedLimit = isNaN(resultLimit) || resultLimit < 1 ? 10 :
                           resultLimit > 100 ? 100 : resultLimit

    return {
      query,
      resultLimit: validatedLimit,
    }
  }, [])

  // Update URL parameters without page reload
  const updateUrlState = useCallback((updates: Partial<UrlState>) => {
    setUrlState((prev) => {
      const newState = { ...prev, ...updates }

      // Build URL search params
      const params = new URLSearchParams()
      if (newState.query) params.set("q", newState.query)
      if (newState.resultLimit !== 10) params.set("limit", newState.resultLimit.toString())

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
