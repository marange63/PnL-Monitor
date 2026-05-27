import tkinter as tk


class Tooltip:
    """Floating yellow tooltip window. One instance per app; reused across panes."""

    def __init__(self, root: tk.Tk, font):
        self._win = tk.Toplevel(root)
        self._win.wm_overrideredirect(True)
        self._win.withdraw()
        self._label = tk.Label(
            self._win, font=font, justify="left",
            background="#ffffcc", relief="solid", bd=1, padx=6, pady=4,
        )
        self._label.pack()

    def show(self, text: str, widget, event) -> None:
        self._label.config(text=text)
        rx = widget.winfo_rootx() + int(event.x) + 15
        ry = widget.winfo_rooty() + int(widget.winfo_height() - event.y) - 10
        self._win.geometry(f"+{rx}+{ry}")
        self._win.deiconify()

    def hide(self) -> None:
        self._win.withdraw()
