"""
Raw/upstream Pydantic models reflecting the exact data payloads returned by the
legacy Urja Meter Ops web portal.
"""
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class UpstreamEnergyData(BaseModel):
    """
    Telemetry payload from GET /portal/meters/{meter_id}/energy
    Captures electrical telemetry (e.g. active energy, apparent energy, voltage, timestamp).
    """
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    kwh: Optional[float] = Field(default=None, alias="KWH")
    kvah: Optional[float] = Field(default=None, alias="KVAH")
    v_r: Optional[float] = Field(default=None, alias="V(R)")
    timestamp: Optional[Union[str, int, float]] = Field(default=None, alias="timestamp")
    raw: Dict[str, Any] = Field(default_factory=dict)


class UpstreamGeoData(BaseModel):
    """
    Geographic coordinates payload from GET /portal/meters/{meter_id}/geo
    """
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    latitude: Optional[float] = Field(default=None, alias="lat")
    longitude: Optional[float] = Field(default=None, alias="lng")


class UpstreamHierarchyData(BaseModel):
    """
    Network topology hierarchy extracted from Svelte payload.
    """
    model_config = ConfigDict(extra="allow")

    zone: Optional[str] = None
    circle: Optional[str] = None
    division: Optional[str] = None
    substation: Optional[str] = None
    feeder: Optional[str] = None


class UpstreamNameplateData(BaseModel):
    """
    Meter specifications extracted from Svelte payload.
    """
    model_config = ConfigDict(extra="allow")

    make: Optional[str] = None
    phase: Optional[Union[str, int]] = None
    status: Optional[str] = None


class UpstreamSveltePayload(BaseModel):
    """
    Wrapper for SvelteKit __data.json response.
    Extra fields allowed to handle arbitrary nested SvelteKit devalue/node representations.
    """
    model_config = ConfigDict(extra="allow")

    nodes: Optional[List[Any]] = None
    data: Optional[Dict[str, Any]] = None
