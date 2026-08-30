"""Where each level sits on the anger thermometer.

The thermometer was a table of five rows, which asks a pupil to hold "7-8" and
"about to lose control" together in their head. A drawn scale lets them point at
a height. The same geometry drives the screen and the printed pack, so a pupil
pointing at a mentor's laptop and one marking a photocopy are using the same
picture.

Coordinates are in a 100 x 200 box, as in body_map, so both renderers scale from
that and the bands stay on the tube at any size. The box holds the FIGURE only,
again as in body_map: the level names sit beside it in the renderer's own units,
because 8mm of gutter on a printed sheet and a flex gap on screen are not the
same measurement and pretending otherwise put the whole figure in the left third
of the page.
"""

# Bottom to top: a thermometer fills upward, and the pupil reads it that way.
# Each band is (label, range, what it feels like, what to do).
LEVELS = [
    ("Calm", "1-2", "Totally settled", "Nothing needed"),
    ("Annoyed", "3-4", "Slightly irritated", "You can act on this one"),
    ("Frustrated", "5-6", "Building now", "The gap is still open"),
    ("Angry", "7-8", "Hard to think past it", "STOP goes here"),
    ("Furious", "9-10", "About to lose control", "Leave, then talk later"),
]

VIEW_W, VIEW_H = 100, 200

# The tube, and the bulb under it. The tube is a little under half the width of
# the box: narrower than this and it reads as a strip with writing next to it
# rather than as a thermometer.
TUBE_X, TUBE_W = 28, 44
TUBE_TOP, TUBE_BOTTOM = 10, 152
TUBE_R = TUBE_W / 2.0          # a full dome on top; the foot is square

# The bulb is wider than the tube, and TUBE_BOTTOM is set just inside it: the
# sides of the tube run past the bulb's edge (the circle is 23 wide at that
# depth against the tube's 22) so the two meet with no gap and no seam, and the
# bulb's arc reappears just outside the tube where it should.
BULB_CX, BULB_CY, BULB_R = 50, 168, 28

# One ramp, cool at the bulb and hot at the top, used by both renderers so the
# printed sheet and the screen can never drift apart. Every band is filled: a
# thermometer fills from the bottom, so shading only the top of it says the
# opposite of what the picture is for.
BAND_FILLS = ["#D9EAE0", "#F3E7C2", "#EFC98B", "#DE9A6A", "#C4623F"]
# Numerals sit on the band, so the top two need to flip to white to stay legible.
BAND_INKS = ["#2C2C2A", "#2C2C2A", "#2C2C2A", "#FFFFFF", "#FFFFFF"]

BULB_FILL = BAND_FILLS[0]      # the reservoir continues the coolest band
OUTLINE = "#B9B4A4"            # a shade darker than BORDER: the fills are strong


def bands():
    """Each level as a band on the tube, bottom to top.

    Returns dicts with the band's box in view coordinates and the text that goes
    beside it, so a renderer only has to scale and draw.
    """
    height = (TUBE_BOTTOM - TUBE_TOP) / float(len(LEVELS))
    out = []
    for index, (name, span, feels, do) in enumerate(LEVELS):
        # index 0 is the coolest, and sits at the bottom of the tube.
        bottom = TUBE_BOTTOM - index * height
        out.append({
            "n": index + 1,
            "name": name,
            "span": span,
            "feels": feels,
            "do": do,
            "x": TUBE_X,
            "w": TUBE_W,
            "top": bottom - height,
            "bottom": bottom,
            "mid": bottom - height / 2.0,
            "fill": BAND_FILLS[index],
            "ink": BAND_INKS[index],
            # The top two are where a mentor is watching for trouble. This marks
            # the LABEL beside the tube, not the tube itself.
            "hot": index >= 3,
        })
    return out


def is_thermometer(item):
    return (item or {}).get("figure") == "thermometer"


def label_track():
    """Where the label column sits, as percentages of the figure's height.

    The tube is only the top three-quarters of the 100x200 box - the bulb takes
    the rest - so a list stretched over the whole figure would sit a band low.
    Returned from here rather than written into the stylesheet, so moving the
    tube moves the labels with it.
    """
    top = 100.0 * TUBE_TOP / VIEW_H
    height = 100.0 * (TUBE_BOTTOM - TUBE_TOP) / VIEW_H
    return top, height


def tube_path_d():
    """The tube as an SVG path: domed top, square foot.

    Used for both the clip and the outline, and mirrored by the print renderer,
    so the two draw one shape rather than two that happen to look alike.
    """
    return ("M %g %g A %g %g 0 0 1 %g %g L %g %g L %g %g Z"
            % (TUBE_X, TUBE_TOP + TUBE_R, TUBE_R, TUBE_R,
               TUBE_X + TUBE_W, TUBE_TOP + TUBE_R,
               TUBE_X + TUBE_W, TUBE_BOTTOM, TUBE_X, TUBE_BOTTOM))


def svg(uid="therm", width=None):
    """The tube, bulb and bands as an SVG fragment.

    Screen side of the same geometry. The caller places the level names beside
    this in HTML, so the text wraps and reflows the way the rest of a resource
    does instead of being baked into the drawing at a fixed size.
    """
    w = 'width="%s" ' % width if width else ""
    parts = [
        '<svg %sviewBox="0 0 %d %d" class="therm-fig" role="img" '
        'aria-label="Anger thermometer, calm at the bottom to furious at the top" '
        'xmlns="http://www.w3.org/2000/svg">' % (w, VIEW_W, VIEW_H),
        '<defs><clipPath id="%s-tube"><path d="%s"/></clipPath></defs>'
        % (uid, tube_path_d()),
        # Bulb first, so the foot of the tube sits over it.
        '<circle cx="%g" cy="%g" r="%g" fill="%s" stroke="%s" stroke-width="1.5"/>'
        % (BULB_CX, BULB_CY, BULB_R, BULB_FILL, OUTLINE),
        '<g clip-path="url(#%s-tube)">' % uid,
    ]
    rows = bands()
    for b in rows:
        # Clipped to the tube, so the top band takes the dome and the bottom one
        # runs square into the bulb, covering the arc that crosses it.
        parts.append(
            '<rect x="%g" y="%g" width="%g" height="%g" fill="%s"/>'
            % (b["x"], b["top"], b["w"], b["bottom"] - b["top"], b["fill"]))
        if b is not rows[-1]:
            parts.append(
                '<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="%s" stroke-width="1"/>'
                % (b["x"], b["top"], b["x"] + b["w"], b["top"], OUTLINE))
    parts.append('</g>')
    # Sides and dome only. A closed outline would draw the tube's foot across
    # the inside of the bulb, which is what made the bulb read as a separate
    # circle parked underneath.
    parts.append(
        '<path d="M %g %g L %g %g A %g %g 0 0 1 %g %g L %g %g" fill="none" '
        'stroke="%s" stroke-width="1.5"/>'
        % (TUBE_X, TUBE_BOTTOM, TUBE_X, TUBE_TOP + TUBE_R, TUBE_R, TUBE_R,
           TUBE_X + TUBE_W, TUBE_TOP + TUBE_R, TUBE_X + TUBE_W, TUBE_BOTTOM,
           OUTLINE))
    for b in rows:
        parts.append(
            '<text x="%g" y="%g" text-anchor="middle" font-size="13" '
            'font-weight="700" fill="%s">%s</text>'
            % (BULB_CX, b["mid"] + 4.5, b["ink"], b["span"]))
    parts.append('</svg>')
    return "".join(parts)
