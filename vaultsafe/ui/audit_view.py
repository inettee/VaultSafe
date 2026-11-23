"""Danh sách tài khoản có mật khẩu yếu hoặc dùng lại."""

from functools import partial

import customtkinter as ctk

from .. import theme


class AuditView(ctk.CTkFrame):
    def __init__(self, parent, accounts, findings, on_open):
        super().__init__(parent, fg_color="transparent")
        self.summary = summary = ctk.CTkFrame(self, fg_color="transparent")
        self.first_open_button = None
        summary.pack(fill="x", pady=(0, theme.SECTION_GAP))
        summary.grid_columnconfigure((0, 1), weight=1, uniform="audit_counts")
        self._metric(summary, 0, "Mật khẩu yếu", len(findings.weak), theme.WARNING)
        self._metric(summary, 1, "Mật khẩu dùng lại", len(findings.reused), theme.ACCENT)

        report = theme.card(self)
        report.pack(fill="x")
        padding = theme.CARD_PADDING + 1
        theme.label(report, "Chi tiết cảnh báo", bold=True, height=22, anchor="w").pack(
            fill="x", padx=padding, pady=(padding, 6),
        )
        if not findings.weak and not findings.reused:
            theme.label(
                report, "Không phát hiện tài khoản nào.", size=13, color=theme.MUTED, anchor="w",
            ).pack(fill="x", padx=padding, pady=(0, padding))
            return
        rows = ctk.CTkFrame(report, fg_color="transparent")
        rows.pack(fill="x", padx=padding, pady=(0, padding))
        for kind, reasons in (("Yếu", findings.weak), ("Dùng lại", findings.reused)):
            for account_id, reason in reasons.items():
                button = self._warning_row(rows, accounts[account_id], kind, reason, on_open)
                if self.first_open_button is None:
                    self.first_open_button = button

    @staticmethod
    def _metric(parent, column, title, count, color):
        metric = theme.card(parent, bg=theme.HEADER_SURFACE)
        metric.grid(row=0, column=column, sticky="nsew",
                    padx=(0, theme.SPACING) if column == 0 else (theme.SPACING, 0))
        theme.label(
            metric, title, size=theme.FONT_META, color=theme.MUTED, anchor="w", height=18,
        ).pack(fill="x", padx=theme.FIELD_PADDING, pady=(theme.FIELD_PADDING, 3))
        theme.label(
            metric, str(count), size=26, color=color if count else theme.SUCCESS,
            family=theme.MONO, bold=True, height=32, anchor="w",
        ).pack(fill="x", padx=theme.FIELD_PADDING)
        theme.label(
            metric, "Tài khoản bị ảnh hưởng", size=11, color=theme.SUBTLE, height=16, anchor="w",
        ).pack(fill="x", padx=theme.FIELD_PADDING, pady=(3, theme.FIELD_PADDING))

    @staticmethod
    def _warning_row(parent, account, kind, reason, on_open):
        theme.divider(parent).pack(fill="x")
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=10)
        button = theme.button(
            row, "Mở mục", partial(on_open, account.id), width=67, height=28,
            radius=theme.SPACING, size=theme.FONT_META,
        )
        button.pack(side="right")
        theme.label(
            row, kind, size=11, color=theme.WARNING, fg_color=theme.WARNING_SURFACE,
            corner_radius=5, padx=6, height=20,
        ).pack(side="right", padx=(8, 8))
        description = ctk.CTkFrame(row, fg_color="transparent")
        description.pack(side="left", fill="x", expand=True)
        theme.wrapped_label(
            description, account.service, bold=True, height=19,
        ).pack(fill="x")
        theme.wrapped_label(
            description, reason, size=theme.FONT_META, color=theme.MUTED, height=17,
        ).pack(fill="x", pady=(2, 0))
        return button
