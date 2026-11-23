"""Nền Canvas và bố cục vòng khóa cho màn hình xác thực."""

from dataclasses import dataclass
from math import ceil, cos, exp, hypot, pi, sin
from random import Random
from time import monotonic
import tkinter as tk

import customtkinter as ctk

from .. import theme


# Kích thước và tốc độ tính theo pixel giao diện, trước khi áp dụng DPI.
BACKGROUND = "#0C1424"
CIRCUIT = "#172D3E"
CONTACT = "#254859"
PULSE_TAIL = "#244959"
PULSE_HEAD = "#39798D"
PULSE_POINT = "#5BAABC"
PARTICLE_COLORS = ("#284455", "#324E60", "#3C6475")
LINK_COLOR = "#528D9D"
RING_COLORS = ("#2B5265", "#1C3548", "#192F41")
ARC_COLORS = ("#458294", "#315D73")
TICK_COLORS = ("#2D5669", "#213F52")
FRAME_MS = 33
PARTICLE_SPACING = 77
PARTICLE_SPEED = (11, 23)
PARTICLE_RADIUS = (0.75, 1.10)
TRACE_SPACING = 165
PULSE_SPEED = (45, 83)
ARC_SPEEDS = (4.3, -2.6)
POINTER_RANGE = 176
LINK_RANGE = 128
LINK_FADE = 10
DIAL_FILL = 0.445
DIAL_PADDING = 10
DIAL_EDGE = 8
COMPACT_BELOW = 646


def _shade(color, strength):
    base = bytes.fromhex(BACKGROUND[1:])
    tint = bytes.fromhex(color[1:])
    return "#" + bytes(round(a + (b - a) * strength) for a, b in zip(base, tint)).hex()


LINK_PALETTE = tuple(_shade(LINK_COLOR, index / 15) for index in range(16))


@dataclass(slots=True)
class Particle:
    item: int
    x: float
    y: float
    vx: float
    vy: float
    radius: float


@dataclass(slots=True)
class Circuit:
    legs: tuple
    length: float
    pace: float
    phase: float
    tail: int
    head: int
    point: int


class UnlockBackground:
    def __init__(self, canvas):
        self.canvas = canvas
        self.timer = None
        self._last = None
        self._elapsed = 0.0
        self._size = None
        self._dial = None
        self.particles = []
        self._circuits = []
        self._arcs = []
        self.links = {}
        canvas.bind("<Map>", self._resume, add="+")
        canvas.bind("<Unmap>", self.pause, add="+")

    def _resume(self, _event):
        if self.timer is None:
            self.timer = self.canvas.after(FRAME_MS, self._frame)

    def pause(self, _event=None):
        if self.timer is not None:
            self.canvas.after_cancel(self.timer)
            self.timer = None
        self._last = None

    def arrange(self, width, height, scale, circle):
        size = (width, height, scale)
        if size != self._size:
            self._size = size
            self._build_scene(width, height, scale)
        if (circle, scale) != self._dial:
            self._dial = circle, scale
            self._build_dial(*circle, scale)

    def _build_scene(self, width, height, scale):
        self.canvas.delete("field")
        self.links.clear()
        self.particles.clear()
        self._circuits.clear()
        random = Random(43)
        columns = max(1, round(width / (PARTICLE_SPACING * scale)))
        rows = max(1, round(height / (PARTICLE_SPACING * scale)))
        for row in range(rows):
            for column in range(columns):
                x = width * (column + random.uniform(.19, .81)) / columns
                y = height * (row + random.uniform(.19, .81)) / rows
                angle = random.uniform(0, 2 * pi)
                speed = random.uniform(*PARTICLE_SPEED) * scale
                radius = random.uniform(*PARTICLE_RADIUS) * scale
                item = self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius,
                                               fill=random.choice(PARTICLE_COLORS), outline="",
                                               tags=("field", "particle"))
                self.particles.append(Particle(item, x, y, cos(angle) * speed, sin(angle) * speed, radius))
        count = max(8, round(width * height / (TRACE_SPACING * scale) ** 2))
        for index in range(count):
            x, y = random.uniform(0, width), random.uniform(0, height)
            distance = random.uniform(52, 165) * scale * random.choice((-1, 1))
            bend = random.uniform(12, 29) * scale * random.choice((-1, 1))
            horizontal = index % 5 < 3
            middle = (x + distance, y) if horizontal else (x, y + distance)
            end = (middle[0], y + bend) if horizontal else (x + bend, middle[1])
            points = ((x, y), middle, end) if index % 3 == 0 else ((x, y), middle)
            legs = tuple((a, b, hypot(b[0] - a[0], b[1] - a[1])) for a, b in zip(points, points[1:]))
            self.canvas.create_line(*points, fill=CIRCUIT, tags="field")
            self.canvas.create_rectangle(x - 1, y - 1, x + 1, y + 1, fill=CONTACT,
                                         outline="", tags="field")
            tail = self.canvas.create_line(0, 0, 0, 0, fill=PULSE_TAIL, tags="field", state="hidden")
            head = self.canvas.create_line(0, 0, 0, 0, fill=PULSE_HEAD, tags="field", state="hidden")
            point = self.canvas.create_oval(0, 0, 0, 0, fill=PULSE_POINT, outline="", tags="field", state="hidden")
            self._circuits.append(Circuit(legs, sum(leg[2] for leg in legs), random.uniform(*PULSE_SPEED) * scale,
                                          random.uniform(0, 250) * scale, tail, head, point))
        self.canvas.tag_raise("dial")

    def _build_dial(self, x, y, radius, scale):
        self.canvas.delete("dial")
        self._arcs.clear()

        def bounds(offset):
            r = radius + offset * scale
            return x - r, y - r, x + r, y + r

        for offset, color in zip((0, 8, -10), RING_COLORS):
            self.canvas.create_oval(*bounds(offset), outline=color, tags="dial")
        for index in range(72):
            angle = index * pi / 36
            dx, dy = cos(angle), sin(angle)
            major = index % 6 == 0
            outer, inner = radius - 9 * scale, radius - (14 if major else 11) * scale
            self.canvas.create_line(x + outer * dx, y + outer * dy, x + inner * dx, y + inner * dy,
                                    fill=TICK_COLORS[0 if major else 1], tags="dial")
        for offset, speed, color, phase in zip((4, -5), ARC_SPEEDS, ARC_COLORS, (12, 53)):
            for index in range(4):
                start = phase + index * 90
                item = self.canvas.create_arc(*bounds(offset), start=start, extent=38 if index % 2 == 0 else 15,
                                              outline=color, style=tk.ARC, tags="dial")
                self._arcs.append((item, start, speed))

    def _pointer(self):
        x, y = self.canvas.winfo_pointerxy()
        widget = self.canvas.winfo_containing(x, y)
        while widget is not None and widget is not self.canvas:
            widget = widget.master
        if widget is self.canvas:
            return (self.canvas.canvasx(x - self.canvas.winfo_rootx()),
                    self.canvas.canvasy(y - self.canvas.winfo_rooty()))
        return None

    def _update_particles(self, dt, width, height, scale):
        for star in self.particles:
            r = star.radius
            x, y = star.x + star.vx * dt, star.y + star.vy * dt
            if not r <= x <= width - r:
                star.vx = -star.vx
            if not r <= y <= height - r:
                star.vy = -star.vy
            star.x, star.y = min(width - r, max(r, x)), min(height - r, max(r, y))
            self.canvas.coords(star.item, star.x - r, star.y - r, star.x + r, star.y + r)

        desired = {}
        pointer = self._pointer()
        if pointer is not None:
            px, py = pointer
            nearby = []
            for index, star in enumerate(self.particles):
                weight = 1 - hypot(star.x - px, star.y - py) / (POINTER_RANGE * scale)
                if weight > 0:
                    nearby.append((index, star, weight))
            for position, (i, a, wa) in enumerate(nearby):
                for j, b, wb in nearby[position + 1:]:
                    strength = (1 - hypot(a.x - b.x, a.y - b.y) / (LINK_RANGE * scale)) * min(wa, wb)
                    if strength > 0:
                        desired[i, j] = min(1, strength * 1.8)

        blend = 1 - exp(-dt * LINK_FADE)
        for pair in self.links.keys() | desired.keys():
            item, strength = self.links.get(pair, (None, 0))
            strength += (desired.get(pair, 0) - strength) * blend
            light = round(strength * (len(LINK_PALETTE) - 1))
            if not light:
                if item is not None:
                    self.canvas.delete(item)
                    del self.links[pair]
                continue
            a, b = (self.particles[index] for index in pair)
            coords = (a.x, a.y, b.x, b.y)
            if item is None:
                item = self.canvas.create_line(*coords, tags="field")
                self.canvas.tag_lower(item, "particle")
            else:
                self.canvas.coords(item, *coords)
            self.canvas.itemconfigure(item, fill=LINK_PALETTE[light])
            self.links[pair] = item, strength

    def _update_pulses(self, scale):
        for path in self._circuits:
            position = (path.phase + self._elapsed * path.pace) % (path.length + 88 * scale)
            hidden = position > path.length
            for item in (path.tail, path.head, path.point):
                self.canvas.itemconfigure(item, state="hidden" if hidden else "normal")
            if hidden:
                continue
            for (ax, ay), (bx, by), length in path.legs:
                if position <= length:
                    dx, dy = (bx - ax) / length, (by - ay) / length
                    x, y = ax + dx * position, ay + dy * position
                    lead, trail = min(position, 9 * scale), min(position, 24 * scale)
                    self.canvas.coords(path.tail, x - dx * trail, y - dy * trail, x, y)
                    self.canvas.coords(path.head, x - dx * lead, y - dy * lead, x, y)
                    r = scale
                    self.canvas.coords(path.point, x - r, y - r, x + r, y + r)
                    break
                position -= length

    def _frame(self):
        self.timer = None
        now = monotonic()
        dt = min(.08, now - self._last) if self._last is not None else FRAME_MS / 1000
        self._last = now
        self._elapsed += dt
        if self._size is not None:
            self._update_particles(dt, *self._size)
            self._update_pulses(self._size[2])
            for item, start, speed in self._arcs:
                self.canvas.itemconfigure(item, start=(start + self._elapsed * speed) % 360)
        self._resume(None)


class UnlockViewport(theme.ScrollPane):
    """Hai cửa sổ Canvas giữ nguyên các widget thật và có thể cuộn khi form dài."""

    def __init__(self, parent, resize_form):
        super().__init__(parent, BACKGROUND)
        self._resize_form = resize_form
        self._compact = None
        self.canvas.itemconfigure(self.content_window, anchor="n")
        self.branding = ctk.CTkFrame(self.canvas, fg_color=BACKGROUND, corner_radius=0)
        self._brand_window = self.canvas.create_window(0, 0, anchor="n", window=self.branding)
        tk.Widget.bind(self.branding, "<Configure>", self._set_scroll_region, add="+")
        self.animation = UnlockBackground(self.canvas)

    def _resize_canvas(self, event):
        self._set_scroll_region()

    def _set_scroll_region(self, _event=None):
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if width <= 1 or height <= 1:
            return
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        compact = height < COMPACT_BELOW * scale
        if compact != self._compact:
            self._compact = compact
            self._resize_form(compact)

        head_h, form_h = self.branding.winfo_reqheight(), self.content.winfo_reqheight()
        head_x, form_x = self.branding.winfo_reqwidth() / 2, self.content.winfo_reqwidth() / 2
        total = head_h + form_h
        # Balance the upper branding corners and lower form corners about the dial center.
        offset = (form_x ** 2 - head_x ** 2 + total ** 2) / (2 * total)
        extent = max(hypot(head_x, offset), hypot(form_x, total - offset), hypot(form_x, head_h - offset))
        radius = max(extent + DIAL_PADDING * scale, min(width, height) * DIAL_FILL)
        scene_height = max(height, ceil(2 * (radius + DIAL_EDGE * scale)))
        cx, cy = width / 2, scene_height / 2
        top = cy - offset
        self.canvas.coords(self._brand_window, cx, top)
        self.canvas.coords(self.content_window, cx, top + head_h)
        self.canvas.configure(scrollregion=(0, 0, width, scene_height))
        self.animation.arrange(width, scene_height, scale, (cx, cy, radius))

    def destroy(self):
        self.animation.pause()
        super().destroy()
