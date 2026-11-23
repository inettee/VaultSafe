"""Per-pixel Windows spotlight. Its owned window always passes mouse input through."""

import ctypes as ct
from ctypes import wintypes as wt
import sys

from PIL import Image, ImageDraw, ImageFilter


WINDOWS = sys.platform == "win32"


class _BitmapInfo(ct.Structure):
    _fields_ = [
        ("size", wt.DWORD), ("width", wt.LONG), ("height", wt.LONG),
        ("planes", wt.WORD), ("bits", wt.WORD), ("compression", wt.DWORD),
        ("image_size", wt.DWORD), ("x_ppm", wt.LONG), ("y_ppm", wt.LONG),
        ("colors", wt.DWORD), ("important_colors", wt.DWORD),
    ]


class _Blend(ct.Structure):
    _fields_ = [(name, wt.BYTE) for name in ("operation", "flags", "alpha", "format")]


def _signature(dll, name, result, *arguments):
    function = getattr(dll, name)
    function.restype = result
    function.argtypes = arguments
    return function


if WINDOWS:
    _user = ct.WinDLL("user32", use_last_error=True)
    _gdi = ct.WinDLL("gdi32", use_last_error=True)
    _root = _signature(_user, "GetAncestor", wt.HWND, wt.HWND, wt.UINT)
    _create = _signature(_user, "CreateWindowExW", wt.HWND, wt.DWORD, wt.LPCWSTR,
                         wt.LPCWSTR, wt.DWORD, ct.c_int, ct.c_int, ct.c_int, ct.c_int,
                         wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID)
    _update = _signature(_user, "UpdateLayeredWindow", wt.BOOL, wt.HWND, wt.HDC,
                         ct.POINTER(wt.POINT), ct.POINTER(wt.SIZE), wt.HDC,
                         ct.POINTER(wt.POINT), wt.DWORD, ct.POINTER(_Blend), wt.DWORD)
    _position = _signature(_user, "SetWindowPos", wt.BOOL, wt.HWND, wt.HWND,
                           ct.c_int, ct.c_int, ct.c_int, ct.c_int, wt.UINT)
    _show = _signature(_user, "ShowWindow", wt.BOOL, wt.HWND, ct.c_int)
    _destroy = _signature(_user, "DestroyWindow", wt.BOOL, wt.HWND)
    _dc = _signature(_gdi, "CreateCompatibleDC", wt.HDC, wt.HDC)
    _delete_dc = _signature(_gdi, "DeleteDC", wt.BOOL, wt.HDC)
    _bitmap = _signature(_gdi, "CreateDIBSection", wt.HBITMAP, wt.HDC, ct.POINTER(_BitmapInfo),
                         wt.UINT, ct.POINTER(wt.LPVOID), wt.HANDLE, wt.DWORD)
    _select = _signature(_gdi, "SelectObject", wt.HGDIOBJ, wt.HDC, wt.HGDIOBJ)
    _delete = _signature(_gdi, "DeleteObject", wt.BOOL, wt.HGDIOBJ)


def spotlight_image(size, target, scale):
    image = Image.new("RGBA", size, (0, 0, 0, 150))
    draw = ImageDraw.Draw(image)
    padding = max(2, round(3 * scale))
    outline = (target.x - padding, target.y - padding,
               target.right + padding - 1, target.bottom + padding - 1)
    radius = min(round(12 * scale), target.width // 2, target.height // 2)
    halo = Image.new("L", size)
    ImageDraw.Draw(halo).rounded_rectangle(outline, radius, outline=255,
                                           width=max(3, round(8 * scale)))
    glow = Image.new("RGBA", size, (0, 204, 255))
    glow.putalpha(halo.filter(ImageFilter.GaussianBlur(5 * scale)))
    image.alpha_composite(glow)
    draw.rounded_rectangle(outline, radius, outline="#33E6FF", width=max(2, round(2 * scale)))
    # The widget itself stays at full brightness, including input text and hover states.
    draw.rounded_rectangle((target.x, target.y, target.right - 1, target.bottom - 1),
                           radius, fill=(0, 0, 0, 0))
    return image


class Spotlight:
    def __init__(self, app):
        # WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        styles = 0x080800A0
        self.handle = _create(styles, "STATIC", None, 0x80000000, 0, 0, 0, 0,
                              _root(app.winfo_id(), 2), None, None, None)
        if not self.handle:
            raise ct.WinError(ct.get_last_error())

    def paint(self, image, x, y):
        width, height = image.size
        info = _BitmapInfo(ct.sizeof(_BitmapInfo), width, -height, 1, 32)
        pointer = wt.LPVOID()
        dc = _dc(None)
        if not dc:
            raise ct.WinError(ct.get_last_error())
        bitmap = previous = None
        try:
            bitmap = _bitmap(dc, ct.byref(info), 0, ct.byref(pointer), None, 0)
            if not bitmap or not pointer:
                raise ct.WinError(ct.get_last_error())
            previous = _select(dc, bitmap)
            red, green, blue, alpha = image.convert("RGBa").split()
            pixels = Image.merge("RGBA", (blue, green, red, alpha)).tobytes()
            ct.memmove(pointer, pixels, len(pixels))
            if not _update(self.handle, None, ct.byref(wt.POINT(x, y)),
                           ct.byref(wt.SIZE(width, height)), dc, ct.byref(wt.POINT()),
                           0, ct.byref(_Blend(0, 0, 255, 1)), 2):
                raise ct.WinError(ct.get_last_error())
            # SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW
            _position(self.handle, None, 0, 0, 0, 0, 0x0053)
        finally:
            if previous:
                _select(dc, previous)
            if bitmap:
                _delete(bitmap)
            _delete_dc(dc)

    def hide(self):
        _show(self.handle, 0)

    def close(self):
        if self.handle:
            _destroy(self.handle)
            self.handle = None
