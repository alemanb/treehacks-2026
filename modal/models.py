from pydantic import BaseModel


class Metadata(BaseModel):
    object: str | None = None
    color: str | None = None
    timestamp: str | None = None
    motion_vector: list[float] | None = None
    device_id: str | None = None


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
