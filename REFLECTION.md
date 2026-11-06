# Engineering Reflection

This document reflects on the investigation, design decisions, trade-offs, and lessons learned while reverse-engineering and wrapping the **Urja Meter Ops** legacy portal into a production-grade API service.

---

### What assumptions did you make?
- **Symmetric Key Consistency (`/portal/keys`)**: Assumed that the cryptographic signing secret (`signingSecret`) returned by `/portal/keys` is stable across worker sessions and can be cached in-memory, requiring refresh only if upstream rejects signature verification with HTTP 401/403.
- **Fleet Scale & In-Memory Capacity**: Evaluated that the full distribution fleet consists of 403 smart meters and 40 Distribution Transformers. At this dataset scale (~500KB JSON payload), storing and indexing the fleet directly in memory using Python dictionaries provides instantaneous (<2ms) query response times with near-zero memory footprint, avoiding external database dependencies while remaining appropriately sized.
- **Data Anomaly Preservation**: Assumed that while downstream consumers need clean, normalized strings for filtering (e.g. standardizing "Schneider Electric" or "1-Phase"), data science and audit teams still require transparency into legacy data defects. Therefore, rather than discarding malformed records, the indexing engine flags anomalies (Null Island coordinates, duplicate serials, orphaned DT references) and documents them for audit purposes.
- **Telemetry Freshness vs Stampede Protection**: Assumed that real-time electrical telemetry changes frequently, but burst traffic requires buffering. We established a tiered TTL strategy: 10 minutes for static metadata/transformers, and 30 seconds for interval energy telemetry.

---

### Which part was the most difficult, and how did you get unstuck?
- **Reverse-Engineering the HMAC-SHA256 Signed Bulk Export**:
  - *Challenge*: The legacy portal frontend fetched bulk data through `GET /portal/export?page={page}`, but manual requests failed with HTTP 403 Forbidden. Inspecting DevTools revealed two custom headers: `x-timestamp` and `x-signature`.
  - *Resolution*: Investigated network calls during application load to discover `GET /portal/keys` returning a 32-character symmetric secret. Decompiled and analyzed the client bundle to deduce the canonical signing string: `GET\n/portal/export\npage={page}\n{timestamp}`. Implementing HMAC-SHA256 signing unlocked the full 403-meter dataset and transformed the entire architecture from fragile single-meter web scraping into a robust bulk-sync model.
- **SvelteKit Action Authentication & Devalue Deserialization**:
  - *Challenge*: The authentication endpoint rejected standard POST requests, and page metadata (`/meters/{id}/__data.json`) contained integer arrays instead of plain strings.
  - *Resolution*: Identified that the portal runs on SvelteKit with progressive enhancement, requiring the `x-sveltekit-action: true` header alongside CSRF Origin/Referer verification. Built an automated devalue resolver to dereference index pointers into human-readable hierarchy nodes.

---

### If you had another day, what would you improve?
- **Distributed Cache & Storage (Redis / SQLite WAL)**: The current in-memory index lives in process memory. If deployed with multiple Uvicorn worker processes (`--workers 4`), each worker maintains its own copy. In a production cluster, backing the index with Redis or an embedded SQLite instance in WAL mode would synchronize state across workers and persist restarts.
- **Webhook / WebSocket Change Data Capture (CDC)**: Implement a streaming change feed so that when upstream telemetry updates or field engineers update meter statuses, updates are pushed directly to subscribed client dashboards.
- **Historical Telemetry Aggregation Engine**: Add server-side analytical aggregations (e.g. daily/weekly rollups, peak load hours, and voltage sag detection) directly on top of the 337 interval readings.

---

### What mistake did you make while solving this (there's always one)?
- **Initial Single-Meter Scrape Paradigm**: In the initial design, we treated each meter as an independent lookup through `/portal/meters/{id}/*`. While functional, querying meters in isolation resulted in $O(N)$ HTTP roundtrips, couldn't support multi-attribute filtering, and risked rate limits. Discovering the HMAC `/portal/export` endpoint forced us to tear down the monolithic fetcher and rebuild the service around an in-memory index layer—a trade-off that ultimately made the system infinitely more scalable.
- **Zero-Value Truthiness Trap**: When writing coordinate validation, using Python's `lat_val or raw_geo.get(...)` caused coordinates with value `0.0` (Null Island) to be evaluated as falsy, misclassifying them as missing coordinates rather than explicit invalid values. Unit testing uncovered this and prompted an explicit `if key in dict` check.

---

### If you were reviewing your own submission, what would you criticise?
- **Coupling to Unversioned Internal Endpoints**: While our API is clean and RESTful, its upstream dependency relies on internal portal endpoints (`/portal/export`, `/portal/keys`, `/meters/{id}/__data.json`). If the utility updates their portal framework or alters the HMAC signing format, upstream ingestion will break until updated.
- **Single-Point Ingestion Latency on Startup**: The service eagerly syncs on startup. If the upstream portal experiences high latency during cold-start, API boot time can stretch by 2-3 seconds. Implementing background non-blocking hydration would improve startup responsiveness.
