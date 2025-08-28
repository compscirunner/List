#!/usr/bin/env python3
"""
mlist.py — a tiny, fast, cross‑platform text viewer inspired by LIST.COM

Now with optional **directory browsing**:
  • Pass a folder instead of a file and you’ll get a file selector.
  • Use ↑/↓ to move, Enter to open, Backspace to go up.
  • Once inside a file, the normal viewer UI takes over.

Usage:
  python mlist.py <path-to-text-file>
  python mlist.py <folder>
  cat file.txt | python mlist.py -
"""
from __future__ import annotations

import argparse
import curses
import os
import sys
from typing import List, Optional

TABSIZE = 8


def read_text(path: Optional[str]) -> List[str]:
    if path is None:
        raise ValueError("No input file provided")
    if path == "-":
        data = sys.stdin.read()
    else:
        with open(path, "rb") as f:
            raw = f.read()
        data = raw.decode("utf-8", errors="replace")
    lines = data.splitlines()
    if not lines:
        lines = [""]
    return lines


class ViewerState:
    def __init__(self, lines: List[str], filename: str):
        self.lines = lines
        self.filename = filename
        self.total = len(lines)
        self.cur = 0
        self.top = 0
        self.hscroll = 0
        self.show_linenums = False
        self.search_q: Optional[str] = None

    def prefix(self, idx: int) -> str:
        return f"{idx+1:6d} " if self.show_linenums else ""


def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


# --- Directory Browser ---

def browse_dir(stdscr, start_path: str) -> str:
    """Simple curses directory browser. Returns selected file path."""
    path = os.path.abspath(start_path)
    entries = []
    idx = 0

    while True:
        stdscr.erase()
        maxy, maxx = stdscr.getmaxyx()
        try:
            entries = [".."] + sorted(os.listdir(path))
        except Exception as e:
            entries = [".."]

        for i, name in enumerate(entries[: maxy - 1]):
            full = os.path.join(path, name)
            mark = "/" if os.path.isdir(full) else ""
            s = f"{name}{mark}"
            attr = curses.A_REVERSE if i == idx else curses.A_NORMAL
            try:
                stdscr.addnstr(i, 0, s, maxx, attr)
            except curses.error:
                pass

        stdscr.addnstr(maxy - 1, 0, f"Browse: {path}", maxx, curses.A_REVERSE)
        stdscr.refresh()

        ch = stdscr.getch()
        if ch in (ord('q'), 27):
            sys.exit(0)
        elif ch in (curses.KEY_UP, ord('k')):
            idx = clamp(idx - 1, 0, len(entries) - 1)
        elif ch in (curses.KEY_DOWN, ord('j')):
            idx = clamp(idx + 1, 0, len(entries) - 1)
        elif ch in (curses.KEY_ENTER, 10, 13):
            sel = entries[idx]
            full = os.path.join(path, sel)
            if sel == "..":
                path = os.path.dirname(path)
                idx = 0
            elif os.path.isdir(full):
                path = full
                idx = 0
            else:
                return full
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            path = os.path.dirname(path)
            idx = 0


def draw(stdscr, state: ViewerState) -> None:
    """Draw the viewer screen."""
    stdscr.erase()
    maxy, maxx = stdscr.getmaxyx()
    
    # Draw visible lines
    for y in range(maxy - 1):
        line_idx = state.top + y
        if line_idx >= state.total:
            break
            
        line = state.lines[line_idx]
        prefix = state.prefix(line_idx)
        
        # Handle horizontal scrolling
        display_line = line[state.hscroll:] if state.hscroll < len(line) else ""
        full_line = prefix + display_line
        
        # Highlight current line
        attr = curses.A_REVERSE if line_idx == state.cur else curses.A_NORMAL
        
        try:
            stdscr.addnstr(y, 0, full_line, maxx, attr)
        except curses.error:
            pass
    
    # Status line
    status = f"File: {state.filename} | Line {state.cur + 1}/{state.total}"
    if state.search_q:
        status += f" | Search: {state.search_q}"
    if state.show_linenums:
        status += " | LineNums: ON"
    
    try:
        stdscr.addnstr(maxy - 1, 0, status, maxx, curses.A_REVERSE)
    except curses.error:
        pass
    
    stdscr.refresh()


def search_forward(state: ViewerState, query: str, start_line: int = None) -> int:
    """Search for query starting from start_line. Returns line number or -1."""
    if start_line is None:
        start_line = state.cur + 1
    
    for i in range(start_line, state.total):
        if query.lower() in state.lines[i].lower():
            return i
    return -1


def search_backward(state: ViewerState, query: str, start_line: int = None) -> int:
    """Search for query backwards from start_line. Returns line number or -1."""
    if start_line is None:
        start_line = state.cur - 1
    
    for i in range(start_line, -1, -1):
        if query.lower() in state.lines[i].lower():
            return i
    return -1


def run(stdscr, lines: List[str], filename: str) -> None:
    """Main viewer loop."""
    curses.curs_set(0)  # Hide cursor
    stdscr.nodelay(False)
    stdscr.keypad(True)
    
    state = ViewerState(lines, filename)
    
    while True:
        maxy, maxx = stdscr.getmaxyx()
        
        # Ensure current line is visible
        if state.cur < state.top:
            state.top = state.cur
        elif state.cur >= state.top + maxy - 1:
            state.top = state.cur - maxy + 2
        
        draw(stdscr, state)
        
        ch = stdscr.getch()
        
        # Navigation
        if ch in (ord('q'), ord('Q'), 27):  # ESC
            break
        elif ch in (curses.KEY_UP, ord('k')):
            state.cur = clamp(state.cur - 1, 0, state.total - 1)
        elif ch in (curses.KEY_DOWN, ord('j')):
            state.cur = clamp(state.cur + 1, 0, state.total - 1)
        elif ch in (curses.KEY_LEFT, ord('h')):
            state.hscroll = clamp(state.hscroll - 1, 0, 1000)
        elif ch in (curses.KEY_RIGHT, ord('l')):
            state.hscroll = clamp(state.hscroll + 1, 0, 1000)
        elif ch in (curses.KEY_PPAGE, ord('b')):  # Page Up
            state.cur = clamp(state.cur - (maxy - 2), 0, state.total - 1)
        elif ch in (curses.KEY_NPAGE, ord(' ')):  # Page Down / Space
            state.cur = clamp(state.cur + (maxy - 2), 0, state.total - 1)
        elif ch in (curses.KEY_HOME, ord('g')):
            state.cur = 0
        elif ch in (curses.KEY_END, ord('G')):
            state.cur = state.total - 1
        elif ch == ord('n'):  # Toggle line numbers
            state.show_linenums = not state.show_linenums
        elif ch == ord('/'):  # Search
            curses.echo()
            stdscr.addstr(maxy - 1, 0, "Search: ")
            stdscr.refresh()
            query = stdscr.getstr().decode('utf-8')
            curses.noecho()
            if query:
                state.search_q = query
                result = search_forward(state, query, state.cur)
                if result != -1:
                    state.cur = result
        elif ch == ord('?'):  # Search backward
            curses.echo()
            stdscr.addstr(maxy - 1, 0, "Search backward: ")
            stdscr.refresh()
            query = stdscr.getstr().decode('utf-8')
            curses.noecho()
            if query:
                state.search_q = query
                result = search_backward(state, query, state.cur)
                if result != -1:
                    state.cur = result
        elif ch == ord('F') and state.search_q:  # Find next
            result = search_forward(state, state.search_q, state.cur + 1)
            if result != -1:
                state.cur = result


def run_viewer(stdscr, lines: List[str], filename: str) -> None:
    run(stdscr, lines, filename)


def main():
    ap = argparse.ArgumentParser(description="LIST.COM-style text viewer with dir browser")
    ap.add_argument("path", help="File, folder, or '-' for stdin")
    args = ap.parse_args()

    if os.path.isdir(args.path):
        # launch browser
        sel = curses.wrapper(browse_dir, args.path)
        lines = read_text(sel)
        curses.wrapper(run_viewer, lines, sel)
    else:
        lines = read_text(args.path)
        curses.wrapper(run_viewer, lines, args.path)


if __name__ == "__main__":
    main()
