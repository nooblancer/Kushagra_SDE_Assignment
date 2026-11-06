import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import math
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.client.portal_client import UrjaPortalClient
from app.config import get_settings
from app.dashboard import DASHBOARD_HTML
from app.exceptions import (
    PortalAuthError,
    PortalError,
    PortalNotFoundError,
    PortalRateLimitError,
    PortalUpstreamError,
)
from app.models.domain import (
    ConsumptionSummary,
    ErrorResponse,
    FullHierarchy,
    GeoLocation,
    HealthResponse,
    HierarchyElement,
    HierarchyTreeResponse,
    InstallType,
    LatestReadingSummary,
    MeterConsumptionResponse,
    MeterDetailResponse,
    MeterMake,
    MeterStatus,
    MeterSummary,
    NameplateDetails,
    NormalizedIntervalReading,
    PaginatedMetersResponse,
    PaginatedTransformersResponse,
    PaginationMeta,
    PhaseType,
    SortOrder,
    TransformerDetailResponse,
    TransformerInfo,
    TransformerResponse,
)
from app.services.index_service import LocalIndexService, _parse_timestamp_iso


# Lifespan and Dependencies
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    app.state.portal_client = UrjaPortalClient(settings=settings)
    app.state.index_service = LocalIndexService(ttl_seconds=600.0)

    # Initial eager sync on startup
    try:
        await app.state.index_service.ensure_synced(app.state.portal_client)
    except Exception as exc:
        print(f"Warning: Initial index sync failed on startup ({exc}). Index will sync on first request.")

    yield

    if hasattr(app.state, "portal_client") and app.state.portal_client:
        await app.state.portal_client.close()


def get_portal_client(request: Request) -> UrjaPortalClient:
    return request.app.state.portal_client


def get_index_service(request: Request) -> LocalIndexService:
    return request.app.state.index_service


app = FastAPI(
    title="Urja Meter Ops API Service",
    description=(
        "A high-performance, systematic RESTful API adapter over the legacy Urja Meter Ops portal. "
        "Powered by an in-memory query engine populated via HMAC-SHA256 signed bulk exports, "
        "supporting multi-attribute filtering, Haversine geospatial radius search, full grid hierarchy "
        "reconstruction, transformer telemetry aggregation, and automated data quality inspection."
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters={
        "docExpansion": "list",
        "defaultModelsExpandDepth": 0,
        "deepLinking": True,
        "displayRequestDuration": True,
        "filter": True,
        "tryItOutEnabled": True,
    },
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception Handlers
@app.exception_handler(PortalAuthError)
async def auth_error_handler(request: Request, exc: PortalAuthError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content=ErrorResponse(
            error="Upstream authentication failure",
            code="UPSTREAM_AUTH_ERROR",
            details=exc.message,
        ).model_dump(),
    )


@app.exception_handler(PortalNotFoundError)
async def not_found_error_handler(request: Request, exc: PortalNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=ErrorResponse(
            error="Resource not found",
            code="NOT_FOUND",
            details=exc.message,
        ).model_dump(),
    )


@app.exception_handler(PortalRateLimitError)
async def rate_limit_error_handler(request: Request, exc: PortalRateLimitError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=ErrorResponse(
            error="Upstream rate limit reached",
            code="RATE_LIMITED",
            details=exc.message,
        ).model_dump(),
    )


@app.exception_handler(PortalUpstreamError)
async def upstream_error_handler(request: Request, exc: PortalUpstreamError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content=ErrorResponse(
            error="Upstream communication failure",
            code="UPSTREAM_ERROR",
            details=exc.message,
        ).model_dump(),
    )


@app.exception_handler(PortalError)
async def generic_portal_error_handler(request: Request, exc: PortalError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Internal portal service error",
            code="PORTAL_INTERNAL_ERROR",
            details=exc.message,
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Internal Server Error",
            code="UNHANDLED_EXCEPTION",
            details=str(exc),
        ).model_dump(),
    )


# -----------------------------------------------------------------------------
# 1. Meters Endpoints
# -----------------------------------------------------------------------------

@app.get(
    "/api/v1/meters",
    response_model=PaginatedMetersResponse,
    summary="List & search meters with multi-attribute and geospatial filters",
    tags=["Meters"],
)
async def list_meters(
    # --- Primary Filters (Dropdowns & Search) ---
    q: Optional[str] = Query(
        None,
        description="Free-text search across meter ID, serial number, and DT name",
        openapi_examples={"example_meter": {"summary": "Meter ID", "value": "J100001"}, "example_dt": {"summary": "DT Name", "value": "Mansarovar"}},
    ),
    status: Optional[MeterStatus] = Query(
        None,
        description="Operational lifecycle status (select from dropdown)",
    ),
    phase_type: Optional[PhaseType] = Query(
        None,
        description="Electrical phase configuration (select from dropdown)",
    ),
    make: Optional[MeterMake] = Query(
        None,
        description="Hardware manufacturer (select from dropdown)",
    ),
    install_type: Optional[InstallType] = Query(
        None,
        description="Meter connection / installation type (select from dropdown)",
    ),

    # --- Geospatial Radius Search ---
    near_lat: Optional[float] = Query(
        None,
        description="Center latitude for geospatial radius search",
        openapi_examples={"jaipur": {"summary": "Jaipur Center", "value": 26.8530}},
    ),
    near_lng: Optional[float] = Query(
        None,
        description="Center longitude for geospatial radius search",
        openapi_examples={"jaipur": {"summary": "Jaipur Center", "value": 75.7600}},
    ),
    radius_km: Optional[float] = Query(
        None,
        description="Geospatial search radius boundary in kilometers",
        openapi_examples={"five_km": {"summary": "5 km radius", "value": 5.0}},
    ),

    # --- Advanced Grid Topology Filters ---
    dt_code: Optional[str] = Query(
        None,
        description="[Advanced Grid Filter] Distribution Transformer code (e.g. DT-001)",
        openapi_examples={"dt": {"summary": "DT Code", "value": "DT-001"}},
    ),
    feeder_code: Optional[str] = Query(
        None,
        description="[Advanced Grid Filter] 11kV feeder line code (e.g. F-001)",
        openapi_examples={"feeder": {"summary": "Feeder Code", "value": "F-001"}},
    ),
    substation_code: Optional[str] = Query(
        None,
        description="[Advanced Grid Filter] Upstream primary substation code (e.g. SS-01)",
    ),
    division_code: Optional[str] = Query(
        None,
        description="[Advanced Grid Filter] Utility division code (e.g. D-01)",
    ),
    circle_code: Optional[str] = Query(
        None,
        description="[Advanced Grid Filter] Utility circle code (e.g. C-01)",
    ),
    zone_code: Optional[str] = Query(
        None,
        description="[Advanced Grid Filter] Utility distribution zone code (e.g. Z-01)",
    ),
    build: Optional[str] = Query(
        None,
        description="[Advanced Hardware Filter] Hardware / firmware build revision tag",
    ),

    # --- Pagination ---
    page: int = Query(1, ge=1, description="Page number (1-based index)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    client: UrjaPortalClient = Depends(get_portal_client),
    index_service: LocalIndexService = Depends(get_index_service),
) -> PaginatedMetersResponse:
    await index_service.ensure_synced(client)

    items, total, total_pages = index_service.query_meters(
        q=q,
        make=make.value if make else None,
        phase_type=phase_type.value if phase_type else None,
        status=status.value if status else None,
        install_type=install_type.value if install_type else None,
        build=build,
        dt_code=dt_code,
        feeder_code=feeder_code,
        substation_code=substation_code,
        division_code=division_code,
        circle_code=circle_code,
        zone_code=zone_code,
        near_lat=near_lat,
        near_lng=near_lng,
        radius_km=radius_km,
        page=page,
        page_size=page_size,
    )

    summaries = [
        MeterSummary(
            meter_id=item["meter_id"],
            serial_no=item.get("serial_no"),
            make=item.get("make"),
            phase_type=item.get("phase_type"),
            status=item.get("status"),
            install_type=item.get("install_type"),
            build=item.get("build"),
            dt_code=item.get("dt_code"),
            dt_name=item.get("dt_name"),
            feeder_code=item.get("feeder_code"),
            substation_code=item.get("substation_code"),
            division_code=item.get("division_code"),
            circle_code=item.get("circle_code"),
            zone_code=item.get("zone_code"),
            location=GeoLocation(**item["location"]) if item.get("location") else None,
            distance_km=item.get("distance_km"),
        )
        for item in items
    ]

    return PaginatedMetersResponse(
        items=summaries,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@app.get(
    "/api/v1/meters/{meter_id}",
    response_model=MeterDetailResponse,
    summary="Get single meter profile with hardware, hierarchy, transformer, and latest reading",
    tags=["Meters"],
)
async def get_meter_profile(
    meter_id: str,
    include_latest_reading: bool = Query(True, description="Fetch the latest telemetry reading summary from upstream"),
    client: UrjaPortalClient = Depends(get_portal_client),
    index_service: LocalIndexService = Depends(get_index_service),
) -> MeterDetailResponse:
    await index_service.ensure_synced(client)

    meter_data = index_service.get_meter(meter_id)
    if not meter_data:
        raise PortalNotFoundError(f"Meter '{meter_id}' not found in registry.")

    # Transformer enriched details
    transformer_info = None
    dt_code = meter_data.get("dt_code")
    if dt_code:
        dt_detail = index_service.get_transformer_detail(dt_code)
        if dt_detail:
            transformer_info = TransformerInfo(
                code=dt_detail["code"],
                name=dt_detail.get("name"),
                feeder_code=dt_detail.get("feeder_code"),
                capacity_kva=dt_detail.get("capacity_kva"),
            )

    # Optional latest telemetry fetch
    latest_reading = None
    if include_latest_reading:
        try:
            energy_raw = await client.get_meter_energy(meter_id)
            readings = energy_raw.get("data")
            if isinstance(readings, list) and readings:
                last_pt = readings[-1]
                ts = last_pt.get("timestamp")
                latest_reading = LatestReadingSummary(
                    timestamp=ts,
                    timestamp_iso=_parse_timestamp_iso(ts),
                    kwh=float(last_pt["kwh"]) if "kwh" in last_pt and last_pt["kwh"] is not None else None,
                    kvah=float(last_pt["kvah"]) if "kvah" in last_pt and last_pt["kvah"] is not None else None,
                    voltage_r=float(last_pt["voltR"]) if "voltR" in last_pt and last_pt["voltR"] is not None else None,
                )
        except Exception:
            # Graceful degradation if telemetry endpoint is temporarily unreachable
            pass

    h = meter_data.get("hierarchy", {})
    return MeterDetailResponse(
        meter_id=meter_data["meter_id"],
        serial_no=meter_data.get("serial_no"),
        nameplate=NameplateDetails(
            meter_id=meter_data["meter_id"],
            serial_no=meter_data.get("serial_no"),
            make=meter_data.get("make"),
            phase_type=meter_data.get("phase_type"),
            install_status=meter_data.get("status"),
            install_type=meter_data.get("install_type"),
            build=meter_data.get("build"),
        ),
        hierarchy=FullHierarchy(
            zone=HierarchyElement(**h.get("zone", {})),
            circle=HierarchyElement(**h.get("circle", {})),
            division=HierarchyElement(**h.get("division", {})),
            subdivision=HierarchyElement(**h.get("subdivision", {})),
            substation=HierarchyElement(**h.get("substation", {})),
            feeder=HierarchyElement(**h.get("feeder", {})),
            dt=HierarchyElement(**h.get("dt", {})),
        ),
        transformer=transformer_info,
        location=GeoLocation(**meter_data["location"]) if meter_data.get("location") else None,
        latest_reading=latest_reading,
    )


# -----------------------------------------------------------------------------
# 2. Telemetry & Consumption Endpoints
# -----------------------------------------------------------------------------

@app.get(
    "/api/v1/meters/{meter_id}/consumption",
    response_model=MeterConsumptionResponse,
    summary="Paginated 30-minute interval telemetry with analytical summary statistics",
    tags=["Telemetry"],
)
async def get_meter_consumption(
    meter_id: str,
    from_timestamp: Optional[str] = Query(
        None,
        description="Filter start date/time (DD/MM/YYYY HH:MM or ISO)",
        openapi_examples={"week_start": {"summary": "Start of week", "value": "23/06/2026 23:30"}},
    ),
    to_timestamp: Optional[str] = Query(
        None,
        description="Filter end date/time (DD/MM/YYYY HH:MM or ISO)",
        openapi_examples={"week_end": {"summary": "End of week", "value": "30/06/2026 23:30"}},
    ),
    order: SortOrder = Query(
        SortOrder.DESC,
        description="Sort direction for interval readings (select from dropdown)",
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(48, ge=1, le=500, description="Readings per page (default 48 = 24 hours of 30-min intervals)"),
    client: UrjaPortalClient = Depends(get_portal_client),
) -> MeterConsumptionResponse:
    energy_raw = await client.get_meter_energy(meter_id)
    raw_readings = energy_raw.get("data", [])
    if not isinstance(raw_readings, list):
        raw_readings = []

    # Parse and normalize interval readings
    parsed: List[NormalizedIntervalReading] = []
    for r in raw_readings:
        if not isinstance(r, dict):
            continue
        ts_orig = r.get("timestamp")
        if not ts_orig:
            continue
        ts_iso = _parse_timestamp_iso(ts_orig)

        # Date range filtering if requested
        if from_timestamp:
            from_iso = _parse_timestamp_iso(from_timestamp)
            if ts_iso and from_iso and ts_iso < from_iso:
                continue
        if to_timestamp:
            to_iso = _parse_timestamp_iso(to_timestamp)
            if ts_iso and to_iso and ts_iso > to_iso:
                continue

        kwh_val = float(r["kwh"]) if "kwh" in r and r["kwh"] is not None else None
        kvah_val = float(r["kvah"]) if "kvah" in r and r["kvah"] is not None else None
        vr_val = float(r["voltR"]) if "voltR" in r and r["voltR"] is not None else None

        parsed.append(
            NormalizedIntervalReading(
                timestamp=ts_orig,
                timestamp_iso=ts_iso,
                kwh=kwh_val,
                kvah=kvah_val,
                voltage_r=vr_val,
            )
        )

    # Sort chronological or reverse-chronological
    parsed.sort(key=lambda x: x.timestamp_iso or x.timestamp, reverse=(order.value == "desc"))

    # Compute analytical statistics across all filtered readings
    total = len(parsed)
    voltages = [x.voltage_r for x in parsed if x.voltage_r is not None]

    chronological = sorted(parsed, key=lambda x: x.timestamp_iso or x.timestamp)
    earliest_kwh = chronological[0].kwh if chronological and chronological[0].kwh is not None else None
    latest_kwh = chronological[-1].kwh if chronological and chronological[-1].kwh is not None else None

    earliest_kvah = chronological[0].kvah if chronological and chronological[0].kvah is not None else None
    latest_kvah = chronological[-1].kvah if chronological and chronological[-1].kvah is not None else None

    net_kwh = round(latest_kwh - earliest_kwh, 2) if earliest_kwh is not None and latest_kwh is not None else None
    net_kvah = round(latest_kvah - earliest_kvah, 2) if earliest_kvah is not None and latest_kvah is not None else None

    power_factor = None
    if net_kwh is not None and net_kvah is not None and net_kvah > 0:
        power_factor = round(min(1.0, max(0.0, net_kwh / net_kvah)), 4)

    summary = ConsumptionSummary(
        total_readings=total,
        period_start=chronological[0].timestamp_iso if chronological else None,
        period_end=chronological[-1].timestamp_iso if chronological else None,
        earliest_kwh=earliest_kwh,
        latest_kwh=latest_kwh,
        net_kwh_consumption=net_kwh,
        net_kvah_consumption=net_kvah,
        avg_voltage_r=round(sum(voltages) / len(voltages), 2) if voltages else None,
        min_voltage_r=min(voltages) if voltages else None,
        max_voltage_r=max(voltages) if voltages else None,
        apparent_power_factor=power_factor,
    )

    # Pagination slice
    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1
    page = max(1, min(page, total_pages))
    offset = (page - 1) * page_size
    page_items = parsed[offset : offset + page_size]

    return MeterConsumptionResponse(
        meter_id=meter_id,
        summary=summary,
        pagination=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
        readings=page_items,
    )


# -----------------------------------------------------------------------------
# 3. Transformers Endpoints
# -----------------------------------------------------------------------------

@app.get(
    "/api/v1/transformers",
    response_model=PaginatedTransformersResponse,
    summary="List Distribution Transformers with live rolled-up meter statistics",
    tags=["Transformers"],
)
async def list_transformers(
    q: Optional[str] = Query(None, description="Free-text search in DT code or DT name", openapi_examples={"name": {"summary": "DT Name", "value": "Malviya"}}),
    feeder_code: Optional[str] = Query(None, description="Filter by parent feeder code (e.g. F-001)"),
    min_capacity_kva: Optional[float] = Query(None, description="Minimum transformer rating in kVA (e.g. 100)"),
    max_capacity_kva: Optional[float] = Query(None, description="Maximum transformer rating in kVA"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    client: UrjaPortalClient = Depends(get_portal_client),
    index_service: LocalIndexService = Depends(get_index_service),
) -> PaginatedTransformersResponse:
    await index_service.ensure_synced(client)

    items, total, total_pages = index_service.query_transformers(
        q=q,
        feeder_code=feeder_code,
        min_capacity_kva=min_capacity_kva,
        max_capacity_kva=max_capacity_kva,
        page=page,
        page_size=page_size,
    )

    dt_responses = [TransformerResponse(**item) for item in items]
    return PaginatedTransformersResponse(
        items=dt_responses,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@app.get(
    "/api/v1/transformers/{dt_code}",
    response_model=TransformerDetailResponse,
    summary="Get single Distribution Transformer with connected meters and health counts",
    tags=["Transformers"],
)
async def get_transformer_detail(
    dt_code: str,
    client: UrjaPortalClient = Depends(get_portal_client),
    index_service: LocalIndexService = Depends(get_index_service),
) -> TransformerDetailResponse:
    await index_service.ensure_synced(client)

    dt_detail = index_service.get_transformer_detail(dt_code)
    if not dt_detail:
        raise PortalNotFoundError(f"Distribution Transformer '{dt_code}' not found.")

    meter_summaries = [
        MeterSummary(
            meter_id=m["meter_id"],
            serial_no=m.get("serial_no"),
            make=m.get("make"),
            phase_type=m.get("phase_type"),
            status=m.get("status"),
            install_type=m.get("install_type"),
            build=m.get("build"),
            dt_code=m.get("dt_code"),
            dt_name=m.get("dt_name"),
            feeder_code=m.get("feeder_code"),
            substation_code=m.get("substation_code"),
            division_code=m.get("division_code"),
            circle_code=m.get("circle_code"),
            zone_code=m.get("zone_code"),
            location=GeoLocation(**m["location"]) if m.get("location") else None,
        )
        for m in dt_detail.get("meters", [])
    ]

    return TransformerDetailResponse(
        code=dt_detail["code"],
        name=dt_detail["name"],
        feeder_code=dt_detail.get("feeder_code"),
        capacity_kva=dt_detail.get("capacity_kva"),
        hierarchy_path=dt_detail.get("hierarchy_path"),
        meter_counts=dt_detail.get("meter_counts", {}),
        meters=meter_summaries,
    )


# -----------------------------------------------------------------------------
# 4. Network & Hierarchy Endpoints
# -----------------------------------------------------------------------------

@app.get(
    "/api/v1/network/hierarchy",
    response_model=HierarchyTreeResponse,
    summary="Reconstructed 7-tier grid topology tree with aggregated fleet counts",
    tags=["Network & Hierarchy"],
)
async def get_grid_hierarchy_tree(
    client: UrjaPortalClient = Depends(get_portal_client),
    index_service: LocalIndexService = Depends(get_index_service),
) -> HierarchyTreeResponse:
    await index_service.ensure_synced(client)

    tree = index_service.build_hierarchy_tree()
    total_meters = len(index_service._meters)
    return HierarchyTreeResponse(
        tree=tree,
        total_meters=total_meters,
    )


# -----------------------------------------------------------------------------
# 5. Health & Client UI
# -----------------------------------------------------------------------------

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health and local cache metrics",
    tags=["System"],
)
async def health_check(
    request: Request,
    index_service: LocalIndexService = Depends(get_index_service),
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        upstream_status="connected",
        version="2.0.0",
        index_status=index_service.get_index_stats(),
    )


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    """Serves the interactive web client extension."""
    return HTMLResponse(content=DASHBOARD_HTML, status_code=200)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    """Default entrypoint loads the modern interactive web client."""
    return HTMLResponse(content=DASHBOARD_HTML, status_code=200)
