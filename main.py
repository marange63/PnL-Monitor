import tkinter as tk
import sv_ttk
from app import PnLApp

if __name__ == '__main__':
    root = tk.Tk()
    sv_ttk.set_theme("light")
    PnLApp(root)
    root.mainloop()
