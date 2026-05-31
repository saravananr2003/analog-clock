"""Nokia 3310-style Snake II game (Tkinter).

Run directly:

    python3 snake_game.py

Controls (Nokia keypad + arrows):
    8 / Up     — up
    2 / Down   — down
    4 / Left   — left
    6 / Right  — right
    5 / Space  — start / pause
    * / Escape — quit to title
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from tkinter import Canvas, Frame, Label, Tk, font as tkfont

# Nokia 3310 LCD (Snake II era) — light background, dark pixels
LCD_LIGHT = "#c7f0d8"
LCD_DARK = "#43523d"
LCD_MID = "#6b8f71"
BEZEL = "#2a2f28"
BEZEL_HIGHLIGHT = "#4a5248"

GRID_COLS = 12
GRID_ROWS = 16
DISPLAY_SCALE = 1.3
CELL = round(14 * DISPLAY_SCALE)
HUD_HEIGHT = round(28 * DISPLAY_SCALE)
BEZEL_PAD = round(10 * DISPLAY_SCALE)
FRAME_PAD = round(14 * DISPLAY_SCALE)
WINDOW_MARGIN = round(28 * DISPLAY_SCALE)
TICK_MS = 180
MIN_TICK_MS = 70
SPEEDUP_EVERY = 5


class Direction(Enum):
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)


class GamePhase(Enum):
    TITLE = "title"
    PLAYING = "playing"
    PAUSED = "paused"
    GAME_OVER = "game_over"


@dataclass
class Point:
    x: int
    y: int

    def shifted(self, direction: Direction) -> Point:
        dx, dy = direction.value
        return Point(self.x + dx, self.y + dy)


class SnakeGame:
    """Snake II on a faux 3310 screen."""

    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("Snake II")
        self.root.resizable(False, False)
        self.root.configure(bg=BEZEL)

        screen_w = BEZEL_PAD * 2 + GRID_COLS * CELL
        screen_h = BEZEL_PAD * 2 + HUD_HEIGHT + GRID_ROWS * CELL

        self.nokia_font = tkfont.Font(
            family="Helvetica", size=round(9 * DISPLAY_SCALE), weight="bold"
        )
        self.title_font = tkfont.Font(
            family="Helvetica", size=round(14 * DISPLAY_SCALE), weight="bold"
        )

        outer = Frame(root, bg=BEZEL, padx=FRAME_PAD, pady=FRAME_PAD)
        outer.pack()

        self.phone = Frame(outer, bg=BEZEL_HIGHLIGHT, padx=BEZEL_PAD, pady=BEZEL_PAD)
        self.phone.pack()

        self.hud = Label(
            self.phone,
            text="",
            font=self.nokia_font,
            fg=LCD_DARK,
            bg=LCD_LIGHT,
            anchor="w",
            padx=round(6 * DISPLAY_SCALE),
            pady=round(4 * DISPLAY_SCALE),
        )
        self.hud.pack(fill="x")

        play_h = GRID_ROWS * CELL
        self.canvas = Canvas(
            self.phone,
            width=GRID_COLS * CELL,
            height=play_h,
            bg=LCD_LIGHT,
            highlightthickness=0,
        )
        self.canvas.pack()

        self.root.geometry(f"{screen_w + WINDOW_MARGIN}x{screen_h + WINDOW_MARGIN}")
        self._bind_keys()

        self.phase = GamePhase.TITLE
        self.score = 0
        self.high_score = 0
        self.tick_ms = TICK_MS
        self.snake: list[Point] = []
        self.direction = Direction.RIGHT
        self.next_direction = Direction.RIGHT
        self.food: Point | None = None
        self._tick_id: str | None = None

        self._draw_frame()

    def _bind_keys(self) -> None:
        mapping = {
            "Up": Direction.UP,
            "Down": Direction.DOWN,
            "Left": Direction.LEFT,
            "Right": Direction.RIGHT,
            "8": Direction.UP,
            "2": Direction.DOWN,
            "4": Direction.LEFT,
            "6": Direction.RIGHT,
        }
        for key, direction in mapping.items():
            self.root.bind(f"<{key}>", lambda e, d=direction: self._set_direction(d))

        self.root.bind("<space>", lambda e: self._action_key())
        self.root.bind("<Return>", lambda e: self._action_key())
        self.root.bind("5", lambda e: self._action_key())
        self.root.bind("<Escape>", lambda e: self._escape_key())
        self.root.bind("*", lambda e: self._escape_key())

    def _set_direction(self, direction: Direction) -> None:
        if self.phase not in (GamePhase.PLAYING, GamePhase.PAUSED):
            return
        opposite = {
            Direction.UP: Direction.DOWN,
            Direction.DOWN: Direction.UP,
            Direction.LEFT: Direction.RIGHT,
            Direction.RIGHT: Direction.LEFT,
        }
        if direction == opposite.get(self.direction):
            return
        self.next_direction = direction
        if self.phase == GamePhase.PAUSED:
            self._resume()

    def _action_key(self) -> None:
        if self.phase == GamePhase.TITLE:
            self._start_game()
        elif self.phase == GamePhase.PLAYING:
            self._pause()
        elif self.phase == GamePhase.PAUSED:
            self._resume()
        elif self.phase == GamePhase.GAME_OVER:
            self._start_game()

    def _escape_key(self) -> None:
        self._stop_tick()
        self.phase = GamePhase.TITLE
        self._draw_frame()

    def _start_game(self) -> None:
        mid_y = GRID_ROWS // 2
        self.snake = [Point(4, mid_y), Point(3, mid_y), Point(2, mid_y)]
        self.direction = Direction.RIGHT
        self.next_direction = Direction.RIGHT
        self.score = 0
        self.tick_ms = TICK_MS
        self.phase = GamePhase.PLAYING
        self._spawn_food()
        self._update_hud()
        self._draw_frame()
        self._start_tick()

    def _pause(self) -> None:
        self.phase = GamePhase.PAUSED
        self._stop_tick()
        self._draw_frame()

    def _resume(self) -> None:
        if self.phase != GamePhase.PAUSED:
            return
        self.phase = GamePhase.PLAYING
        self._draw_frame()
        self._start_tick()

    def _start_tick(self) -> None:
        self._stop_tick()
        self._tick_id = self.root.after(self.tick_ms, self._game_tick)

    def _stop_tick(self) -> None:
        if self._tick_id is not None:
            self.root.after_cancel(self._tick_id)
            self._tick_id = None

    def _game_tick(self) -> None:
        if self.phase != GamePhase.PLAYING:
            return

        self.direction = self.next_direction
        head = self.snake[0].shifted(self.direction)

        if not self._in_bounds(head) or head in self.snake:
            self._game_over()
            return

        self.snake.insert(0, head)

        if self.food and head.x == self.food.x and head.y == self.food.y:
            self.score += 1
            if self.score > self.high_score:
                self.high_score = self.score
            if self.score % SPEEDUP_EVERY == 0 and self.tick_ms > MIN_TICK_MS:
                self.tick_ms = max(MIN_TICK_MS, self.tick_ms - 12)
            self._spawn_food()
        else:
            self.snake.pop()

        self._update_hud()
        self._draw_frame()
        self._start_tick()

    def _game_over(self) -> None:
        self.phase = GamePhase.GAME_OVER
        self._stop_tick()
        self._draw_frame()

    def _in_bounds(self, point: Point) -> bool:
        return 0 <= point.x < GRID_COLS and 0 <= point.y < GRID_ROWS

    def _spawn_food(self) -> None:
        occupied = {(p.x, p.y) for p in self.snake}
        free = [
            Point(x, y)
            for x in range(GRID_COLS)
            for y in range(GRID_ROWS)
            if (x, y) not in occupied
        ]
        self.food = random.choice(free) if free else None

    def _update_hud(self) -> None:
        self.hud.configure(text=f"  {self.score:03d}          HI {self.high_score:03d}")

    def _draw_frame(self) -> None:
        self.canvas.delete("all")

        if self.phase == GamePhase.TITLE:
            self.hud.configure(text="  Snake II")
            self._draw_center_text("SNAKE II", self.title_font)
            self._draw_center_text("Press 5", self.nokia_font, y_offset=round(22 * DISPLAY_SCALE))
            self._draw_center_text("2 4 6 8", self.nokia_font, y_offset=round(40 * DISPLAY_SCALE))
            return

        self._update_hud()
        self._draw_playfield_border()

        if self.food:
            self._draw_cell(self.food.x, self.food.y, LCD_DARK)

        for index, segment in enumerate(self.snake):
            color = LCD_DARK if index == 0 else LCD_MID
            self._draw_cell(segment.x, segment.y, color)

        if self.phase == GamePhase.PAUSED:
            self._draw_overlay("PAUSED")
        elif self.phase == GamePhase.GAME_OVER:
            self._draw_overlay("GAME OVER")

    def _draw_playfield_border(self) -> None:
        w = GRID_COLS * CELL
        h = GRID_ROWS * CELL
        self.canvas.create_rectangle(0, 0, w - 1, h - 1, outline=LCD_DARK, width=1)

    def _draw_cell(self, col: int, row: int, fill: str) -> None:
        pad = 1
        x0 = col * CELL + pad
        y0 = row * CELL + pad
        x1 = (col + 1) * CELL - pad
        y1 = (row + 1) * CELL - pad
        self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline=fill)

    def _draw_center_text(self, text: str, fnt: tkfont.Font, y_offset: int = 0) -> None:
        cx = (GRID_COLS * CELL) / 2
        cy = (GRID_ROWS * CELL) / 2 + y_offset
        self.canvas.create_text(cx, cy, text=text, fill=LCD_DARK, font=fnt)

    def _draw_overlay(self, text: str) -> None:
        w = GRID_COLS * CELL
        h = GRID_ROWS * CELL
        overlay_half = round(18 * DISPLAY_SCALE)
        self.canvas.create_rectangle(
            2, h // 2 - overlay_half, w - 2, h // 2 + overlay_half, fill=LCD_LIGHT, outline=LCD_DARK
        )
        self.canvas.create_text(w / 2, h / 2, text=text, fill=LCD_DARK, font=self.nokia_font)


def main() -> None:
    root = Tk()
    SnakeGame(root)
    root.mainloop()


if __name__ == "__main__":
    main()
