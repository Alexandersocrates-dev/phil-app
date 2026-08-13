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


def pdf_response(path, filename):
    with open(path, "rb") as f:
        data = f.read()
    return Response(
        data,
        content_type="application/pdf",
        headers=[("Content-Disposition", f'inline; filename="{filename}"')],
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


def make_wsgi_app(router, static_dir=None, static_prefix="/static/"):
    def app(environ, start_response):
        path = environ.get("PATH_INFO", "/")
        if static_dir and path.startswith(static_prefix):
            rel = path[len(static_prefix):]
            file_path = os.path.normpath(os.path.join(static_dir, rel))
            if file_path.startswith(static_dir) and os.path.isfile(file_path):
                ctype = "text/css" if file_path.endswith(".css") else "application/octet-stream"
                if file_path.endswith(".js"):
                    ctype = "application/javascript"
                with open(file_path, "rb") as f:
                    data = f.read()
                start_response("200 OK", [("Content-Type", ctype)])
                return [data]
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
