"""Native picker boundary for the local workspace manager.

The UI never supplies a browser-selected path.  These methods are the only
place where a native dialog is requested, which keeps the boundary easy to
mock in backend tests and lets headless hosts degrade explicitly.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..contracts import PickerResult, is_absolute_local_path


def _unavailable(message: str) -> PickerResult:
    return PickerResult(
        status="unavailable",
        code="native_picker_unavailable",
        message=message,
    )


def _initial_directory(initial_path: str | None) -> str | None:
    if not initial_path:
        return None
    candidate = Path(initial_path)
    if candidate.is_dir():
        return str(candidate)
    if candidate.parent.is_dir():
        return str(candidate.parent)
    return None


class NativePicker:
    """Small, injectable adapter around native Windows file dialogs."""

    @staticmethod
    def _available() -> bool:
        return sys.platform == "win32"

    @staticmethod
    def _root_and_dialog():
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        return root, filedialog

    def pick_folder(self, *, purpose: str, initial_path: str | None) -> PickerResult:
        if not self._available():
            return _unavailable("Native folder selection is available only on the local Windows host.")
        root = None
        try:
            root, filedialog = self._root_and_dialog()
            selected = filedialog.askdirectory(
                parent=root,
                title=f"Select {purpose} folder",
                initialdir=_initial_directory(initial_path),
                mustexist=True,
            )
            if not selected:
                return PickerResult(status="cancelled")
            if not is_absolute_local_path(selected):
                return _unavailable("The native picker returned a non-local path.")
            return PickerResult(status="selected", path=selected)
        except Exception as exc:  # pragma: no cover - platform/dialog dependent
            return _unavailable(f"Native folder selection is unavailable: {type(exc).__name__}: {exc}")
        finally:
            if root is not None:
                try:
                    root.destroy()
                except Exception:
                    pass
    def pick_database(
        self,
        *,
        mode: str,
        initial_path: str | None,
        suggested_name: str,
    ) -> PickerResult:
        if not self._available():
            return _unavailable("Native database selection is available only on the local Windows host.")
        root = None
        try:
            root, filedialog = self._root_and_dialog()
            options = {
                "parent": root,
                "title": "Open review database" if mode == "open" else "Create review database",
                "initialdir": _initial_directory(initial_path),
                "filetypes": [("SQLite database", "*.sqlite *.db"), ("All files", "*.*")],
            }
            if mode == "open":
                selected = filedialog.askopenfilename(**options)
            else:
                selected = filedialog.asksaveasfilename(
                    **options,
                    initialfile=suggested_name,
                    defaultextension=".sqlite",
                )
            if not selected:
                return PickerResult(status="cancelled")
            if not is_absolute_local_path(selected):
                return _unavailable("The native picker returned a non-local path.")
            return PickerResult(status="selected", path=selected)
        except Exception as exc:  # pragma: no cover - platform/dialog dependent
            return _unavailable(f"Native database selection is unavailable: {type(exc).__name__}: {exc}")
        finally:
            if root is not None:
                try:
                    root.destroy()
                except Exception:
                    pass
