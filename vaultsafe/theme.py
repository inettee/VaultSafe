"""Màu sắc, kích thước và các widget dùng chung."""

from functools import lru_cache
import os
from pathlib import Path
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont


BACKGROUND = "#0F172A"
SIDEBAR = "#0B1120"
LIST_BACKGROUND = "#131C2E"
SIDEBAR_FOOT = "#090E1A"
SCRIM = "#000000"
SCRIM_OPACITY = 0.60
TOOLBAR = "#111929"
SURFACE = "#182232"
HEADER_SURFACE = "#1A2435"
CONTROL = "#101829"
BORDER = "#1E293B"
INPUT_BORDER = "#303E52"
SCROLL_THUMB = "#334155"
PRIMARY = "#2563EB"
PRIMARY_HOVER = "#3B82F6"
NAV_SELECTED = "#0F1D3E"
SELECTED = "#16274A"
SELECTED_BORDER = "#234581"
SECONDARY = "#1E293B"
SECONDARY_HOVER = "#334155"
TEXT = "#F1F5F9"
MUTED = "#94A3B8"
SUBTLE = "#71839D"
ACCENT = "#60A5FA"
SUCCESS = "#34D399"
SUCCESS_BAR = "#10B981"
WARNING = "#FBBF24"
WARNING_SURFACE = "#352B21"
ERROR = "#FDA4AF"
DANGER_HOVER = "#3E2637"

FONT = "Segoe UI"
MONO = "Consolas"
FONT_META = 12
FONT_BODY = 14
FONT_TITLE = 20
RADIUS = 16
CONTROL_RADIUS = 12
SPACING = 8
FIELD_PADDING = 16
CARD_PADDING = 20
SECTION_GAP = 24
PANEL_PADDING = 32
PANEL_MAX_WIDTH = 704
GENERATOR_MAX_WIDTH = 608
PANEL_COMPACT_PADDING = 16
PANEL_INSET_MIN_WIDTH = 560
DETAIL_TOP_PADDING = 56
DETAIL_ACTION_HEIGHT = 34
SCROLLBAR_WIDTH = 8
SIDEBAR_WIDTH = 245
LIST_WIDTH = 335
COMPACT_LIST_WIDTH = 325
FIXED_SIDEBAR_MIN_WIDTH = 1200
MENU_SLIDE_MS = 160
MENU_FRAME_MS = 16
MENU_BUTTON_SIZE = 34
MENU_ROW_HEIGHT = 32
MENU_INSET = 12
MENU_GROUP_GAP = 12
MENU_COUNT_WIDTH = 21
LIST_ROW_HEIGHT = 62
LIST_ROW_GAP = 4
SERVICE_ICON_SIZE = 40
SEARCH_BUTTON_SIZE = 36
SEARCH_FIELD_HEIGHT = 38
TOOLBAR_PADDING = 14
UNLOCK_LOGO_SIZE = 88
SIDEBAR_LOGO_SIZE = 38
WINDOW_SIZE = (1366, 768)
MIN_WINDOW_SIZE = (740, 460)
MASK = "•"
ASSET_DIR = Path(__file__).resolve().parent / "assets"
ICON_FONT = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segmdl2.ttf"
ICONS = {
    "vault": "\ue8b7", "key": "\ue8d7", "audit": "\ue72e", "search": "\ue721",
    "edit": "\ue70f", "delete": "\ue74d", "copy": "\ue8c8", "refresh": "\ue72c",
    "eye": "\ue890", "hide": "\ued1a", "menu": "\ue700",
    "favorite": "\ue734", "login": "\ue909", "card": "\ue8c7",
    "identity": "\ue8d4", "note": "\ue70b", "folder": "\ue8b7",
}


def load_logo(size: int) -> ctk.CTkImage | None:
    try:
        with Image.open(ASSET_DIR / "logo.png") as source:
            image = source.convert("RGBA")
    except OSError:
        return None
    scale = size / max(image.size)
    dimensions = tuple(max(1, round(side * scale)) for side in image.size)
    return ctk.CTkImage(light_image=image, size=dimensions)


def icon(name, color=TEXT, size=14):
    image = _render_icon(name, color, size)
    return ctk.CTkImage(light_image=image, size=(size, size)) if image else None


@lru_cache(maxsize=32)
def _render_icon(name, color, size):
    try:
        font = ImageFont.truetype(str(ICON_FONT), size * 3)
    except OSError:
        return None
    glyph = ICONS[name]
    left, top, right, bottom = font.getbbox(glyph)
    image = Image.new("RGBA", (size * 3, size * 3))
    ImageDraw.Draw(image).text(((size * 3 - right - left) / 2,
                                (size * 3 - bottom - top) / 2),
                               glyph, font=font, fill=color)
    return image


def label(parent, text="", *, size=FONT_BODY, color=TEXT, bold=False, family=FONT, **kwargs):
    return ctk.CTkLabel(
        parent, text=text, text_color=color,
        font=(family, size, "bold" if bold else "normal"), **kwargs,
    )


def wrapped_label(parent, text, *, margin=0, **kwargs):
    """Ngắt dòng theo chiều rộng thực tế, kể cả với URL hoặc tên dài."""
    widget = label(parent, text, anchor="w", justify="left", wraplength=250, **kwargs)

    def resize(event):
        # Tk reports screen pixels. CustomTkinter scales wraplength itself.
        scale = ctk.ScalingTracker.get_widget_scaling(widget)
        widget.configure(wraplength=max(1, round(event.width / scale) - margin))

    parent.bind("<Configure>", resize, add="+")
    return widget


def ellipsized_label(parent, text, *, size=FONT_BODY, bold=False, color=TEXT, height=20):
    font = ctk.CTkFont(family=FONT, size=size, weight="bold" if bold else "normal")
    widget = ctk.CTkLabel(parent, text="", width=1, height=height, font=font,
                          text_color=color, anchor="w")
    text = " ".join(text.split())

    def fit(event):
        scale = ctk.ScalingTracker.get_widget_scaling(widget)
        width = event.width / scale
        if font.measure(text) <= width:
            widget.configure(text=text)
            return
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if font.measure(text[:middle] + "…") <= width:
                low = middle
            else:
                high = middle - 1
        widget.configure(text=text[:low].rstrip() + "…")

    tk.Widget.bind(widget, "<Configure>", fit, add="+")
    return widget


def button(parent, text, command, *, kind="secondary", width=96, height=36,
           radius=CONTROL_RADIUS, size=13, icon_name=None, icon_color=None, **kwargs):
    colors = {
        "primary": (PRIMARY, PRIMARY_HOVER, TEXT),
        "secondary": (SECONDARY, SECONDARY_HOVER, TEXT),
        "quiet": ("transparent", SECONDARY, MUTED),
        "accent": (NAV_SELECTED, SELECTED, ACCENT),
        "danger": (SECONDARY, DANGER_HOVER, ERROR),
    }
    background, hover, foreground = colors[kind]
    return ctk.CTkButton(
        parent, text=text, command=command, fg_color=background, hover_color=hover,
        text_color=foreground, font=(FONT, size, "bold"), width=width, height=height,
        corner_radius=radius, image=icon(icon_name, icon_color or foreground) if icon_name else None,
        **kwargs,
    )


def entry(parent, *, height=42, bg=CONTROL, border_width=1, radius=CONTROL_RADIUS,
          family=FONT, **kwargs):
    return ctk.CTkEntry(
        parent, height=height, fg_color=bg, text_color=TEXT,
        border_color=INPUT_BORDER, border_width=border_width, corner_radius=radius,
        font=(family, FONT_BODY), **kwargs,
    )


def card(parent, *, bg=SURFACE):
    return ctk.CTkFrame(
        parent, fg_color=bg, corner_radius=RADIUS,
        border_width=1, border_color=BORDER,
    )


def divider(parent, *, vertical=False):
    dimension = {"width": 1} if vertical else {"height": 1}
    return ctk.CTkFrame(parent, bg_color=BORDER, fg_color=BORDER, corner_radius=0, **dimension)


def strength_strip(parent, color=SECONDARY):
    return ctk.CTkFrame(parent, fg_color=color, height=6, corner_radius=3)


def short_text(text, limit):
    return text if len(text) <= limit else text[:limit - 1] + "…"


def service_mark(parent, service, size=SERVICE_ICON_SIZE):
    palettes = (
        ("#1B3758", "#9DCCFF"), ("#173C42", "#80E3D1"),
        ("#302B52", "#C9BBFA"), ("#3A3040", "#F4BDDC"),
    )
    background, foreground = palettes[sum(map(ord, service.casefold())) % len(palettes)]
    letters = "".join(word[0] for word in service.split()[:2]).upper()
    mark = label(
        parent, letters or "?", size=round(size * 0.36), color=foreground, bold=True,
        width=size, height=size, fg_color=background, corner_radius=CONTROL_RADIUS,
    )
    mark.grid_propagate(False)
    return mark


class ScrollPane(ctk.CTkFrame):
    """Một vùng cuộn dọc với thanh cuộn CustomTkinter."""

    def __init__(self, parent, color, *, center=False):
        super().__init__(parent, fg_color=color, corner_radius=0)
        self.center = center
        self.canvas = tk.Canvas(self, bg=color, highlightthickness=0, width=1,
                                height=1, yscrollincrement=24)
        self.scrollbar = ctk.CTkScrollbar(
            self, command=self.canvas.yview, fg_color=color, minimum_pixel_length=28,
            button_color=color, button_hover_color=color, width=SCROLLBAR_WIDTH, border_spacing=1,
        )

        def update_thumb(first, last):
            self.scrollbar.set(first, last)
            full = self.canvas.yview() == (0.0, 1.0)
            thumb = color if full else SCROLL_THUMB
            if self.scrollbar.cget("scrollbar_color") != thumb:
                self.scrollbar.configure(button_color=thumb, button_hover_color=thumb)

        self.canvas.configure(yscrollcommand=update_thumb)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y", pady=5)

        self.content = ctk.CTkFrame(self.canvas, fg_color=color, corner_radius=0)
        self.content_window = self.canvas.create_window(0, 0, anchor="nw", window=self.content)
        self.canvas.bind("<Configure>", self._resize_canvas)
        tk.Widget.bind(self.content, "<Configure>", self._set_scroll_region, add="+")

    def _resize_canvas(self, event):
        self.canvas.itemconfigure(self.content_window, width=event.width)
        self._set_scroll_region()

    def _set_scroll_region(self, event=None):
        top = 0
        bottom_padding = 0
        height = self.content.winfo_height()
        if self.center:
            top = max(10, (self.canvas.winfo_height() - height) // 2)
            bottom_padding = 10
            self.canvas.coords(self.content_window, 0, top)
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(),
                                           top + height + bottom_padding))

    def scroll_to_top(self):
        self.canvas.yview_moveto(0)

    def scroll_by(self, units):
        if self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(units, "units")

    def reveal(self, widget):
        canvas = self.canvas
        first, last = canvas.yview()
        if (first, last) == (0.0, 1.0):
            return False
        height = canvas.winfo_height()
        top = widget.winfo_rooty() - canvas.winfo_rooty()
        bottom = top + widget.winfo_height()
        if top >= 0 and (bottom <= height or widget.winfo_height() > height):
            return False
        _, start, _, end = map(int, canvas.cget("scrollregion").split())
        above = top < 0 or widget.winfo_height() >= height
        offset = top - 8 if above else bottom - height + 8
        canvas.yview_moveto((canvas.canvasy(0) + offset - start) / max(1, end - start))
        return canvas.yview() != (first, last)
