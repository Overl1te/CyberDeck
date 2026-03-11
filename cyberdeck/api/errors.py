from fastapi import APIRouter

from ..errors import catalog_items


router = APIRouter()


@router.get("/api/errors/catalog")
def errors_catalog(q: str = "", limit: int = 200):
    """Return searchable error catalog used by launcher/web/mobile clients."""
    rows = catalog_items(query=q, limit=limit)
    return {
        "status": "ok",
        "query": str(q or "").strip(),
        "total": len(rows),
        "items": rows,
    }

