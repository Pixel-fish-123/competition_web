"""CSRF protection middleware.

Applies globally (added via app.add_middleware). For non-GET/HEAD/OPTIONS
requests that carry an Origin header, the request is rejected with 403 unless
the Origin is:

- same-site: scheme + host/port match the request URL, or
- in the explicit allow-list (local frontend dev servers).
"""

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

ALLOWED_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://cy2rookiecup.xyz",
    "https://www.cy2rookiecup.xyz",
}


def _normalize_netloc(netloc: str) -> str:
    """Strip a redundant default port so http://host and http://host:80 match."""
    if netloc.endswith(":80") or netloc.endswith(":443"):
        return netloc.rsplit(":", 1)[0]
    return netloc


def _origin_allowed(request: Request, origin: str) -> bool:
    if origin in ALLOWED_ORIGINS:
        return True
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    # Same-site: scheme + normalized host[:port] must equal the request URL.
    return (
        parsed.scheme == request.url.scheme
        and _normalize_netloc(parsed.netloc) == _normalize_netloc(request.url.netloc)
    )


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in SAFE_METHODS:
            origin = request.headers.get("origin")
            if origin and not _origin_allowed(request, origin):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF 校验失败：Origin 不被允许"},
                )
        return await call_next(request)
