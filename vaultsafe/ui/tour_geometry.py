"""Placement and connected callout outline in client pixels."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height

    def intersect(self, other):
        x, y = max(self.x, other.x), max(self.y, other.y)
        right, bottom = min(self.right, other.right), min(self.bottom, other.bottom)
        if right > x and bottom > y:
            return Rect(x, y, right - x, bottom - y)
        return None


@dataclass(frozen=True)
class Placement:
    body: Rect
    side: str
    pointer: int
    depth: int

    @property
    def window(self):
        body, side, depth = self.body, self.side, self.depth
        return Rect(body.x - (depth if side == "right" else 0),
                    body.y - (depth if side == "below" else 0),
                    body.width + (depth if side in ("left", "right") else 0),
                    body.height + (depth if side in ("above", "below") else 0))


def choose_placement(client, target, measure, *, sides, scale):
    margin, gap, depth = (round(size * scale) for size in (10, 7, 16))
    minimum, normal = round(142 * scale), round(340 * scale)
    left, top = client.x + margin, client.y + margin
    right, bottom = client.right - margin, client.bottom - margin
    slots = {
        "right": Rect(target.right + gap + depth, top, right - target.right - gap - depth, bottom - top),
        "left": Rect(left, top, target.x - gap - depth - left, bottom - top),
        "below": Rect(left, target.bottom + gap + depth, right - left, bottom - target.bottom - gap - depth),
        "above": Rect(left, top, right - left, target.y - gap - depth - top),
    }
    candidates = []
    for priority, side in enumerate(sides):
        space = slots[side]
        width = min(space.width, normal)
        if width < minimum:
            continue
        height = measure(width)
        if height > space.height:
            continue
        cx, cy = target.x + target.width // 2, target.y + target.height // 2
        if side in ("left", "right"):
            x = space.right - width if side == "left" else space.x
            y = max(space.y, min(cy - height // 2, space.bottom - height))
            pointer = cy - y
        else:
            x = max(space.x, min(cx - width // 2, space.right - width))
            y = space.bottom - height if side == "above" else space.y
            pointer = cx - x
        # A wider card is easier to scan. Prefer the reference side when widths are close.
        score = width - priority * round(24 * scale)
        candidates.append((score, Placement(Rect(x, y, width, height), side, pointer, depth)))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def callout_outline(placement, radius, half_base):
    """One clockwise polygon includes the four curves and the pointer."""
    body, window = placement.body, placement.window
    x, y = body.x - window.x + 1, body.y - window.y + 1
    right, bottom = x + body.width - 2, y + body.height - 2
    side = placement.side
    horizontal = side in ("above", "below")
    offset = (y if not horizontal else x) + placement.pointer - 1
    low, high = (x, right) if horizontal else (y, bottom)
    inset = radius + half_base + 2
    pointer = max(low + inset, min(offset, high - inset))
    points = []

    def arc(cx, cy, start):
        for angle in range(start, start + 91, 10):
            radians = math.radians(angle)
            points.append((round(cx + radius * math.cos(radians)),
                           round(cy + radius * math.sin(radians))))

    arc(x + radius, y + radius, 180)
    if side == "below":
        points.extend(((pointer - half_base, y), (pointer, 1), (pointer + half_base, y)))
    arc(right - radius, y + radius, 270)
    if side == "left":
        points.extend(((right, pointer - half_base), (window.width - 2, pointer),
                       (right, pointer + half_base)))
    arc(right - radius, bottom - radius, 0)
    if side == "above":
        points.extend(((pointer + half_base, bottom), (pointer, window.height - 2),
                       (pointer - half_base, bottom)))
    arc(x + radius, bottom - radius, 90)
    if side == "right":
        points.extend(((x, pointer + half_base), (1, pointer), (x, pointer - half_base)))
    return points
