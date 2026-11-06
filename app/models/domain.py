"""
Clean, consumer-facing domain models exposed by our modern Urja Meter Ops API service.
Normalized and decoupled from legacy portal quirks and unstandardized schemas.
"""
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator


class MeterStatus(str, Enum):
    """Operational lifecycle status of a smart meter."""
    INSTALLED = "Installed"
    FAULTY = "Faulty"
    DECOMMISSIONED = "Decommissioned"


class PhaseType(str, Enum):
    """Electrical phase configuration."""
    ONE_PHASE = "1-Phase"
    THREE_PHASE = "3-Phase"


class MeterMake(str, Enum):
    """Major meter hardware manufacturers identified in the utility fleet."""
    SCHNEIDER = "Schneider Electric"
    SECURE = "Secure Meters"
    GENUS = "Genus"
    ALLIED = "Allied"
    LT = "L&T"
    HPL = "HPL"


class InstallType(str, Enum):
    """Meter installation and connection type."""
    CT_OPERATED = "CT Operated"
    WHOLE_CURRENT = "Whole Current"


class SortOrder(str, Enum):
    """Sort direction for time-series readings."""
    DESC = "desc"
    ASC = "asc"


class GeoLocation(BaseModel):
    """Normalized geographical coordinates."""
    latitude: Optional[float] = Field(default=None, description="Latitude coordinate in decimal degrees")
    longitude: Optional[float] = Field(default=None, description="Longitude coordinate in decimal degrees")


class HierarchyElement(BaseModel):
    """A single node within the electrical distribution hierarchy."""
    name: Optional[str] = Field(default=None, description="Human-readable node name")
    code: Optional[str] = Field(default=None, description="Standard utility node identifier / code")

    @field_validator("name", "code", mode="before")
    @classmethod
    def coerce_to_str(cls, v: Any) -> Optional[str]:
        if v is not None:
            return str(v)
        return None


class FullHierarchy(BaseModel):
    """Complete 7-tier electrical distribution network hierarchy."""
    zone: HierarchyElement = Field(default_factory=HierarchyElement, description="Distribution Zone")
    circle: HierarchyElement = Field(default_factory=HierarchyElement, description="Distribution Circle")
    division: HierarchyElement = Field(default_factory=HierarchyElement, description="Division")
    subdivision: HierarchyElement = Field(default_factory=HierarchyElement, description="Sub-Division")
    substation: HierarchyElement = Field(default_factory=HierarchyElement, description="Primary Substation (SS)")
    feeder: HierarchyElement = Field(default_factory=HierarchyElement, description="11kV Feeder Line")
    dt: HierarchyElement = Field(default_factory=HierarchyElement, description="Distribution Transformer (DT)")


class TransformerInfo(BaseModel):
    """Enriched Distribution Transformer specifications."""
    code: str = Field(description="Unique DT identifier code (e.g. DT-001)")
    name: Optional[str] = Field(default=None, description="DT location / name")
    feeder_code: Optional[str] = Field(default=None, description="Parent 11kV feeder line code")
    capacity_kva: Optional[float] = Field(default=None, description="Transformer power capacity rating in kVA")


class NameplateDetails(BaseModel):
    """Hardware specifications and operational lifecycle status."""
    meter_id: Optional[str] = Field(default=None, description="Meter identifier")
    serial_no: Optional[str] = Field(default=None, description="Hardware manufacturer serial number")
    make: Optional[str] = Field(default=None, description="Meter manufacturer (e.g., Schneider Electric, Secure Meters)")
    phase_type: Optional[str] = Field(default=None, description="Phase configuration (1-Phase, 3-Phase)")
    install_status: Optional[str] = Field(default=None, description="Operational state (Installed, Faulty, Decommissioned)")
    install_type: Optional[str] = Field(default=None, description="Metering connection (Whole Current, CT Operated)")
    build: Optional[str] = Field(default=None, description="Hardware / firmware build revision")


class LatestReadingSummary(BaseModel):
    """Summary of the most recently recorded electrical telemetry reading."""
    timestamp: Optional[str] = Field(default=None, description="Original recording timestamp (DD/MM/YYYY HH:MM)")
    timestamp_iso: Optional[str] = Field(default=None, description="Standardized ISO-8601 UTC timestamp")
    kwh: Optional[float] = Field(default=None, description="Active energy in kilowatt-hours (kWh)")
    kvah: Optional[float] = Field(default=None, description="Apparent energy in kilovolt-ampere-hours (kVAh)")
    voltage_r: Optional[float] = Field(default=None, description="Phase R voltage in Volts")


class MeterSummary(BaseModel):
    """Lightweight meter summary for collection queries, search, and geospatial listings."""
    meter_id: str = Field(description="Smart meter identifier (e.g., J100002)")
    serial_no: Optional[str] = Field(default=None, description="Hardware serial number")
    make: Optional[str] = Field(default=None, description="Meter manufacturer")
    phase_type: Optional[str] = Field(default=None, description="Phase type (1-Phase, 3-Phase)")
    status: Optional[str] = Field(default=None, description="Operating status (Installed, Faulty, Decommissioned)")
    install_type: Optional[str] = Field(default=None, description="Installation type (CT Operated, Whole Current)")
    build: Optional[str] = Field(default=None, description="Hardware build tag")
    dt_code: Optional[str] = Field(default=None, description="Associated Distribution Transformer code")
    dt_name: Optional[str] = Field(default=None, description="Associated Distribution Transformer name")
    feeder_code: Optional[str] = Field(default=None, description="Parent feeder code")
    substation_code: Optional[str] = Field(default=None, description="Parent substation code")
    division_code: Optional[str] = Field(default=None, description="Parent division code")
    circle_code: Optional[str] = Field(default=None, description="Parent circle code")
    zone_code: Optional[str] = Field(default=None, description="Parent zone code")
    location: Optional[GeoLocation] = Field(default=None, description="GIS coordinates")
    distance_km: Optional[float] = Field(default=None, description="Distance in km when querying near coordinates")


class PaginatedMetersResponse(BaseModel):
    """Paginated collection of smart meters."""
    items: List[MeterSummary] = Field(description="List of meters matching query criteria")
    total: int = Field(description="Total count of matching meters across all pages")
    page: int = Field(description="Current page index (1-based)")
    page_size: int = Field(description="Page size limit")
    total_pages: int = Field(description="Total number of available pages")


class MeterDetailResponse(BaseModel):
    """Detailed meter view aggregating nameplate, full hierarchy, DT details, and latest reading."""
    meter_id: str = Field(description="Unique smart meter identifier")
    serial_no: Optional[str] = Field(default=None, description="Hardware serial number")
    nameplate: NameplateDetails = Field(default_factory=NameplateDetails, description="Meter manufacturer specs")
    hierarchy: FullHierarchy = Field(default_factory=FullHierarchy, description="Complete 7-tier distribution hierarchy")
    transformer: Optional[TransformerInfo] = Field(default=None, description="Associated transformer specifications")
    location: Optional[GeoLocation] = Field(default=None, description="Physical geographic installation coordinates")
    latest_reading: Optional[LatestReadingSummary] = Field(default=None, description="Latest telemetry reading summary")


class NormalizedIntervalReading(BaseModel):
    """Standardized 30-minute electrical telemetry interval reading."""
    timestamp: str = Field(description="Original timestamp string (DD/MM/YYYY HH:MM)")
    timestamp_iso: Optional[str] = Field(default=None, description="Standardized ISO-8601 timestamp")
    kwh: Optional[float] = Field(default=None, description="Cumulative active energy in kWh")
    kvah: Optional[float] = Field(default=None, description="Cumulative apparent energy in kVAh")
    voltage_r: Optional[float] = Field(default=None, description="Phase R voltage in Volts")


class ConsumptionSummary(BaseModel):
    """Analytical summary computed over interval telemetry readings."""
    total_readings: int = Field(description="Number of telemetry interval readings evaluated")
    period_start: Optional[str] = Field(default=None, description="Timestamp of first reading in interval")
    period_end: Optional[str] = Field(default=None, description="Timestamp of last reading in interval")
    earliest_kwh: Optional[float] = Field(default=None, description="Initial kWh reading")
    latest_kwh: Optional[float] = Field(default=None, description="Final kWh reading")
    net_kwh_consumption: Optional[float] = Field(default=None, description="Net active energy consumed (kWh)")
    net_kvah_consumption: Optional[float] = Field(default=None, description="Net apparent energy consumed (kVAh)")
    avg_voltage_r: Optional[float] = Field(default=None, description="Average Phase R voltage across period")
    min_voltage_r: Optional[float] = Field(default=None, description="Minimum Phase R voltage recorded")
    max_voltage_r: Optional[float] = Field(default=None, description="Maximum Phase R voltage recorded")
    apparent_power_factor: Optional[float] = Field(
        default=None,
        description="Calculated power factor (net_kwh / net_kvah)",
    )


class PaginationMeta(BaseModel):
    """Standard pagination metadata."""
    total: int = Field(description="Total number of items")
    page: int = Field(description="Current page index (1-based)")
    page_size: int = Field(description="Page size limit")
    total_pages: int = Field(description="Total number of pages")


class MeterConsumptionResponse(BaseModel):
    """Paginated time-series telemetry with analytical summary statistics."""
    meter_id: str = Field(description="Unique smart meter identifier")
    summary: ConsumptionSummary = Field(description="Computed telemetry metrics for the evaluated window")
    pagination: PaginationMeta = Field(description="Interval readings pagination metadata")
    readings: List[NormalizedIntervalReading] = Field(description="Chronological interval readings for this page")


class TransformerResponse(BaseModel):
    """Distribution Transformer with attached meter counts and operational metrics."""
    code: str = Field(description="Transformer code (e.g., DT-001)")
    name: str = Field(description="Transformer location / name")
    feeder_code: Optional[str] = Field(default=None, description="Parent feeder code")
    capacity_kva: Optional[float] = Field(default=None, description="Capacity in kVA")
    total_meters: int = Field(default=0, description="Total meters connected to this DT")
    installed_count: int = Field(default=0, description="Installed & functioning meters")
    faulty_count: int = Field(default=0, description="Faulty meters requiring field service")
    decommissioned_count: int = Field(default=0, description="Decommissioned meters")


class PaginatedTransformersResponse(BaseModel):
    """Paginated collection of Distribution Transformers."""
    items: List[TransformerResponse] = Field(description="List of transformers matching query")
    total: int = Field(description="Total matching transformers")
    page: int = Field(description="Current page (1-based)")
    page_size: int = Field(description="Page size limit")
    total_pages: int = Field(description="Total pages available")


class TransformerDetailResponse(BaseModel):
    """Single Distribution Transformer details and full list of attached meters."""
    code: str = Field(description="Transformer code")
    name: str = Field(description="Transformer name")
    feeder_code: Optional[str] = Field(default=None, description="Parent feeder code")
    capacity_kva: Optional[float] = Field(default=None, description="Capacity in kVA")
    hierarchy_path: Optional[str] = Field(default=None, description="Full breadcrumb path in distribution network")
    meter_counts: Dict[str, int] = Field(default_factory=dict, description="Meters broken down by operational status")
    meters: List[MeterSummary] = Field(default_factory=list, description="All meters connected to this DT")


class HierarchyTreeNode(BaseModel):
    """A node in the reconstructed electrical distribution topology tree."""
    name: str = Field(description="Node name")
    code: str = Field(description="Node code")
    level: str = Field(description="Hierarchy depth level (Zone, Circle, Division, Subdivision, Substation, Feeder, DT)")
    total_meters: int = Field(default=0, description="Aggregate meters under this subtree")
    installed_meters: int = Field(default=0, description="Installed meters under this subtree")
    faulty_meters: int = Field(default=0, description="Faulty meters under this subtree")
    decommissioned_meters: int = Field(default=0, description="Decommissioned meters under this subtree")
    children: List[Any] = Field(default_factory=list, description="Sub-nodes in distribution tree")


class HierarchyTreeResponse(BaseModel):
    """Reconstructed hierarchical tree of the utility distribution network."""
    tree: List[HierarchyTreeNode] = Field(description="Top-level hierarchy zones and their nested descendants")
    total_meters: int = Field(description="Total fleet meters accounted for in the hierarchy tree")


class AnomalyItem(BaseModel):
    """A single data anomaly or inconsistency discovered in the legacy portal dataset."""
    meter_id: str = Field(description="Affected smart meter identifier")
    category: str = Field(description="Anomaly classification (e.g. missing_geo, hierarchy_mismatch, orphaned_dt)")
    description: str = Field(description="Detailed explanation of the data defect")
    raw_data: Dict[str, Any] = Field(default_factory=dict, description="Raw upstream record for debugging")


class AnomaliesReportResponse(BaseModel):
    """Comprehensive data quality and fleet health report."""
    total_meters_scanned: int = Field(description="Total meters analyzed in the legacy dataset")
    total_anomalies: int = Field(description="Total anomalies discovered")
    anomalies: List[AnomalyItem] = Field(description="Itemized list of data anomalies and defects")
    fleet_statistics: Dict[str, Dict[str, int]] = Field(
        description="Fleet breakdown by manufacturer, phase type, operational status, and build"
    )
    transformer_health: List[Dict[str, Any]] = Field(
        description="Transformers flagged with high failure rates or abnormal meter allocations"
    )


class HealthResponse(BaseModel):
    """Operational status and local in-memory index metrics."""
    status: str = Field(default="ok", description="Overall health status")
    upstream_status: Optional[str] = Field(default="connected", description="Upstream portal connectivity")
    version: str = Field(default="2.0.0", description="API version")
    index_status: Dict[str, Any] = Field(
        default_factory=dict,
        description="Local index cache status (meter count, DT count, sync timestamps)",
    )


class ErrorResponse(BaseModel):
    """Standardized error response payload."""
    error: str = Field(description="Human-readable error description")
    code: str = Field(description="Machine-readable error classification code")
    details: Optional[Any] = Field(default=None, description="Optional diagnostic details")
