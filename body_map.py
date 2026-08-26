"""Where each body-map region sits on the figure.

The body map was a list of words — "Head and face", "Chest" — which asks a
pupil to do the mapping in their own head. A figure lets them point. The same
geometry drives the screen and the printed pack, so a pupil filling it in on a
mentor's laptop and one filling in a photocopy are marking the same picture.

Coordinates are in a 100 x 200 box. Both renderers scale from that, so the
figure can be any size without the numbers drifting off their limbs.
"""

# Matched on the words in a checklist row, so a pack can label its rows however
# it likes ("Head - racing thoughts, blank mind") and still land on the head.
# Ordered: the first keyword found wins, so "hands" beats "whole body" on a row
# that happens to mention both.
REGIONS = [
    (("shoulder", "jaw", "neck"), (50, 44)),
    (("head", "face", "mind"), (50, 21)),
    (("chest", "heart", "breath"), (50, 60)),
    (("stomach", "tummy", "belly", "gut"), (50, 83)),
    (("hand", "arm", "fist"), (25, 86)),
    (("leg", "feet", "foot", "knee"), (40, 140)),
    # Sits on the corner of the dashed outline, clear of the figure — over a
    # shoulder it read as marking the shoulder.
    (("whole", "all over", "everywhere"), (88, 170)),
]

# The outline itself: simple parts rather than a traced silhouette, so it reads
# the same at handout size and doesn't look like a medical diagram.
PARTS = {
    "head":     ("circle", 50, 21, 14),
    "neck":     ("rect", 45.5, 34, 9, 8, 2),
    "torso":    ("rect", 31, 41, 38, 56, 10),
    "arm_l":    ("rect", 19, 45, 12, 48, 6),
    "arm_r":    ("rect", 69, 45, 12, 48, 6),
    "hips":     ("rect", 33, 94, 34, 13, 5),
    "leg_l":    ("rect", 35, 105, 13, 62, 6),
    "leg_r":    ("rect", 52, 105, 13, 62, 6),
}

VIEW_W, VIEW_H = 100, 200

# Small enough that the head still reads as a head with a number on it.
DOT_R = 7.5


def points_for(items):
    """Number each checklist row and place it on the figure.

    The number is the row's position in the list, so the figure and the tick
    list always agree even when a pack words its rows differently. A row that
    matches no region gets no marker rather than a wrong one.
    """
    points = []
    for index, text in enumerate(items, start=1):
        low = (text or "").lower()
        for keywords, (x, y) in REGIONS:
            if any(k in low for k in keywords):
                points.append({"n": index, "x": x, "y": y, "label": text,
                               "whole": keywords[0] == "whole"})
                break
    return points


def is_body_map(item):
    return (item or {}).get("figure") == "body-map"
