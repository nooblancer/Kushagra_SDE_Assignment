# Urja Meter Ops — Protocol & Architecture Documentation

This document records the reverse-engineering findings of the legacy **Urja Meter Ops** portal (`https://urja-ops.flockenergy.tech`), including authentication mechanisms, cryptographic signatures, bulk export protocols, endpoints, schemas, and data quirks.

---

## 1. Authentication & Session Management

- **Mechanism**: SvelteKit Progressive Form Action + Better Auth Session Cookie (`__Secure-better-auth.session_token`).
- **Login Endpoint**: `POST /login`
- **Request Format**: `application/x-www-form-urlencoded`
  - Body: `email=<PORTAL_USERNAME>&password=<PORTAL_PASSWORD>`
- **Required Headers**:
  - `x-sveltekit-action: true` (Critical: signals SvelteKit to invoke the backend action instead of rendering HTML)
  - `origin: https://urja-ops.flockenergy.tech`
  - `referer: https://urja-ops.flockenergy.tech/login`
  - `accept: application/json`
- **Response**:
  - Sets cookie: `__Secure-better-auth.session_token=<token>; Path=/; Secure; HttpOnly; SameSite=Lax`
- **Session Lifecycle**:
  - Upstream responds with HTTP 401/403 when session is expired.
  - Client transparently re-authenticates and retries requests once.

---

## 2. Cryptographic Signing & Bulk Data Protocol

### 2.1 Cryptographic Signing Key
- **Endpoint**: `GET /portal/keys`
- **Response**:
  ```json
  {
    "data": {
      "signingSecret": "I3dZPPf5CgTp7JyGNMI8i6z8LFR7TmSR"
    }
  }
  ```
- **Purpose**: Provides the shared symmetric secret required to sign requests to the bulk export engine.

### 2.2 Signed Bulk Meter Export
- **Endpoint**: `GET /portal/export?page={page}`
- **Security Requirement**: Requests **must** be signed using **HMAC-SHA256**.
- **Signature Computation**:
  ```python
  timestamp = str(int(time.time()))
  signature_payload = f"GET\n/portal/export\npage={page}\n{timestamp}"
  signature = hmac.new(
      signing_secret.encode("utf-8"),
      signature_payload.encode("utf-8"),
      hashlib.sha256
  ).hexdigest()
  ```
- **Required Headers**:
  - `x-timestamp`: Unix epoch timestamp string
  - `x-signature`: Lowercase hexadecimal HMAC-SHA256 digest
- **Response Format**:
  ```json
  {
    "data": [
      {
        "meterId": "J100001",
        "serialNo": "SN-001042",
        "make": "Schneider Electric",
        "phaseType": "3-Phase",
        "installStatus": "Installed",
        "installType": "CT Operated",
        "build": "v2.1",
        "dtCode": "DT-001",
        "hierarchy": {
          "zone": {"name": "Jaipur Zone 1", "code": "Z-01"},
          "circle": {"name": "Circle 1", "code": "C-01"},
          "division": {"name": "Division 1", "code": "D-01"},
          "subdivision": {"name": "Subdivision 1", "code": "SD-01"},
          "substation": {"name": "Substation 1", "code": "SS-01"},
          "feeder": {"name": "Feeder 1", "code": "F-001"},
          "dt": {"name": "Malviya Nagar DT 1", "code": "DT-001"}
        },
        "geo": {
          "lat": "26.8530",
          "lng": "75.7600"
        }
      }
    ],
    "total": 403
  }
  ```

### 2.3 Distribution Transformers (DTs)
- **Endpoint**: `GET /portal/dts?page={page}`
- **Response Format**:
  ```json
  {
    "data": [
      {
        "code": "DT-001",
        "name": "Malviya Nagar DT 1",
        "feederCode": "F-001",
        "capacityKva": 100
      }
    ],
    "total": 40,
    "page": 1,
    "pageSize": 20
  }
  ```

### 2.4 Native Search Endpoint (Legacy Limitations)
- **Endpoint**: `GET /portal/meters/search?q={q}&page={page}`
- **Limitation**: Only performs simple substring matches against `meterId` and `serialNo`. It lacks capability for multi-attribute filtering (make, status, phase, feeder), geographic searches, or hierarchy traversal. This necessitated our **Local In-Memory Index Layer**.

### 2.5 Meter Energy Time-Series Telemetry
- **Endpoint**: `GET /portal/meters/{meter_id}/energy`
- **Payload**: Contains 337 chronological 30-minute interval readings (7 days of telemetry):
  ```json
  {
    "data": [
      {
        "timestamp": "23/06/2026 23:30",
        "kwh": "6850.32",
        "kvah": "7398.35",
        "voltR": "227"
      }
    ]
  }
  ```

---

## 3. Legacy Quirks, Inconsistencies & Data Anomalies

1. **HMAC Signature Canonical String**: The bulk export endpoint validates signatures against a newline-delimited string `GET\n/portal/export\npage={page}\n{timestamp}`. If the timestamp drifts or query parameters are formatted differently, requests fail with HTTP 401/403.
2. **Stringified Telemetry Values**: Interval readings use stringified floats (`"kwh": "6850.32"`, `"voltR": "227"`) and legacy key names (`voltR` instead of `voltage_r` or `V(R)`).
3. **Data Quality Anomalies in Fleet Dataset**:
   - **Missing & Zero Coordinates**: Certain meters have missing coordinates or coordinates at Null Island `(0.0, 0.0)`.
   - **Hierarchy & DT Mismatch**: Instances where top-level `meter.dtCode` does not match `meter.hierarchy.dt.code`.
   - **Orphaned DT References**: Meters pointing to DT codes not registered in `/portal/dts`.
   - **Duplicate Serial Numbers**: Shared manufacturer serial numbers across different meter IDs.
   - **SvelteKit Action Requirements**: Authentication strictly enforces `x-sveltekit-action: true` and Origin/Referer headers.
