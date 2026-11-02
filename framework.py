"""
Phil - tiny WSGI micro-framework.

There is no network access to install Flask/Django in this environment, so
this is a small, dependency-free router built directly on wsgiref (stdlib).
It covers exactly what the app needs: GET/POST routes with path params,
cookies, form parsing, redirects, and Jinja2 template rendering (jinja2 is
already installed). Swapping this for a real framework later is a drop-in
replacement, every route handler just takes (request) and returns a Response.
"""

import re
import os
import json
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)


class Request:
    def __init__(self, environ):
        self.environ = environ
        self.method = environ["REQUEST_METHOD"].upper()
        self.path = environ.get("PATH_INFO", "/")
        self.query = parse_qs(environ.get("QUERY_STRING", ""))
        self.params = {}  # filled by router from path pattern
        self._cookies = SimpleCookie()
        self._cookies.load(environ.get("HTTP_COOKIE", ""))
        self._form = None
        self._raw_body = None

    def cookie(self, name):
        m = self._cookies.get(name)
        return m.value if m else None

    def header(self, name):
        """Reads a request header by its normal name, e.g. header('Stripe-Signature')."""
        key = "HTTP_" + name.upper().replace("-", "_")
        return self.environ.get(key)

    @property
    def raw_body(self):
        """The unparsed request body bytes, cached so it's only ever read
        once from wsgi.input regardless of how many times this or `form`
        is accessed. Needed wherever a caller must verify the exact bytes
        that were sent, e.g. Stripe webhook signature verification, which
        breaks if the body has been re-encoded via form parsing first."""
        if self._raw_body is None:
            try:
                length = int(self.environ.get("CONTENT_LENGTH") or 0)
            except ValueError:
                length = 0
            self._raw_body = self.environ["wsgi.input"].read(length) if length > 0 else b""
        return self._raw_body

    @property
    def form(self):
        if self._form is None:
            self._form = {}
            body = self.raw_body
            if body:
                content_type = self.environ.get("CONTENT_TYPE", "")
                if "application/json" in content_type:
                    try:
                        self._form = json.loads(body.decode("utf-8"))
                    except ValueError:
                        self._form = {}
                else:
                    parsed = parse_qs(body.decode("utf-8"))
                    self._form = {k: v[0] for k, v in parsed.items()}
        return self._form

    def field(self, name, default=""):
        v = self.form.get(name, default)
        return v


class Response:
    def __init__(self, body="", status="200 OK", headers=None, content_type="text/html; charset=utf-8"):
        self.body = body
        self.status = status
        self.headers = headers or []
        self.headers.append(("Content-Type", content_type))

    def set_cookie(self, name, value, max_age=None, path="/", httponly=True):
        cookie = SimpleCookie()
        cookie[name] = value
        cookie[name]["path"] = path
        if httponly:
            cookie[name]["httponly"] = True
        if max_age is not None:
            cookie[name]["max-age"] = max_age
        header_value = cookie[name].OutputString()
        self.headers.append(("Set-Cookie", header_value))

    def delete_cookie(self, name):
        self.set_cookie(name, "", max_age=0)


def redirect(location, status="302 Found"):
    return Response("", status=status, headers=[("Location", location)])


def render(template_name, **context):
    template = jinja_env.get_template(template_name)
    return Response(template.render(**context))


def pdf_response(path, filename, download=False):
    """Serves a PDF, either shown in the browser or saved to disk.

    inline is right for something being glanced at — a session record, a
    resource a mentor is about to print. attachment is right for anything a
    school keeps or forwards: a report or a certificate should land in
    Downloads with a sensible name, not sit in a tab until it is closed.

    A button labelled "Download" must send attachment, or it does not do what
    it says.
    """
    with open(path, "rb") as f:
        data = f.read()
    disposition = "attachment" if download else "inline"
    return Response(
        data,
        content_type="application/pdf",
        headers=[("Content-Disposition", f'{disposition}; filename="{filename}"')],
    )


class Router:
    def __init__(self):
        self.routes = []  # (method, compiled_regex, param_names, handler)

    def add(self, method, pattern, handler):
        param_names = re.findall(r"<(\w+)>", pattern)
        regex_pattern = re.sub(r"<(\w+)>", r"(?P<\1>[^/]+)", pattern)
        compiled = re.compile(f"^{regex_pattern}$")
        self.routes.append((method.upper(), compiled, handler))

    def get(self, pattern):
        def deco(fn):
            self.add("GET", pattern, fn)
            return fn
        return deco

    def post(self, pattern):
        def deco(fn):
            self.add("POST", pattern, fn)
            return fn
        return deco

    def dispatch(self, request):
        for method, compiled, handler in self.routes:
            if method != request.method:
                continue
            m = compiled.match(request.path)
            if m:
                request.params = m.groupdict()
                return handler(request)
        return Response("Not found", status="404 Not Found")


# File types the static handler labels explicitly. Anything else goes out as
# application/octet-stream, which browsers treat as "download this" — and some
# refuse outright in the place it is used: a captions track that is not
# text/vtt is ignored by Chrome, and an SVG favicon that is not image/svg+xml
# is not shown. So the type matters here rather than being cosmetic.
STATIC_TYPES = {
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".webmanifest": "application/manifest+json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".vtt": "text/vtt; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".pdf": "application/pdf",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
}

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _parse_range(header, size):
    """Turns a single-range Range header into (start, end) inclusive, or
    returns None to send the whole file, or "unsatisfiable".

    iPhones and Safari will not play a <video> unless the server answers
    "bytes=0-1" with 206 Partial Content: they probe with a tiny range before
    fetching anything, and a 200 with the whole file reads to them as a server
    that cannot stream. Only one range per request is supported; a multi-range
    request is answered with the whole file, which the spec allows."""
    if not header:
        return None
    m = _RANGE_RE.match(header.strip())
    if not m:
        return None
    start_s, end_s = m.groups()
    if start_s == "" and end_s == "":
        return None
    if start_s == "":
        # "bytes=-500" means the last 500 bytes.
        length = int(end_s)
        if length == 0:
            return "unsatisfiable"
        start, end = max(size - length, 0), size - 1
    else:
        start = int(start_s)
        end = int(end_s) if end_s else size - 1
        end = min(end, size - 1)
    if start >= size or start > end:
        return "unsatisfiable"
    return start, end


def _serve_static(environ, start_response, file_path):
    ctype = STATIC_TYPES.get(os.path.splitext(file_path)[1].lower(), "application/octet-stream")
    size = os.path.getsize(file_path)
    head_only = environ.get("REQUEST_METHOD", "GET").upper() == "HEAD"
    headers = [("Content-Type", ctype), ("Accept-Ranges", "bytes")]

    rng = _parse_range(environ.get("HTTP_RANGE"), size)
    if rng == "unsatisfiable":
        start_response("416 Range Not Satisfiable",
                       headers + [("Content-Range", f"bytes */{size}"), ("Content-Length", "0")])
        return [b""]

    if rng is None:
        start, end, status = 0, size - 1, "200 OK"
    else:
        start, end = rng
        status = "206 Partial Content"
        headers.append(("Content-Range", f"bytes {start}-{end}/{size}"))
    length = max(end - start + 1, 0)
    headers.append(("Content-Length", str(length)))
    start_response(status, headers)
    if head_only or length == 0:
        return [b""]
    with open(file_path, "rb") as f:
        f.seek(start)
        return [f.read(length)]


def make_wsgi_app(router, static_dir=None, static_prefix="/static/"):
    static_root = os.path.normpath(static_dir) if static_dir else None

    def app(environ, start_response):
        path = environ.get("PATH_INFO", "/")
        if static_root and path.startswith(static_prefix):
            rel = path[len(static_prefix):]
            file_path = os.path.normpath(os.path.join(static_root, rel))
            # Compare against the folder plus a separator: a bare startswith
            # would also accept a sibling folder such as "static2".
            inside = file_path.startswith(static_root + os.sep)
            method = environ.get("REQUEST_METHOD", "GET").upper()
            if inside and os.path.isfile(file_path) and method in ("GET", "HEAD"):
                return _serve_static(environ, start_response, file_path)
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [b"Not found"]

        request = Request(environ)
        try:
            response = router.dispatch(request)
        except Exception as exc:  # pragma: no cover - defensive
            import traceback
            traceback.print_exc()
            body = f"<pre>Internal error: {exc}</pre>".encode("utf-8")
            start_response("500 Internal Server Error", [("Content-Type", "text/html; charset=utf-8")])
            return [body]

        body = response.body
        if isinstance(body, str):
            body = body.encode("utf-8")
        start_response(response.status, response.headers)
        return [body]

    return app
