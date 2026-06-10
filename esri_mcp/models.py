"""Pydantic request/response models. Esri's raw JSON is verbose and inconsistent —
these are the clean shapes returned to the model."""

from pydantic import BaseModel


class LayerSummary(BaseModel):
    id: int
    name: str
    type: str | None = None
    geometry_type: str | None = None


class FieldInfo(BaseModel):
    name: str  # the real queryable field name — NOT the alias
    alias: str | None = None
    type: str
    length: int | None = None


class LayerInfo(BaseModel):
    id: int
    name: str
    description: str | None = None
    geometry_type: str | None = None
    fields: list[FieldInfo]
    max_record_count: int | None = None
    supports_pagination: bool = False
    extent: dict | None = None
    source_url: str


class Feature(BaseModel):
    attributes: dict
    geometry: dict | None = None


class QueryResult(BaseModel):
    count: int
    truncated: bool
    features: list[Feature]
    source_url: str


class GeocodeCandidate(BaseModel):
    address: str
    longitude: float
    latitude: float
    score: float


class ReverseGeocodeResult(BaseModel):
    address: str | None = None
    longitude: float
    latitude: float
    raw_address_fields: dict = {}


class PortalItem(BaseModel):
    id: str
    title: str
    type: str
    owner: str | None = None
    snippet: str | None = None
    url: str | None = None
    modified: str | None = None  # ISO 8601
    tags: list[str] = []


class PortalSearchResult(BaseModel):
    total: int
    count: int
    items: list[PortalItem]
    source_url: str
