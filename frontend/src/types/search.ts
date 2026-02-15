export interface Metadata {
  object: string | null
  color: string | null
  timestamp: string // ISO 8601 (e.g., "2026-02-13T14:30:05Z")
  motion_vector: number[] | null
  device_id: string | null
}

export interface SearchResult {
  id: string
  content: string // natural language description (from embedding source)
  score: number // cosine similarity 0-1 → mapped to likelihood percentage
  metadata: Metadata
}

export interface PaginationMetadata {
  page: number
  page_size: number
  total_results: number
  total_pages: number
}

export interface SearchResponse {
  query: string
  results: SearchResult[]
  pagination: PaginationMetadata
}
