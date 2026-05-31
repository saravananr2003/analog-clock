"""Tkinter analog clock UI.

Run this module directly to display a resizable analog clock:

    python3 analog_clock.py
"""

from __future__ import annotations

import math
from datetime import datetime
from tkinter import Canvas, Tk


class AnalogClock:
    """Draws and updates an analog clock on a Tkinter canvas."""

    def __init__(self, root: Tk, width: int = 420, height: int = 420) -> None:
        self.root = root
        self.root.title("Analog Clock")
        self.root.minsize(260, 260)

        self.canvas = Canvas(root, width=width, height=height, bg="#f8fafc", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._draw_clock)

        self._draw_clock()
        self._tick()

    def _tick(self) -> None:
        self._draw_clock()
        self.root.after(1000, self._tick)

    def _draw_clock(self, event: object | None = None) -> None:
        del event
        self.canvas.delete("all")

        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        size = min(width, height)
        center_x = width / 2
        center_y = height / 2
        radius = size * 0.42

        self._draw_face(center_x, center_y, radius)
        self._draw_hands(center_x, center_y, radius)

    def _draw_face(self, center_x: float, center_y: float, radius: float) -> None:
        self.canvas.create_oval(
            center_x - radius,
            center_y - radius,
            center_x + radius,
            center_y + radius,
            fill="#ffffff",
            outline="#1e293b",
            width=4,
        )

        for marker in range(60):
            angle = math.radians(marker * 6 - 90)
            outer_x = center_x + math.cos(angle) * radius * 0.92
            outer_y = center_y + math.sin(angle) * radius * 0.92

            if marker % 5 == 0:
                inner_scale = 0.78
                width = 4
                fill = "#0f172a"
            else:
                inner_scale = 0.86
                width = 1
                fill = "#64748b"

            inner_x = center_x + math.cos(angle) * radius * inner_scale
            inner_y = center_y + math.sin(angle) * radius * inner_scale
            self.canvas.create_line(inner_x, inner_y, outer_x, outer_y, fill=fill, width=width)

        for hour in range(1, 13):
            angle = math.radians(hour * 30 - 90)
            number_x = center_x + math.cos(angle) * radius * 0.65
            number_y = center_y + math.sin(angle) * radius * 0.65
            self.canvas.create_text(
                number_x,
                number_y,
                text=str(hour),
                fill="#0f172a",
                font=("Helvetica", max(12, int(radius * 0.12)), "bold"),
            )

    def _draw_hands(self, center_x: float, center_y: float, radius: float) -> None:
        now = datetime.now()

        second = now.second
        minute = now.minute + second / 60
        hour = (now.hour % 12) + minute / 60

        self._draw_hand(center_x, center_y, radius * 0.48, hour * 30, "#0f172a", max(5, int(radius * 0.05)))
        self._draw_hand(center_x, center_y, radius * 0.68, minute * 6, "#334155", max(3, int(radius * 0.03)))
        self._draw_hand(center_x, center_y, radius * 0.76, second * 6, "#dc2626", max(1, int(radius * 0.015)))

        hub_radius = max(5, int(radius * 0.045))
        self.canvas.create_oval(
            center_x - hub_radius,
            center_y - hub_radius,
            center_x + hub_radius,
            center_y + hub_radius,
            fill="#dc2626",
            outline="#ffffff",
            width=2,
        )

    def _draw_hand(
        self,
        center_x: float,
        center_y: float,
        length: float,
        degrees: float,
        fill: str,
        width: int,
    ) -> None:
        angle = math.radians(degrees - 90)
        end_x = center_x + math.cos(angle) * length
        end_y = center_y + math.sin(angle) * length
        self.canvas.create_line(center_x, center_y, end_x, end_y, fill=fill, width=width, capstyle="round")


def main() -> None:
    root = Tk()
    AnalogClock(root)
    root.mainloop()


if __name__ == "__main__":
    main()
