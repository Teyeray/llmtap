"""Shared colors for CLI tables and the TUI.

Plain style strings, so they render in any Rich or Textual console.
"""

from __future__ import annotations

ACCENT = "#38bdf8"      # sky
ACCENT_ALT = "#a78bfa"  # violet
OK = "#34d399"          # emerald
WARN = "#fbbf24"        # amber
BAD = "#f87171"         # rose
DIM = "#64748b"         # slate

HEADER = f"bold {ACCENT}"
TITLE = f"italic {DIM}"

VERDICT = {"ok": OK, "partial": WARN, "fail": BAD, "inconclusive": BAD}


def tui_theme():
    """Textual theme that matches the CLI colors. None on old Textual."""
    try:
        from textual.theme import Theme
    except ImportError:
        return None
    return Theme(
        name="llmtap",
        primary=ACCENT,
        secondary=ACCENT_ALT,
        accent=OK,
        foreground="#e2e8f0",
        background="#0b1120",
        surface="#111827",
        panel="#1e293b",
        success=OK,
        warning=WARN,
        error=BAD,
        dark=True,
    )
