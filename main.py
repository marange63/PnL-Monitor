import logging
import tkinter as tk

import sv_ttk

from app import PnLApp

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
    )
    root = tk.Tk()
    sv_ttk.set_theme("light")
    PnLApp(root)
    root.mainloop()
