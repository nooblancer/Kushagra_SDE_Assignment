import pytest
from app.services.index_service import LocalIndexService, _haversine_distance_km


def test_haversine_distance():
    # Distance between Jaipur center (26.9124, 75.7873) and Mansarovar (26.8530, 75.7600) is ~7.1 km
    dist = _haversine_distance_km(26.9124, 75.7873, 26.8530, 75.7600)
    assert 6.5 < dist < 7.8


def test_index_service_querying_and_anomalies():
    service = LocalIndexService(ttl_seconds=600.0)

    mock_dts = [
        {"code": "DT-001", "name": "Civil Lines DT 1", "feederCode": "F-001", "capacityKva": 100},
        {"code": "DT-002", "name": "Mansarovar DT 2", "feederCode": "F-002", "capacityKva": 200},
    ]

    mock_meters = [
        {
            "meterId": "MTR-101",
            "serialNo": "SN-001",
            "make": "Schneider Electric",
            "phaseType": "3-Phase",
            "installStatus": "Installed",
            "installType": "CT Operated",
            "build": "v1.2",
            "dtCode": "DT-001",
            "geo": {"lat": 26.8530, "lng": 75.7600},
            "hierarchy": {
                "zone": {"name": "Jaipur Zone", "code": "Z-01"},
                "circle": {"name": "Jaipur Circle", "code": "C-01"},
                "division": {"name": "South Division", "code": "D-01"},
                "subdivision": {"name": "Mansarovar SD", "code": "SD-01"},
                "substation": {"name": "220kV Mansarovar SS", "code": "SS-01"},
                "feeder": {"name": "Feeder 1", "code": "F-001"},
                "dt": {"name": "Civil Lines DT 1", "code": "DT-001"},
            },
        },
        {
            "meterId": "MTR-102",
            "serialNo": "SN-002",
            "make": "Secure Meters",
            "phaseType": "1-Phase",
            "installStatus": "Faulty",
            "installType": "Whole Current",
            "build": "v1.0",
            "dtCode": "DT-001",
            "geo": {"lat": 0.0, "lng": 0.0},  # Anomaly: null island
            "hierarchy": {
                "zone": {"name": "Jaipur Zone", "code": "Z-01"},
                "circle": {"name": "Jaipur Circle", "code": "C-01"},
                "division": {"name": "South Division", "code": "D-01"},
                "subdivision": {"name": "Mansarovar SD", "code": "SD-01"},
                "substation": {"name": "220kV Mansarovar SS", "code": "SS-01"},
                "feeder": {"name": "Feeder 1", "code": "F-001"},
                "dt": {"name": "Civil Lines DT 1", "code": "DT-001"},
            },
        },
        {
            "meterId": "MTR-103",
            "serialNo": "SN-001",  # Anomaly: duplicate serial
            "make": "Genius",
            "phaseType": "3-Phase",
            "installStatus": "Installed",
            "installType": "CT Operated",
            "build": "v1.1",
            "dtCode": "DT-999",  # Anomaly: orphaned DT
            "geo": {"lat": 26.8600, "lng": 75.7700},
            "hierarchy": {
                "dt": {"name": "Ghost DT", "code": "DT-999"},
            },
        },
    ]

    service._process_and_index(mock_dts, mock_meters)

    # 1. Verify index counts
    stats = service.get_index_stats()
    assert stats["indexed_meters"] == 3
    assert stats["indexed_transformers"] == 2

    # 2. Verify anomalies detection
    report = service.get_anomalies_report()
    categories = [a["category"] for a in report["anomalies"]]
    assert "null_island_coordinates" in categories
    assert "duplicate_serial_number" in categories
    assert "orphaned_dt_reference" in categories

    # 3. Verify multi-attribute filtering
    items, total, _ = service.query_meters(make="Schneider Electric")
    assert total == 1
    assert items[0]["meter_id"] == "MTR-101"

    # 4. Verify geospatial search
    geo_items, geo_total, _ = service.query_meters(
        near_lat=26.8530, near_lng=75.7600, radius_km=5.0
    )
    assert geo_total == 2  # MTR-101 and MTR-103 (MTR-102 excluded because null island coords were discarded)
    assert geo_items[0]["meter_id"] == "MTR-101"
    assert geo_items[0]["distance_km"] == 0.0

    # 5. Verify hierarchy tree reconstruction
    tree = service.build_hierarchy_tree()
    assert len(tree) >= 1
    assert tree[0]["level"] == "Zone"

