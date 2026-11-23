"""Giao diện kiểm tra link. Việc tải và phân tích HTML chạy ngoài luồng Tk."""

from concurrent.futures import ThreadPoolExecutor
import tkinter as tk

import customtkinter as ctk

from .. import theme
from ..link_checker import InvalidLink, Risk, inspect_page, inspect_url
from ..public_html import FetchStatus, fetch_html


RISK_COLORS = {Risk.HIGH: theme.ERROR, Risk.REVIEW: theme.WARNING, Risk.NONE: theme.TEXT}


def _inspect_content(report, saved):
    loaded = fetch_html(report.source)
    result = inspect_page(report, loaded.body, redirects=loaded.redirects,
                          saved=saved, encoding=loaded.encoding)
    return loaded.status, result


class LinkCheckerView(ctk.CTkFrame):
    def __init__(self, parent, saved):
        super().__init__(parent, fg_color="transparent")
        self._saved = saved
        self._report = None
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vaultsafe-link")
        self._future = None
        self._poll_id = None

        controls = theme.card(self)
        controls.pack(fill="x")
        inset = theme.FIELD_PADDING
        theme.label(controls, "URL đăng nhập", bold=True, anchor="w").pack(
            fill="x", padx=inset, pady=(inset, 4),
        )
        self.url = tk.StringVar(master=self)
        entry = theme.entry(controls, textvariable=self.url, placeholder_text="https://…")
        entry.pack(fill="x", padx=inset)
        entry.bind("<Return>", self._submit)
        self.compare = tk.BooleanVar(master=self)
        ctk.CTkCheckBox(
            controls, text="Đối chiếu với tài khoản đã lưu", variable=self.compare,
            command=self._comparison_changed, state="normal" if saved else "disabled",
            font=(theme.FONT, theme.FONT_META), border_color=theme.INPUT_BORDER,
            fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER,
        ).pack(anchor="w", padx=inset, pady=(12, 0))
        comparison = (f"Mục đối chiếu: {saved.name}" if saved else
                      "Chọn một mục đăng nhập có URL rồi mở lại công cụ để đối chiếu.")
        theme.wrapped_label(controls, comparison, margin=2 * inset, color=theme.MUTED, size=12).pack(
            fill="x", padx=inset, pady=(3, 8),
        )

        actions = ctk.CTkFrame(controls, fg_color="transparent")
        actions.pack(fill="x", padx=inset)
        self.check_button = theme.button(actions, "Kiểm tra", self.check_url, kind="primary", width=88)
        self.check_button.pack(side="left")
        self.html_button = theme.button(actions, "Phân tích nội dung trang", self.load_content,
                                        width=176, state="disabled")
        self.html_button.pack(side="left", padx=(theme.SPACING, 0))
        self.status = theme.wrapped_label(controls, "Kiểm tra URL trước khi tải nội dung.", margin=2 * inset,
                                          color=theme.MUTED, size=12)
        self.status.pack(fill="x", padx=inset, pady=(8, inset))
        self.results = ctk.CTkFrame(self, fg_color="transparent")
        self.results.pack(fill="x", pady=(theme.SECTION_GAP, 0))
        self._url_trace = self.url.trace_add("write", self._url_changed)
        entry.focus_set()

    def _submit(self, _event):
        self.check_url()
        return "break"

    def _url_changed(self, *_args):
        self._cancel_fetch()
        if self._report is not None:
            self._clear_results()
        self._report = None
        self.html_button.configure(state="disabled")
        self._set_status("Bấm Kiểm tra để phân tích URL đang nhập.")

    def _comparison_changed(self):
        if self._report is not None:
            self.check_url()

    def check_url(self):
        self._cancel_fetch()
        try:
            self._report = inspect_url(self.url.get(), self._saved if self.compare.get() else None)
        except InvalidLink as error:
            self._report = None
            self.html_button.configure(state="disabled")
            self._clear_results()
            self._set_status(str(error), theme.WARNING)
            return
        source = self._report.source
        self._render(self._report)
        if source.sensitive:
            self._set_status(FetchStatus.SENSITIVE.value, theme.WARNING)
        elif source.local_host:
            self._set_status(FetchStatus.NON_PUBLIC.value, theme.WARNING)
        else:
            self._set_status("Đã phân tích URL cục bộ. Có thể tải HTML công khai để kiểm tra thêm.")
        self.html_button.configure(state="disabled" if source.sensitive or source.local_host else "normal")

    def load_content(self):
        source = self._report.source if self._report else None
        if source is None or source.sensitive or source.local_host or self._future:
            return
        saved = self._saved if self.compare.get() else None
        self.html_button.configure(state="disabled")
        self._set_status("Đang phân tích nội dung trang…", theme.ACCENT)
        self._future = self._worker.submit(_inspect_content, self._report, saved)
        self._poll_id = self.after(50, self._poll)

    def _poll(self):
        self._poll_id = None
        if not self._future.done():
            self._poll_id = self.after(50, self._poll)
            return
        future, self._future = self._future, None
        try:
            status, report = future.result()
        except Exception:
            # Do not report exception details containing a URL or page content.
            self._set_status("Không đọc được nội dung HTML. Kết quả URL vẫn được giữ.", theme.WARNING)
        else:
            self._render(report)
            self._set_status(status.value, theme.MUTED if status is FetchStatus.OK else theme.WARNING)
        self.html_button.configure(state="normal")

    def _cancel_fetch(self):
        if self._poll_id is not None:
            self.after_cancel(self._poll_id)
            self._poll_id = None
        if self._future is not None:
            self._future.cancel()
            self._future = None

    def _set_status(self, text, color=theme.MUTED):
        self.status.configure(text=text, text_color=color)

    def _clear_results(self):
        for child in self.results.winfo_children():
            child.destroy()

    def _render(self, report):
        self._clear_results()
        card = theme.card(self.results)
        card.pack(fill="x")
        inset = theme.FIELD_PADDING

        def line(text, *, color=theme.TEXT, bold=False, top=3, size=theme.FONT_BODY):
            theme.wrapped_label(card, text, margin=2 * inset, color=color, bold=bold, size=size).pack(
                fill="x", padx=inset, pady=(top, 0),
            )

        line(report.risk.label, color=RISK_COLORS[report.risk], bold=True, top=inset, size=16)
        line(f"Hostname: {report.source.hostname}", top=8)
        line(f"Tên miền đăng ký: {report.source.registered_domain or 'Không xác định'}")
        if report.redirects:
            line(f"Đích cuối ghi nhận: {report.destination.hostname}", top=6)
            line(f"Tên miền đăng ký của đích: {report.destination.registered_domain or 'Không xác định'}")
        if report.title:
            line(f"Tiêu đề HTML: {report.title}", color=theme.MUTED, top=7)
        if report.findings:
            line("Lý do và bằng chứng", bold=True, top=12)
            for finding in report.findings:
                line(f"• {finding.reason}")
                if finding.evidence:
                    line(" · ".join(finding.evidence), color=theme.MUTED, size=12, top=0)
        line("Phần chưa kiểm tra", bold=True, top=12)
        for item in report.unchecked:
            line(f"• {item}", color=theme.MUTED, size=12)
        ctk.CTkFrame(card, height=inset, fg_color="transparent").pack(fill="x")

    def destroy(self):
        self.url.trace_remove("write", self._url_trace)
        self._cancel_fetch()
        self._worker.shutdown(wait=False, cancel_futures=True)
        super().destroy()
