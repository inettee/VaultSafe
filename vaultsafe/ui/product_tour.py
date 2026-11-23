"""Guided walkthrough anchored to live VaultSafe widgets."""

from dataclasses import dataclass, replace
import tkinter as tk
from tkinter import font as tkfont

import customtkinter as ctk

from .. import theme
from .tour_geometry import Rect, callout_outline, choose_placement
from .tour_overlay import WINDOWS, Spotlight, spotlight_image
from .unlock_view import UnlockView
from .vault_view import VaultView


@dataclass(frozen=True)
class Step:
    title: str
    text: str
    sides: tuple[str, ...]


STEPS = (
    Step("Tạo kho riêng của bạn",
         "Đặt tên để nhận ra hồ sơ. Dùng một cụm mật khẩu chính dài, dễ nhớ để mở kho trên máy này.",
         ("right", "left", "above", "below")),
    Step("Thêm tài khoản đầu tiên",
         "Bấm + cạnh ô tìm kiếm, chọn Đăng nhập rồi điền tên dịch vụ, tên đăng nhập và mật khẩu. Bấm Lưu để thêm vào kho.",
         ("below", "right", "left", "above")),
    Step("Tạo mật khẩu mới",
         "Bấm Tạo mật khẩu, chọn độ dài và nhóm ký tự. Bấm Dùng mật khẩu này để điền vào form rồi lưu mục.",
         ("above", "below", "left", "right")),
    Step("Tìm và sao chép mật khẩu",
         "Gõ tên dịch vụ hoặc tên đăng nhập. Chọn một mục rồi bấm Sao chép bên cạnh ô mật khẩu.",
         ("below", "above", "left", "right")),
    Step("Xử lý cảnh báo mật khẩu",
         "VaultSafe chỉ ra mật khẩu yếu hoặc dùng lại. Bấm Mở mục, đổi mật khẩu trên dịch vụ rồi cập nhật mục đã lưu.",
         ("below", "above", "left", "right")),
    Step("Sắp xếp kho của bạn",
         "Đánh dấu sao cho mục hay dùng. Dùng Thùng rác để khôi phục mục đã xóa, hoặc lọc theo loại và thư mục.",
         ("right", "left", "below", "above")),
    Step("Khóa kho khi rời máy",
         "Bấm Khóa kho để đóng kho. Nếu dùng chung máy, bấm Đổi hồ sơ để người khác chọn kho của họ.",
         ("right", "above", "left", "below")),
)


class _Callout:
    fill = "#0D1B34"
    border = "#5076A3"
    clear = "#FE00FE"

    def __init__(self, master, app, tour):
        self.window = tk.Toplevel(master, takefocus=False)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.transient(app)
        self.window.bind("<Escape>", lambda _: tour.stop())
        canvas_bg = self.clear if WINDOWS else theme.BACKGROUND
        if WINDOWS:
            self.window.attributes("-transparentcolor", self.clear)
            if app.attributes("-topmost"):
                self.window.attributes("-topmost", True)
        self.canvas = tk.Canvas(self.window, highlightthickness=0, bg=canvas_bg)
        self.canvas.pack(fill="both", expand=True)
        self.title_font = tkfont.Font(root=app, family=theme.FONT, weight="bold")
        self.body_font = tkfont.Font(root=app, family=theme.FONT)
        self.actions = tk.Frame(self.canvas, bg=self.fill)
        self.back = theme.button(self.actions, "Trước", tour.previous, width=62, height=32)
        self.back.pack(side="left", padx=(0, 6))
        self.forward = theme.button(self.actions, "Tiếp", tour.next, kind="primary",
                                    width=78, height=32)
        self.forward.pack(side="left")
        self.visible = False
        self.scale = None
        self.stacked = False

    def _wrap(self, text, font, width):
        lines = [""]
        for word in text.split():
            proposed = f"{lines[-1]} {word}".lstrip()
            if lines[-1] and font.measure(proposed) > width:
                lines.append(word)
            else:
                lines[-1] = proposed
        return "\n".join(lines), len(lines) * font.metrics("linespace")

    def measure(self, step, width, scale):
        if scale != self.scale:
            self.title_font.configure(size=-round(20 * scale))
            self.body_font.configure(size=-round(15 * scale))
            self.scale = scale
        pad = round(16 * scale) if width >= round(220 * scale) else round(12 * scale)
        title, title_height = self._wrap(step.title, self.title_font, width - 2 * pad)
        text, text_height = self._wrap(step.text, self.body_font, width - 2 * pad)
        stacked = width < round(180 * scale)
        height = 2 * pad + title_height + text_height + round((92 if stacked else 54) * scale)
        return height, pad, title, title_height, text, text_height

    def paint(self, step, placement, client, scale, first, last):
        rect = placement.window
        body = placement.body
        _, pad, title, title_height, text, text_height = self.measure(step, body.width, scale)
        x, y = body.x - rect.x, body.y - rect.y
        self.canvas.delete("all")
        outline = callout_outline(placement, round(14 * scale), round(10 * scale))
        self.canvas.create_polygon(outline, fill=self.fill, outline=self.border, width=max(1, scale))
        self.canvas.create_text(x + pad, y + pad, text=title, font=self.title_font,
                                fill=theme.TEXT, anchor="nw")
        text_y = y + pad + title_height + round(7 * scale)
        self.canvas.create_text(x + pad, text_y, text=text, font=self.body_font,
                                fill=theme.TEXT, anchor="nw")
        self.back.configure(text="Bỏ qua" if first else "Trước")
        self.forward.configure(text="Hoàn tất" if last else "Tiếp")
        stacked = body.width < round(180 * scale)
        if stacked != self.stacked:
            self.back.pack_forget()
            self.forward.pack_forget()
            if stacked:
                self.back.pack(fill="x", pady=(0, 6))
                self.forward.pack(fill="x")
            else:
                self.back.pack(side="left", padx=(0, 6))
                self.forward.pack(side="left")
            self.stacked = stacked
        actions_y = text_y + text_height + round(11 * scale)
        self.canvas.create_window(x + body.width - pad, actions_y, window=self.actions, anchor="ne")
        self.window.geometry(f"{rect.width}x{rect.height}+{client.x + rect.x}+{client.y + rect.y}")
        if not self.visible:
            self.window.deiconify()
            self.visible = True
        self.window.update_idletasks()
        self.window.lift()

    def hide(self):
        if self.visible:
            self.window.withdraw()
            self.visible = False


class ProductTour:
    def __init__(self, app):
        self.app = app
        self.index = None
        self._timer = self._spotlight = self._bubble = self._cache = None
        self._drawer_view = None
        self._dimmed_drawer = None
        self._last_target = None
        self._reveal_key = None
        self._waiting = False
        self.placement = self.target_rect = None

    @property
    def active(self):
        return self.index is not None

    def start(self):
        self.stop()
        view = self.app.view
        if isinstance(view, UnlockView):
            if not view.creating:
                view.show_create()
            self.index = 0
        elif isinstance(view, VaultView):
            self.index = 1
            if view.menu_modal:
                view.close_menu(animate=False)
        self._schedule()

    def unlocked(self):
        if self.index == 0:
            self._waiting = False
            self._go(1)

    def next(self):
        if not self.active:
            return
        if self.index == 0:
            # Profile creation and authentication are completed by the regular form.
            self._waiting = True
            self._hide()
        elif self.index == len(STEPS) - 1:
            self.stop()
        else:
            self._go(self.index + 1)

    def previous(self):
        if self.index in (0, 1):
            self.stop()
        elif self.active:
            self._go(self.index - 1)

    def _go(self, index):
        self.index = index
        self._cache = None
        view = self.app.view
        if isinstance(view, VaultView):
            if index in (5, 6):
                if not view.fixed_sidebar and not view.menu_modal:
                    self._drawer_view = view
                    view.open_menu()
            else:
                self._close_drawer()
                if view.menu_modal and (index < 4 or view.page not in ("form", "generator")):
                    view.close_menu(animate=False)
                if index == 2 and view.page != "form":
                    view.show_form(values={"kind": "login"})
                elif index == 3 and view.page not in ("form", "generator"):
                    account = next((item for item in view.accounts.values()
                                    if item.kind == "login" and view._is_visible(item)), None)
                    if account is not None and view.account_details is None:
                        view.select_account(account.id)
                elif index == 4 and view.page not in ("form", "generator", "audit"):
                    view.show_audit()
        self._schedule()

    def _close_drawer(self):
        drawer, self._drawer_view = self._drawer_view, None
        if drawer is not None and drawer.winfo_exists():
            drawer.close_menu(animate=False)

    def stop(self, *, close_drawer=True):
        if self._timer is not None:
            self.app.after_cancel(self._timer)
            self._timer = None
        self.index = None
        self._waiting = False
        self._cache = self._last_target = self._reveal_key = None
        self.placement = self.target_rect = None
        self._sync_drawer_dim(None)
        if self._bubble is not None:
            self._bubble.window.destroy()
            self._bubble = None
        if self._spotlight is not None:
            self._spotlight.close()
            self._spotlight = None
        if close_drawer:
            self._close_drawer()
        else:
            self._drawer_view = None
        return "break"

    def _schedule(self):
        if self.active and self._timer is None:
            self._timer = self.app.after(40, self._tick)

    def _tick(self):
        self._timer = None
        self._refresh()
        self._schedule()

    def _hide(self):
        self._cache = self.placement = self.target_rect = None
        self._sync_drawer_dim(None)
        if self._bubble is not None:
            self._bubble.hide()
        if self._spotlight is not None:
            self._spotlight.hide()

    def _sync_drawer_dim(self, view):
        if self._dimmed_drawer != view:
            if self._dimmed_drawer is not None:
                self._dimmed_drawer.set_tour_dim(False)
            self._dimmed_drawer = view
            if view is not None:
                view.set_tour_dim(True)

    @staticmethod
    def _box(widget):
        return Rect(widget.winfo_rootx(), widget.winfo_rooty(),
                    widget.winfo_width(), widget.winfo_height())

    def _visible_box(self, widget, client):
        if widget is None or not widget.winfo_exists() or not widget.winfo_viewable():
            return None
        visible = self._box(widget)
        parent = widget.master
        while visible is not None and parent is not None and parent != self.app:
            visible = visible.intersect(self._box(parent))
            parent = parent.master
        return visible.intersect(client) if visible is not None else None

    def _targets(self, view):
        if self.index == 0:
            return (view.form, view.submit_button) if view.creating and not self._waiting else ()
        if view.menu_modal and (
            view._menu_timer is not None or self.index < 4
            or self.index == 4 and view.audit_view is not None
        ):
            return ()
        if self.index == 1:
            if view.account_form is not None and view.account_form.generate_button is not None:
                self.index = 2
            else:
                return (view.add_button,)
        if self.index == 2:
            if view.page == "generator":
                return ()
            if view.account_form is not None:
                return (view.account_form.generate_button, view.add_button)
            self.index = 3
        if self.index == 3:
            detail = view.account_details
            return (getattr(detail, "copy_button", None), view.search_entry)
        if self.index == 4:
            if view.audit_view is not None:
                return (view.audit_view.first_open_button, view.audit_view.summary)
            return (view.nav_buttons["audit"], view.menu_button)
        if self.index == 5:
            return (view.organize_panel, view.filter_buttons[("filter", "all")][0],
                    view.menu_button)
        return (view.profile_panel, view.lock_button, view.menu_button)

    def _step_for(self, view, widget):
        step = STEPS[self.index]
        if self.index >= 4 and widget == view.menu_button:
            return replace(step, text="Mở menu ☰. " + step.text)
        if self.index == 4:
            if view.audit_view is None:
                return replace(step, text="Bấm Kiểm tra an toàn để xem mật khẩu yếu hoặc dùng lại.")
            if view.audit_view.first_open_button is None:
                return replace(step, text="Đây là nơi xem mật khẩu yếu hoặc dùng lại. Kho hiện chưa có cảnh báo.")
        return step

    def _refresh(self):
        view = self.app.view
        if not self.app.winfo_viewable() or self.app.state() == "iconic":
            self._hide()
            return
        targets = tuple(widget for widget in self._targets(view)
                        if widget is not None and widget.winfo_exists() and widget.winfo_viewable())
        client = self._box(self.app)
        local = Rect(0, 0, client.width, client.height)
        scale = ctk.ScalingTracker.get_widget_scaling(self.app)
        drawer = isinstance(view, VaultView) and view.menu_modal
        master = view.sidebar if drawer else self.app

        if targets:
            primary = targets[0]
            reveal_key = (self.index, primary, client.width, client.height)
            if reveal_key != self._reveal_key:
                self._reveal_key = reveal_key
                pane = primary.master
                while pane is not None and not isinstance(pane, theme.ScrollPane):
                    pane = pane.master
                if pane is not None and pane.reveal(primary):
                    self._hide()
                    return

        for widget in targets:
            visible = self._visible_box(widget, client)
            if visible is None or visible.width < 10 or visible.height < 10:
                continue
            target = Rect(visible.x - client.x, visible.y - client.y, visible.width, visible.height)
            if self._bubble is None or self._bubble.window.master != master:
                if self._bubble is not None:
                    self._bubble.window.destroy()
                self._bubble = _Callout(master, self.app, self)
                self._cache = None
            step = self._step_for(view, widget)
            key = (step, client, target, drawer, scale)
            if key != self._cache:
                placement = choose_placement(
                    local, target, lambda w: self._bubble.measure(step, w, scale)[0],
                    sides=step.sides, scale=scale,
                )
                if placement is None:
                    continue
                if WINDOWS:
                    try:
                        if self._spotlight is None:
                            self._spotlight = Spotlight(self.app)
                        self._spotlight.paint(spotlight_image((client.width, client.height),
                                                              target, scale), client.x, client.y)
                    except OSError:
                        if self._spotlight is not None:
                            self._spotlight.close()
                            self._spotlight = None
                self._sync_drawer_dim(view if drawer and self._spotlight is not None else None)
                self._bubble.paint(step, placement, client, scale, self.index <= 1,
                                   self.index == len(STEPS) - 1)
                self.placement, self.target_rect = placement, target
                self._cache = key
            self._last_target = widget
            return
        self._hide()
