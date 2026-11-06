"""
Utility script to generate and export the OpenAPI (3.x) specification JSON
directly from the FastAPI application metadata and route definitions.
"""
import json
from pathlib import Path
from app.main import app

OUTPUT_FILE = Path(__file__).parent / "openapi.json"


def export_openapi() -> None:
    schema = app.openapi()
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
    print(f"Successfully exported OpenAPI schema to: {OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    export_openapi()

