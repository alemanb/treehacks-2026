from pydantic import BaseModel, ConfigDict, field_validator


class Metadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    object: str | None = None
    color: str | None = None
    timestamp: str | None = None
    motion_vector: list[float] | None = None
    device_id: str | None = None
    frame_uuid: str | None = None
    frame_link: str | None = None


class IngestRequest(BaseModel):
    content: str
    metadata: Metadata | None = None


class BatchIngestRequest(BaseModel):
    documents: list[IngestRequest]


class IngestResponse(BaseModel):
    status: str
    id: str


class BatchIngestResponse(BaseModel):
    indexed: int
    errors: int


class HealthResponse(BaseModel):
    status: str
    elasticsearch: str
    jina: str


# Search API models
class SearchRequest(BaseModel):
    query: str
    page: int = 1
    page_size: int = 10

    @field_validator('page')
    @classmethod
    def validate_page(cls, v: int) -> int:
        if v < 1:
            raise ValueError('page must be >= 1')
        return v

    @field_validator('page_size')
    @classmethod
    def validate_page_size(cls, v: int) -> int:
        if not (1 <= v <= 100):
            raise ValueError('page_size must be between 1 and 100')
        return v


class SearchResult(BaseModel):
    id: str
    content: str
    score: float
    metadata: Metadata


class PaginationMetadata(BaseModel):
    """Pagination metadata for search results."""
    page: int
    page_size: int
    total_results: int
    total_pages: int


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    pagination: PaginationMetadata
