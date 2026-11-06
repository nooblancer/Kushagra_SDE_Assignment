import asyncio
from datetime import datetime
import math
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from app.client.portal_client import UrjaPortalClient


def _parse_timestamp_iso(ts_str: Optional[str]) -> Optional[str]:
    """Converts DD/MM/YYYY HH:MM or ISO strings into ISO-8601 UTC."""
    if not ts_str:
        return None
    for fmt in ("%d/%m/%Y %H:%M", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M"):
        try:
            dt = datetime.strptime(ts_str.strip(), fmt)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return ts_str


def _haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two points in kilometers."""
    r = 6371.0  # Earth radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def _normalize_string(val: Optional[Any]) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _normalize_make(val: Optional[Any]) -> Optional[str]:
    raw = _normalize_string(val)
    if not raw:
        return None
    lower = raw.lower()
    if "schneider" in lower:
        return "Schneider Electric"
    if "secure" in lower:
        return "Secure Meters"
    if "genius" in lower:
        return "Genius"
    if "hpl" in lower:
        return "HPL"
    if "l&t" in lower or "larsen" in lower:
        return "L&T"
    return raw.title()


def _normalize_phase(val: Optional[Any]) -> Optional[str]:
    raw = _normalize_string(val)
    if not raw:
        return None
    lower = raw.lower()
    if "1" in lower or "single" in lower:
        return "1-Phase"
    if "3" in lower or "three" in lower:
        return "3-Phase"
    return raw


def _normalize_status(val: Optional[Any]) -> Optional[str]:
    raw = _normalize_string(val)
    if not raw:
        return None
    lower = raw.lower()
    if "installed" in lower or "active" in lower:
        return "Installed"
    if "fault" in lower:
        return "Faulty"
    if "decommission" in lower or "inactive" in lower:
        return "Decommissioned"
    return raw.title()


class LocalIndexService:
    """
    In-memory query engine, index layer, and anomaly detector.
    Indexes the complete fleet of meters (403) and Distribution Transformers (40)
    harvested from the signed bulk export (/portal/export) and /portal/dts.
    """

    def __init__(self, ttl_seconds: float = 600.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._last_synced_at: Optional[float] = None
        self._sync_lock = asyncio.Lock()

        # In-memory storage
        self._meters: List[Dict[str, Any]] = []
        self._meters_by_id: Dict[str, Dict[str, Any]] = {}
        self._transformers: List[Dict[str, Any]] = []
        self._transformers_by_code: Dict[str, Dict[str, Any]] = {}
        self._anomalies: List[Dict[str, Any]] = []
        self._fleet_stats: Dict[str, Dict[str, int]] = {}

    @property
    def is_synced(self) -> bool:
        if self._last_synced_at is None:
            return False
        return (time.time() - self._last_synced_at) < self.ttl_seconds

    @property
    def last_synced_at_iso(self) -> Optional[str]:
        if not self._last_synced_at:
            return None
        return datetime.fromtimestamp(self._last_synced_at).strftime("%Y-%m-%dT%H:%M:%SZ")

    def get_index_stats(self) -> Dict[str, Any]:
        return {
            "indexed_meters": len(self._meters),
            "indexed_transformers": len(self._transformers),
            "total_anomalies_detected": len(self._anomalies),
            "last_synced_at": self.last_synced_at_iso,
            "refresh_ttl_seconds": self.ttl_seconds,
            "status": "fresh" if self.is_synced else "stale_or_uninitialized",
        }

    async def ensure_synced(self, client: UrjaPortalClient, force: bool = False) -> None:
        """Ensures the in-memory index is fresh. Performs a lazy sync if expired or missing."""
        if self.is_synced and not force:
            return

        async with self._sync_lock:
            # Double-check inside lock
            if self.is_synced and not force:
                return

            # Fetch transformers and meters concurrently
            dts_task = client.get_all_transformers()
            meters_task = client.export_all_meters()

            raw_dts, raw_meters = await asyncio.gather(dts_task, meters_task)
            self._process_and_index(raw_dts, raw_meters)

    def _process_and_index(
        self,
        raw_dts: List[Dict[str, Any]],
        raw_meters: List[Dict[str, Any]],
    ) -> None:
        """Cleans, normalizes, inspects anomalies, and cross-references meters and transformers."""
        dt_lookup: Dict[str, Dict[str, Any]] = {}
        for item in raw_dts:
            code = _normalize_string(item.get("code"))
            if code:
                dt_lookup[code] = {
                    "code": code,
                    "name": _normalize_string(item.get("name")),
                    "feeder_code": _normalize_string(item.get("feederCode") or item.get("feeder_code")),
                    "capacity_kva": float(item["capacityKva"]) if "capacityKva" in item else None,
                    "meters": [],
                    "installed_count": 0,
                    "faulty_count": 0,
                    "decommissioned_count": 0,
                }

        normalized_meters: List[Dict[str, Any]] = []
        meters_by_id: Dict[str, Dict[str, Any]] = {}
        anomalies: List[Dict[str, Any]] = []

        seen_serials: Dict[str, str] = {}
        make_counts: Dict[str, int] = {}
        phase_counts: Dict[str, int] = {}
        status_counts: Dict[str, int] = {}
        build_counts: Dict[str, int] = {}

        for m in raw_meters:
            meter_id = _normalize_string(m.get("meterId") or m.get("meter_id"))
            if not meter_id:
                continue

            serial_no = _normalize_string(m.get("serialNo") or m.get("serial_no"))
            raw_make = m.get("make")
            clean_make = _normalize_make(raw_make) or "Unknown"

            raw_phase = m.get("phaseType") or m.get("phase")
            clean_phase = _normalize_phase(raw_phase) or "Unknown"

            raw_status = m.get("installStatus") or m.get("status")
            clean_status = _normalize_status(raw_status) or "Unknown"

            clean_install_type = _normalize_string(m.get("installType") or m.get("installation_type"))
            clean_build = _normalize_string(m.get("build"))

            # Geo validation
            raw_geo = m.get("geo") or {}
            lat_val = raw_geo.get("lat") if "lat" in raw_geo else raw_geo.get("latitude")
            lng_val = raw_geo.get("lng") if "lng" in raw_geo else raw_geo.get("longitude")

            clean_lat: Optional[float] = None
            clean_lng: Optional[float] = None
            if lat_val is not None and lng_val is not None:
                try:
                    clean_lat = float(lat_val)
                    clean_lng = float(lng_val)
                    # Check geographic bounds (India: lat ~8-38, lng ~68-98)
                    if clean_lat == 0.0 and clean_lng == 0.0:
                        anomalies.append({
                            "meter_id": meter_id,
                            "category": "null_island_coordinates",
                            "description": "Meter coordinates are (0.0, 0.0)",
                            "raw_data": {"lat": lat_val, "lng": lng_val},
                        })
                        clean_lat = None
                        clean_lng = None
                    elif not (-90.0 <= clean_lat <= 90.0 and -180.0 <= clean_lng <= 180.0):
                        anomalies.append({
                            "meter_id": meter_id,
                            "category": "out_of_bounds_coordinates",
                            "description": f"Coordinates ({clean_lat}, {clean_lng}) out of range",
                            "raw_data": {"lat": lat_val, "lng": lng_val},
                        })
                        clean_lat = None
                        clean_lng = None
                except (ValueError, TypeError):
                    anomalies.append({
                        "meter_id": meter_id,
                        "category": "invalid_geo_format",
                        "description": f"Unable to parse latitude '{lat_val}' or longitude '{lng_val}'",
                        "raw_data": {"lat": lat_val, "lng": lng_val},
                    })
            else:
                anomalies.append({
                    "meter_id": meter_id,
                    "category": "missing_geo",
                    "description": "Meter record lacks geographical latitude/longitude coordinates",
                    "raw_data": raw_geo,
                })

            # Check duplicate serial numbers
            if serial_no:
                if serial_no in seen_serials:
                    anomalies.append({
                        "meter_id": meter_id,
                        "category": "duplicate_serial_number",
                        "description": f"Serial number '{serial_no}' duplicated with meter '{seen_serials[serial_no]}'",
                        "raw_data": {"serial_no": serial_no, "first_meter_id": seen_serials[serial_no]},
                    })
                else:
                    seen_serials[serial_no] = meter_id

            # Hierarchy & DT validation
            dt_code = _normalize_string(m.get("dtCode") or m.get("dt_code"))
            hierarchy_raw = m.get("hierarchy") or {}

            def _get_node(key: str) -> Dict[str, Optional[str]]:
                node = hierarchy_raw.get(key) or {}
                if isinstance(node, dict):
                    return {
                        "name": _normalize_string(node.get("name")),
                        "code": _normalize_string(node.get("code")),
                    }
                elif isinstance(node, str):
                    return {"name": node, "code": None}
                return {"name": None, "code": None}

            zone_node = _get_node("zone")
            circle_node = _get_node("circle")
            div_node = _get_node("division")
            subdiv_node = _get_node("subdivision")
            ss_node = _get_node("substation")
            feeder_node = _get_node("feeder")
            dt_node = _get_node("dt")

            # Check hierarchy DT code vs meter.dtCode
            if dt_code and dt_node.get("code") and dt_code != dt_node.get("code"):
                anomalies.append({
                    "meter_id": meter_id,
                    "category": "hierarchy_dt_mismatch",
                    "description": (
                        f"Meter dtCode '{dt_code}' mismatches hierarchy.dt.code '{dt_node.get('code')}'"
                    ),
                    "raw_data": {"dtCode": dt_code, "hierarchy_dt": dt_node},
                })

            # Check Orphaned DT
            effective_dt_code = dt_code or dt_node.get("code")
            dt_name = None
            if effective_dt_code:
                if effective_dt_code in dt_lookup:
                    dt_name = dt_lookup[effective_dt_code]["name"]
                    dt_lookup[effective_dt_code]["meters"].append(meter_id)
                    if clean_status == "Installed":
                        dt_lookup[effective_dt_code]["installed_count"] += 1
                    elif clean_status == "Faulty":
                        dt_lookup[effective_dt_code]["faulty_count"] += 1
                    elif clean_status == "Decommissioned":
                        dt_lookup[effective_dt_code]["decommissioned_count"] += 1
                else:
                    anomalies.append({
                        "meter_id": meter_id,
                        "category": "orphaned_dt_reference",
                        "description": (
                            f"Referenced DT code '{effective_dt_code}' does not exist in Distribution Transformers registry"
                        ),
                        "raw_data": {"dtCode": effective_dt_code},
                    })

            # Tally stats
            make_counts[clean_make] = make_counts.get(clean_make, 0) + 1
            phase_counts[clean_phase] = phase_counts.get(clean_phase, 0) + 1
            status_counts[clean_status] = status_counts.get(clean_status, 0) + 1
            if clean_build:
                build_counts[clean_build] = build_counts.get(clean_build, 0) + 1

            meter_entry = {
                "meter_id": meter_id,
                "serial_no": serial_no,
                "make": clean_make,
                "phase_type": clean_phase,
                "status": clean_status,
                "install_type": clean_install_type,
                "build": clean_build,
                "dt_code": effective_dt_code,
                "dt_name": dt_name or dt_node.get("name"),
                "feeder_code": feeder_node.get("code"),
                "substation_code": ss_node.get("code"),
                "division_code": div_node.get("code"),
                "circle_code": circle_node.get("code"),
                "zone_code": zone_node.get("code"),
                "location": {
                    "latitude": clean_lat,
                    "longitude": clean_lng,
                }
                if clean_lat is not None and clean_lng is not None
                else None,
                "hierarchy": {
                    "zone": zone_node,
                    "circle": circle_node,
                    "division": div_node,
                    "subdivision": subdiv_node,
                    "substation": ss_node,
                    "feeder": feeder_node,
                    "dt": dt_node,
                },
                "raw_record": m,
            }
            normalized_meters.append(meter_entry)
            meters_by_id[meter_id] = meter_entry

        # Commit to instance state
        self._meters = normalized_meters
        self._meters_by_id = meters_by_id
        self._transformers = list(dt_lookup.values())
        self._transformers_by_code = dt_lookup
        self._anomalies = anomalies
        self._fleet_stats = {
            "by_make": make_counts,
            "by_phase_type": phase_counts,
            "by_status": status_counts,
            "by_build": build_counts,
        }
        self._last_synced_at = time.time()

    def query_meters(
        self,
        q: Optional[str] = None,
        make: Optional[str] = None,
        phase_type: Optional[str] = None,
        status: Optional[str] = None,
        install_type: Optional[str] = None,
        build: Optional[str] = None,
        dt_code: Optional[str] = None,
        feeder_code: Optional[str] = None,
        substation_code: Optional[str] = None,
        division_code: Optional[str] = None,
        circle_code: Optional[str] = None,
        zone_code: Optional[str] = None,
        near_lat: Optional[float] = None,
        near_lng: Optional[float] = None,
        radius_km: Optional[float] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int, int]:
        """
        Fast in-memory multi-attribute filtering, full-text substring search,
        Haversine geospatial radius search, and pagination.
        Returns: (items, total_count, total_pages)
        """
        results: List[Dict[str, Any]] = []

        q_lower = q.lower().strip() if q else None
        make_lower = make.lower().strip() if make else None
        phase_lower = phase_type.lower().strip() if phase_type else None
        status_lower = status.lower().strip() if status else None
        install_type_lower = install_type.lower().strip() if install_type else None
        build_lower = build.lower().strip() if build else None

        dt_code_norm = dt_code.strip() if dt_code else None
        feeder_code_norm = feeder_code.strip() if feeder_code else None
        ss_code_norm = substation_code.strip() if substation_code else None
        div_code_norm = division_code.strip() if division_code else None
        circle_code_norm = circle_code.strip() if circle_code else None
        zone_code_norm = zone_code.strip() if zone_code else None

        has_geo_filter = near_lat is not None and near_lng is not None

        for m in self._meters:
            # Free-text search
            if q_lower:
                m_id = m["meter_id"].lower()
                s_no = (m.get("serial_no") or "").lower()
                d_name = (m.get("dt_name") or "").lower()
                d_code = (m.get("dt_code") or "").lower()
                if (
                    q_lower not in m_id
                    and q_lower not in s_no
                    and q_lower not in d_name
                    and q_lower not in d_code
                ):
                    continue

            # Attribute filters
            if make_lower and (m.get("make") or "").lower() != make_lower:
                continue
            if phase_lower and (m.get("phase_type") or "").lower() != phase_lower:
                continue
            if status_lower and (m.get("status") or "").lower() != status_lower:
                continue
            if install_type_lower and (m.get("install_type") or "").lower() != install_type_lower:
                continue
            if build_lower and (m.get("build") or "").lower() != build_lower:
                continue

            # Hierarchy code filters
            if dt_code_norm and m.get("dt_code") != dt_code_norm:
                continue
            if feeder_code_norm and m.get("feeder_code") != feeder_code_norm:
                continue
            if ss_code_norm and m.get("substation_code") != ss_code_norm:
                continue
            if div_code_norm and m.get("division_code") != div_code_norm:
                continue
            if circle_code_norm and m.get("circle_code") != circle_code_norm:
                continue
            if zone_code_norm and m.get("zone_code") != zone_code_norm:
                continue

            # Geospatial Haversine radius filter
            distance_km: Optional[float] = None
            if has_geo_filter:
                loc = m.get("location")
                if not loc or loc.get("latitude") is None or loc.get("longitude") is None:
                    continue
                distance_km = _haversine_distance_km(
                    near_lat,  # type: ignore
                    near_lng,  # type: ignore
                    loc["latitude"],
                    loc["longitude"],
                )
                if radius_km is not None and distance_km > radius_km:
                    continue

            item = dict(m)
            item["distance_km"] = round(distance_km, 3) if distance_km is not None else None
            results.append(item)

        # Sort: by distance if geospatial search was applied, otherwise by meter_id
        if has_geo_filter:
            results.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else float("inf"))
        else:
            results.sort(key=lambda x: x["meter_id"])

        total = len(results)
        page_size = max(1, min(page_size, 100))
        total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1
        page = max(1, min(page, total_pages))

        offset = (page - 1) * page_size
        paginated_items = results[offset : offset + page_size]

        return paginated_items, total, total_pages

    def get_meter(self, meter_id: str) -> Optional[Dict[str, Any]]:
        """O(1) in-memory meter retrieval."""
        return self._meters_by_id.get(meter_id)

    def query_transformers(
        self,
        q: Optional[str] = None,
        feeder_code: Optional[str] = None,
        min_capacity_kva: Optional[float] = None,
        max_capacity_kva: Optional[float] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int, int]:
        """Queries and filters Distribution Transformers."""
        results: List[Dict[str, Any]] = []
        q_lower = q.lower().strip() if q else None

        for dt in self._transformers:
            if q_lower:
                if q_lower not in dt["code"].lower() and q_lower not in dt["name"].lower():
                    continue
            if feeder_code and dt.get("feeder_code") != feeder_code.strip():
                continue
            cap = dt.get("capacity_kva")
            if min_capacity_kva is not None and (cap is None or cap < min_capacity_kva):
                continue
            if max_capacity_kva is not None and (cap is None or cap > max_capacity_kva):
                continue

            results.append({
                "code": dt["code"],
                "name": dt["name"],
                "feeder_code": dt.get("feeder_code"),
                "capacity_kva": dt.get("capacity_kva"),
                "total_meters": len(dt.get("meters", [])),
                "installed_count": dt.get("installed_count", 0),
                "faulty_count": dt.get("faulty_count", 0),
                "decommissioned_count": dt.get("decommissioned_count", 0),
            })

        results.sort(key=lambda x: x["code"])
        total = len(results)
        page_size = max(1, min(page_size, 100))
        total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1
        page = max(1, min(page, total_pages))

        offset = (page - 1) * page_size
        return results[offset : offset + page_size], total, total_pages

    def get_transformer_detail(self, dt_code: str) -> Optional[Dict[str, Any]]:
        """Fetches a DT with its connected meters and operational breakdown."""
        dt = self._transformers_by_code.get(dt_code)
        if not dt:
            return None

        attached_meters = [
            self._meters_by_id[m_id]
            for m_id in dt.get("meters", [])
            if m_id in self._meters_by_id
        ]

        # Determine hierarchy breadcrumb path from first attached meter
        hierarchy_path = None
        if attached_meters:
            h = attached_meters[0].get("hierarchy", {})
            parts = [
                h.get("zone", {}).get("name"),
                h.get("circle", {}).get("name"),
                h.get("division", {}).get("name"),
                h.get("subdivision", {}).get("name"),
                h.get("substation", {}).get("name"),
                h.get("feeder", {}).get("name"),
                dt["name"],
            ]
            hierarchy_path = " / ".join(p for p in parts if p)

        return {
            "code": dt["code"],
            "name": dt["name"],
            "feeder_code": dt.get("feeder_code"),
            "capacity_kva": dt.get("capacity_kva"),
            "hierarchy_path": hierarchy_path,
            "meter_counts": {
                "total": len(attached_meters),
                "installed": dt.get("installed_count", 0),
                "faulty": dt.get("faulty_count", 0),
                "decommissioned": dt.get("decommissioned_count", 0),
            },
            "meters": attached_meters,
        }

    def build_hierarchy_tree(self) -> List[Dict[str, Any]]:
        """
        Reconstructs the hierarchical tree:
        Zone -> Circle -> Division -> Subdivision -> Substation -> Feeder -> DT
        with aggregated meter counts computed at every level.
        """
        root_map: Dict[str, Any] = {}

        for m in self._meters:
            h = m.get("hierarchy", {})
            z = h.get("zone") or {"name": "Unassigned Zone", "code": "Z-NONE"}
            c = h.get("circle") or {"name": "Unassigned Circle", "code": "C-NONE"}
            d = h.get("division") or {"name": "Unassigned Division", "code": "D-NONE"}
            sd = h.get("subdivision") or {"name": "Unassigned Subdivision", "code": "SD-NONE"}
            ss = h.get("substation") or {"name": "Unassigned Substation", "code": "SS-NONE"}
            f = h.get("feeder") or {"name": "Unassigned Feeder", "code": "F-NONE"}
            dt = h.get("dt") or {"name": "Unassigned DT", "code": "DT-NONE"}

            status = m.get("status")

            def _get_or_create(parent_dict: Dict[str, Any], node_info: Dict[str, Any], level: str) -> Dict[str, Any]:
                code = node_info.get("code") or node_info.get("name") or "unknown"
                if code not in parent_dict:
                    parent_dict[code] = {
                        "name": node_info.get("name") or code,
                        "code": code,
                        "level": level,
                        "total_meters": 0,
                        "installed_meters": 0,
                        "faulty_meters": 0,
                        "decommissioned_meters": 0,
                        "_children": {},
                    }
                node = parent_dict[code]
                node["total_meters"] += 1
                if status == "Installed":
                    node["installed_meters"] += 1
                elif status == "Faulty":
                    node["faulty_meters"] += 1
                elif status == "Decommissioned":
                    node["decommissioned_meters"] += 1
                return node

            z_node = _get_or_create(root_map, z, "Zone")
            c_node = _get_or_create(z_node["_children"], c, "Circle")
            d_node = _get_or_create(c_node["_children"], d, "Division")
            sd_node = _get_or_create(d_node["_children"], sd, "Subdivision")
            ss_node = _get_or_create(sd_node["_children"], ss, "Substation")
            f_node = _get_or_create(ss_node["_children"], f, "Feeder")
            _get_or_create(f_node["_children"], dt, "DT")

        def _convert(children_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
            arr = []
            for v in children_dict.values():
                node = {
                    "name": v["name"],
                    "code": v["code"],
                    "level": v["level"],
                    "total_meters": v["total_meters"],
                    "installed_meters": v["installed_meters"],
                    "faulty_meters": v["faulty_meters"],
                    "decommissioned_meters": v["decommissioned_meters"],
                    "children": _convert(v["_children"]),
                }
                arr.append(node)
            arr.sort(key=lambda x: x["code"])
            return arr

        return _convert(root_map)

    def get_anomalies_report(self) -> Dict[str, Any]:
        """Compiles data anomalies, defect distributions, and high-risk transformers."""
        # Find high-risk transformers (>50% faulty meters)
        high_risk_dts: List[Dict[str, Any]] = []
        for dt in self._transformers:
            total = len(dt.get("meters", []))
            faulty = dt.get("faulty_count", 0)
            if total > 0 and (faulty / total) >= 0.5:
                high_risk_dts.append({
                    "dt_code": dt["code"],
                    "dt_name": dt["name"],
                    "feeder_code": dt.get("feeder_code"),
                    "total_meters": total,
                    "faulty_meters": faulty,
                    "fault_rate_pct": round((faulty / total) * 100.0, 1),
                })
        high_risk_dts.sort(key=lambda x: x["fault_rate_pct"], reverse=True)

        return {
            "total_meters_scanned": len(self._meters),
            "total_anomalies": len(self._anomalies),
            "anomalies": self._anomalies,
            "fleet_statistics": self._fleet_stats,
            "transformer_health": high_risk_dts,
        }
