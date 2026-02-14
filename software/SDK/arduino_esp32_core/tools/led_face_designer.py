"""
Interactive LED face designer for the Cyobot NeoPixel hex matrix.

Layout (LED indices):
    --00000--
    -0000000-
    000000000
    -0000000-
    --00000--

Usage:
    python led_face_designer.py

Controls:
    - Left click: toggle LED on/off
    - Right click: clear LED
    - Space: clear all LEDs
    - Enter: export C++ code snippet
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional, Set, Tuple

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except ImportError:
    print("Tkinter is required. On Windows it ships with Python. On Linux install python3-tk.", file=sys.stderr)
    sys.exit(1)

# Physical LED indices in each row
LED_LAYOUT: List[List[Optional[int]]] = [
    [None, None, 0, 1, 2, 3, 4, None, None],
    [None, 5, 6, 7, 8, 9, 10, 11, None],
    [12, 13, 14, 15, 16, 17, 18, 19, 20],
    [None, 21, 22, 23, 24, 25, 26, 27, None],
    [None, None, 28, 29, 30, 31, 32, None, None],
]

CELL_SIZE = 50
PADDING = 10
BG_COLOR = "#1e1e1e"
LED_OFF = "#303030"
LED_ON = "#ffd54f"
LED_BORDER = "#555555"


@dataclass
class LedCell:
    led_index: int
    rect_id: int


class LedFaceDesigner(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Cyobot LED Face Designer")
        self.configure(bg=BG_COLOR)
        self.selected_leds: Set[int] = set()
        self._create_widgets()
        self._create_layout()
        self._bind_events()
        self._update_status()

    def _create_widgets(self) -> None:
        self.canvas = tk.Canvas(
            self,
            width=CELL_SIZE * len(LED_LAYOUT[0]) + PADDING * 2,
            height=CELL_SIZE * len(LED_LAYOUT) + PADDING * 2,
            bg=BG_COLOR,
            highlightthickness=0,
        )
        self.canvas.grid(row=0, column=0, padx=12, pady=12)

        button_frame = ttk.Frame(self)
        button_frame.grid(row=1, column=0, pady=(0, 12))

        self.btn_clear = ttk.Button(button_frame, text="Clear (Space)", command=self.clear_all)
        self.btn_clear.grid(row=0, column=0, padx=5)

        self.btn_export = ttk.Button(button_frame, text="Export (Enter)", command=self.export_snippet)
        self.btn_export.grid(row=0, column=1, padx=5)

        self.status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(self, textvariable=self.status_var, background=BG_COLOR, foreground="#d0d0d0")
        status_label.grid(row=2, column=0, pady=(0, 12))

    def _create_layout(self) -> None:
        self.cell_map: dict[Tuple[int, int], LedCell] = {}
        for row_idx, row in enumerate(LED_LAYOUT):
            for col_idx, led_idx in enumerate(row):
                x0 = PADDING + col_idx * CELL_SIZE
                y0 = PADDING + row_idx * CELL_SIZE
                x1 = x0 + CELL_SIZE
                y1 = y0 + CELL_SIZE
                fill = LED_OFF if led_idx is not None else BG_COLOR
                rect = self.canvas.create_rectangle(
                    x0,
                    y0,
                    x1,
                    y1,
                    fill=fill,
                    outline=LED_BORDER if led_idx is not None else BG_COLOR,
                    width=1,
                )
                if led_idx is not None:
                    self.canvas.create_text(
                        (x0 + x1) / 2,
                        (y0 + y1) / 2,
                        text=str(led_idx),
                        fill="#999999",
                        font=("Segoe UI", 12),
                    )
                    self.cell_map[(row_idx, col_idx)] = LedCell(led_index=led_idx, rect_id=rect)

    def _bind_events(self) -> None:
        self.canvas.bind("<Button-1>", self._on_left_click)
        self.canvas.bind("<Button-3>", self._on_right_click)
        self.bind("<space>", lambda _: self.clear_all())
        self.bind("<Return>", lambda _: self.export_snippet())

    def _canvas_to_cell(self, event: tk.Event) -> Optional[LedCell]:
        col = (event.x - PADDING) // CELL_SIZE
        row = (event.y - PADDING) // CELL_SIZE
        cell = self.cell_map.get((row, col))
        return cell

    def _on_left_click(self, event: tk.Event) -> None:
        cell = self._canvas_to_cell(event)
        if cell:
            if cell.led_index in self.selected_leds:
                self.selected_leds.remove(cell.led_index)
            else:
                self.selected_leds.add(cell.led_index)
            self._update_cell(cell)
            self._update_status()

    def _on_right_click(self, event: tk.Event) -> None:
        cell = self._canvas_to_cell(event)
        if cell and cell.led_index in self.selected_leds:
            self.selected_leds.remove(cell.led_index)
            self._update_cell(cell)
            self._update_status()

    def _update_cell(self, cell: LedCell) -> None:
        fill = LED_ON if cell.led_index in self.selected_leds else LED_OFF
        self.canvas.itemconfig(cell.rect_id, fill=fill)

    def _update_status(self) -> None:
        indices = sorted(self.selected_leds)
        preview = " ".join(map(str, indices))
        self.status_var.set(f"LEDs: {len(indices)} selected :: {preview}")

    def clear_all(self) -> None:
        self.selected_leds.clear()
        for cell in self.cell_map.values():
            self._update_cell(cell)
        self._update_status()

    def export_snippet(self) -> None:
        indices = sorted(self.selected_leds)
        if not indices:
            messagebox.showinfo("Export", "No LEDs selected.")
            return

        array_literal = ", ".join(map(str, indices))
        cpp_snippet = (
            f"const uint8_t FACE_CUSTOM[] = {{{array_literal}}};\n"
            f"const FaceExpression FACE_EXPRESSIONS[] = {{\n"
            f"    {{FACE_CUSTOM, static_cast<uint8_t>(sizeof(FACE_CUSTOM) / sizeof(FACE_CUSTOM[0]))}}\n"
            f"}};"
        )
        json_data = json.dumps(indices, indent=2)

        result_window = tk.Toplevel(self)
        result_window.title("Export Result")
        result_window.configure(bg=BG_COLOR)

        ttk.Label(result_window, text="C++ snippet:", background=BG_COLOR, foreground="#d0d0d0").grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 4)
        )
        cpp_text = tk.Text(result_window, wrap="word", width=70, height=6, bg="#202020", fg="#e0e0e0")
        cpp_text.insert("1.0", cpp_snippet)
        cpp_text.configure(state="disabled")
        cpp_text.grid(row=1, column=0, padx=12, pady=(0, 12))

        ttk.Label(result_window, text="JSON array:", background=BG_COLOR, foreground="#d0d0d0").grid(
            row=2, column=0, sticky="w", padx=12, pady=(0, 4)
        )
        json_text = tk.Text(result_window, wrap="word", width=70, height=6, bg="#202020", fg="#e0e0e0")
        json_text.insert("1.0", json_data)
        json_text.configure(state="disabled")
        json_text.grid(row=3, column=0, padx=12, pady=(0, 12))

        ttk.Button(result_window, text="Close", command=result_window.destroy).grid(
            row=4, column=0, pady=(0, 12)
        )


def main() -> None:
    app = LedFaceDesigner()
    app.mainloop()


if __name__ == "__main__":
    main()
