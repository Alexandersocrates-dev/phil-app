"""
Draws the card motifs into a PDF.

Why this exists: the printed pack had its artwork switched off because svglib
rendered each motif at its native size rather than inside the box it was given,
so illustrations landed on top of the card text. svglib cannot be installed or
tested in the environment where this was written, and guessing at a fix that
cannot be run is how the original bug survived.

This renders the motifs directly with reportlab instead, using only the SVG
subset the sprite actually uses — verified against all 100 symbols:

    elements    path, circle, rect, text, g
    commands    M m L l H h V v C c S s Q q T t A a Z z

Everything is drawn inside a saved graphics state with an explicit scale, so a
motif can never paint outside the box it is given. That was the original fault.
"""
import math
import re

VIEWBOX_W = 100.0
VIEWBOX_H = 74.0

_NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")
_CMD = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])")


def _numbers(chunk):
    return [float(n) for n in _NUM.findall(chunk)]


def _attr(tag, name, default=None):
    m = re.search(r'%s="([^"]*)"' % re.escape(name), tag)
    return m.group(1) if m else default


def _arc_to_cubics(x0, y0, rx, ry, rotation, large_arc, sweep, x1, y1):
    """An elliptical arc as a series of cubic curves.

    Seven motifs use arcs. reportlab has no arc-to primitive that matches SVG's
    endpoint parameterisation, so the standard conversion from the SVG
    specification's implementation notes is used."""
    if rx == 0 or ry == 0 or (x0 == x1 and y0 == y1):
        return [("line", x1, y1)]
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(rotation)
    cos_p, sin_p = math.cos(phi), math.sin(phi)

    dx2, dy2 = (x0 - x1) / 2.0, (y0 - y1) / 2.0
    x1p = cos_p * dx2 + sin_p * dy2
    y1p = -sin_p * dx2 + cos_p * dy2

    # Scale the radii up if they are too small to span the two points.
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:
        scale = math.sqrt(lam)
        rx, ry = rx * scale, ry * scale

    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    factor = math.sqrt(max(num / den, 0.0))
    if large_arc == sweep:
        factor = -factor
    cxp = factor * rx * y1p / ry
    cyp = -factor * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (x0 + x1) / 2.0
    cy = sin_p * cxp + cos_p * cyp + (y0 + y1) / 2.0

    def angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        mag = math.sqrt((ux * ux + uy * uy) * (vx * vx + vy * vy))
        if mag == 0:
            return 0.0
        a = math.acos(max(-1.0, min(1.0, dot / mag)))
        return -a if (ux * vy - uy * vx) < 0 else a

    theta1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta = angle((x1p - cxp) / rx, (y1p - cyp) / ry,
                  (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi

    # One cubic per quarter turn keeps the error invisible at this size.
    segments = max(1, int(math.ceil(abs(delta) / (math.pi / 2))))
    out = []
    step = delta / segments
    alpha = 4.0 / 3.0 * math.tan(step / 4.0)
    t1 = theta1
    px, py = x0, y0
    for _ in range(segments):
        t2 = t1 + step
        cos1, sin1 = math.cos(t1), math.sin(t1)
        cos2, sin2 = math.cos(t2), math.sin(t2)

        def point(cos_t, sin_t):
            return (cos_p * rx * cos_t - sin_p * ry * sin_t + cx,
                    sin_p * rx * cos_t + cos_p * ry * sin_t + cy)

        def deriv(cos_t, sin_t):
            return (-cos_p * rx * sin_t - sin_p * ry * cos_t,
                    -sin_p * rx * sin_t + cos_p * ry * cos_t)

        ex, ey = point(cos2, sin2)
        d1x, d1y = deriv(cos1, sin1)
        d2x, d2y = deriv(cos2, sin2)
        out.append(("curve", px + alpha * d1x, py + alpha * d1y,
                    ex - alpha * d2x, ey - alpha * d2y, ex, ey))
        px, py = ex, ey
        t1 = t2
    return out


def _quad_to_cubic(x0, y0, qx, qy, x1, y1):
    """A quadratic curve as a cubic — reportlab only draws cubics."""
    c1x = x0 + 2.0 / 3.0 * (qx - x0)
    c1y = y0 + 2.0 / 3.0 * (qy - y0)
    c2x = x1 + 2.0 / 3.0 * (qx - x1)
    c2y = y1 + 2.0 / 3.0 * (qy - y1)
    return c1x, c1y, c2x, c2y


def _walk_path(d):
    """Yields drawing operations from a path's `d` attribute.

    Coordinates come out in SVG space (y increasing downward); the caller
    flips them. Emits ('move', x, y), ('line', x, y),
    ('curve', c1x, c1y, c2x, c2y, x, y) and ('close',)."""
    tokens = [t for t in _CMD.split(d) if t.strip()]
    x = y = 0.0
    start_x = start_y = 0.0
    prev_c2 = None      # for S/s
    prev_q = None       # for T/t
    cmd = None
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if _CMD.fullmatch(token):
            cmd = token
            i += 1
            args = _numbers(tokens[i]) if i < len(tokens) and not _CMD.fullmatch(tokens[i]) else []
            if args:
                i += 1
        else:
            args = _numbers(token)
            i += 1
            # An implicit repeat: M becomes L, m becomes l.
            if cmd == "M":
                cmd = "L"
            elif cmd == "m":
                cmd = "l"

        rel = cmd.islower()
        c = cmd.upper()

        def take(n):
            """Consume n numbers at a time, so `L 1 2 3 4` draws two lines."""
            for k in range(0, len(args) - n + 1, n):
                yield args[k:k + n]

        if c == "Z":
            yield ("close",)
            x, y = start_x, start_y
            prev_c2 = prev_q = None
            continue

        for a in take({"M": 2, "L": 2, "H": 1, "V": 1, "C": 6,
                       "S": 4, "Q": 4, "T": 2, "A": 7}[c]):
            if c == "M":
                x, y = (x + a[0], y + a[1]) if rel else (a[0], a[1])
                start_x, start_y = x, y
                yield ("move", x, y)
                prev_c2 = prev_q = None
            elif c == "L":
                x, y = (x + a[0], y + a[1]) if rel else (a[0], a[1])
                yield ("line", x, y)
                prev_c2 = prev_q = None
            elif c == "H":
                x = x + a[0] if rel else a[0]
                yield ("line", x, y)
                prev_c2 = prev_q = None
            elif c == "V":
                y = y + a[0] if rel else a[0]
                yield ("line", x, y)
                prev_c2 = prev_q = None
            elif c == "C":
                if rel:
                    c1, c2, end = (x + a[0], y + a[1]), (x + a[2], y + a[3]), (x + a[4], y + a[5])
                else:
                    c1, c2, end = (a[0], a[1]), (a[2], a[3]), (a[4], a[5])
                yield ("curve", c1[0], c1[1], c2[0], c2[1], end[0], end[1])
                prev_c2 = c2
                prev_q = None
                x, y = end
            elif c == "S":
                # The first control point mirrors the previous curve's second.
                c1 = (2 * x - prev_c2[0], 2 * y - prev_c2[1]) if prev_c2 else (x, y)
                if rel:
                    c2, end = (x + a[0], y + a[1]), (x + a[2], y + a[3])
                else:
                    c2, end = (a[0], a[1]), (a[2], a[3])
                yield ("curve", c1[0], c1[1], c2[0], c2[1], end[0], end[1])
                prev_c2 = c2
                prev_q = None
                x, y = end
            elif c == "Q":
                if rel:
                    q, end = (x + a[0], y + a[1]), (x + a[2], y + a[3])
                else:
                    q, end = (a[0], a[1]), (a[2], a[3])
                c1x, c1y, c2x, c2y = _quad_to_cubic(x, y, q[0], q[1], end[0], end[1])
                yield ("curve", c1x, c1y, c2x, c2y, end[0], end[1])
                prev_q = q
                prev_c2 = None
                x, y = end
            elif c == "A":
                end = (x + a[5], y + a[6]) if rel else (a[5], a[6])
                for op in _arc_to_cubics(x, y, a[0], a[1], a[2],
                                         bool(a[3]), bool(a[4]), end[0], end[1]):
                    yield op
                prev_c2 = prev_q = None
                x, y = end
            elif c == "T":
                q = (2 * x - prev_q[0], 2 * y - prev_q[1]) if prev_q else (x, y)
                end = (x + a[0], y + a[1]) if rel else (a[0], a[1])
                c1x, c1y, c2x, c2y = _quad_to_cubic(x, y, q[0], q[1], end[0], end[1])
                yield ("curve", c1x, c1y, c2x, c2y, end[0], end[1])
                prev_q = q
                prev_c2 = None
                x, y = end


def _colour(value, default=None):
    """SVG colour to a reportlab colour, or None for 'none'."""
    from reportlab.lib.colors import HexColor
    if value in (None, "", "none"):
        return default
    if value == "currentColor":
        return "CURRENT"
    if value.startswith("#"):
        hexpart = value[1:]
        # reportlab reads "#fff" as three decimal digits, which comes out blue.
        # Expand shorthand to the six-digit form first.
        if len(hexpart) == 3:
            hexpart = "".join(ch * 2 for ch in hexpart)
        try:
            return HexColor("#" + hexpart)
        except Exception:
            return default
    return default


def draw_symbol(c, body, x, y, width, height, colour):
    """Draws one motif's contents into the box at (x, y) with the given size.

    (x, y) is the bottom-left corner, as everywhere else in reportlab. The whole
    motif is clipped to a scale that fits the box, so it cannot paint over
    neighbouring content — the failure that switched this feature off."""
    from reportlab.lib.colors import HexColor

    scale = min(width / VIEWBOX_W, height / VIEWBOX_H)
    draw_w, draw_h = VIEWBOX_W * scale, VIEWBOX_H * scale
    ox = x + (width - draw_w) / 2.0
    oy = y + (height - draw_h) / 2.0

    def sx(v):
        return ox + v * scale

    def sy(v):
        # SVG y runs downward; PDF y runs upward.
        return oy + (VIEWBOX_H - v) * scale

    def resolve(value, default=None):
        col = _colour(value, default)
        return colour if col == "CURRENT" else col

    c.saveState()
    for m in re.finditer(r"<(path|circle|rect|text|g)\b([^>]*?)(/?)>", body):
        tag, attrs = m.group(1), m.group(2)
        stroke = resolve(_attr(attrs, "stroke"), None)
        fill = resolve(_attr(attrs, "fill"), None)
        sw = float(_attr(attrs, "stroke-width", "0") or 0) * scale
        opacity = float(_attr(attrs, "opacity", "1") or 1)

        if tag == "g":
            continue  # groups here only carry inherited paint, handled per shape

        c.saveState()
        if opacity < 1:
            c.setFillAlpha(opacity)
            c.setStrokeAlpha(opacity)
        if stroke is not None:
            c.setStrokeColor(stroke)
            c.setLineWidth(max(sw, 0.2))
        if _attr(attrs, "stroke-linecap") == "round":
            c.setLineCap(1)
        if _attr(attrs, "stroke-linejoin") == "round":
            c.setLineJoin(1)
        dash = _attr(attrs, "stroke-dasharray")
        if dash:
            c.setDash([float(v) * scale for v in _numbers(dash)])
        if fill is not None:
            c.setFillColor(fill)

        do_fill = 1 if fill is not None else 0
        do_stroke = 1 if stroke is not None else 0

        if tag == "circle":
            cx, cy = float(_attr(attrs, "cx", 0)), float(_attr(attrs, "cy", 0))
            r = float(_attr(attrs, "r", 0)) * scale
            c.circle(sx(cx), sy(cy), r, stroke=do_stroke, fill=do_fill)
        elif tag == "rect":
            rx0, ry0 = float(_attr(attrs, "x", 0)), float(_attr(attrs, "y", 0))
            w = float(_attr(attrs, "width", 0)) * scale
            h = float(_attr(attrs, "height", 0)) * scale
            rr = float(_attr(attrs, "rx", 0) or 0) * scale
            # SVG rect y is the top edge; reportlab wants the bottom.
            by = sy(ry0) - h
            if rr:
                c.roundRect(sx(rx0), by, w, h, rr, stroke=do_stroke, fill=do_fill)
            else:
                c.rect(sx(rx0), by, w, h, stroke=do_stroke, fill=do_fill)
        elif tag == "text":
            tx, ty = float(_attr(attrs, "x", 0)), float(_attr(attrs, "y", 0))
            size = float(_attr(attrs, "font-size", "10") or 10) * scale
            weight = _attr(attrs, "font-weight", "")
            anchor = _attr(attrs, "text-anchor", "start")
            after = body[m.end():]
            label = after.split("<", 1)[0].strip()
            if label:
                c.setFont("Helvetica-Bold" if weight in ("700", "bold") else "Helvetica", size)
                c.setFillColor(fill if fill is not None else colour)
                if anchor == "middle":
                    c.drawCentredString(sx(tx), sy(ty), label)
                else:
                    c.drawString(sx(tx), sy(ty), label)
        elif tag == "path":
            d = _attr(attrs, "d")
            if d:
                p = c.beginPath()
                started = False
                for op in _walk_path(d):
                    if op[0] == "move":
                        p.moveTo(sx(op[1]), sy(op[2]))
                        started = True
                    elif op[0] == "line" and started:
                        p.lineTo(sx(op[1]), sy(op[2]))
                    elif op[0] == "curve" and started:
                        p.curveTo(sx(op[1]), sy(op[2]), sx(op[3]), sy(op[4]),
                                  sx(op[5]), sy(op[6]))
                    elif op[0] == "close" and started:
                        p.close()
                if started:
                    c.drawPath(p, stroke=do_stroke, fill=do_fill)
        c.restoreState()
    c.restoreState()
    return True
