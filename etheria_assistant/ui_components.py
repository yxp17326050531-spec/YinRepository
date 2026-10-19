"""Dialogs keep actions above a scrollable form at every supported DPI."""
import tkinter as tk
from tkinter import ttk


class FormDialog(tk.Toplevel):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(True, True)
        # Allocate actions FIRST. A long form can only shrink the canvas.
        self.actions = ttk.Frame(self, padding=(12, 10))
        self.actions.pack(side='top', fill='x')
        outer = ttk.Frame(self)
        outer.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0, background='#eef2f6')
        bar = ttk.Scrollbar(outer, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.content = ttk.Frame(self.canvas, padding=(18, 8, 18, 18))
        self.form_id = self.canvas.create_window(0, 0, window=self.content, anchor='nw')
        self.content.bind('<Configure>', lambda event: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda event: self.canvas.itemconfigure(self.form_id, width=event.width))
        self.bind('<MouseWheel>', self.scroll)
        self.bind('<Button-4>', lambda event: self.canvas.yview_scroll(-1, 'units'))
        self.bind('<Button-5>', lambda event: self.canvas.yview_scroll(1, 'units'))
        self.bind('<Escape>', lambda event: self.destroy())
        self.bind('<FocusIn>', self.reveal_focus, add='+')

    def scroll(self, event):
        # Text widgets keep their own internal wheel behavior.
        if isinstance(event.widget, tk.Text):
            return
        steps = -int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
        self.canvas.yview_scroll(steps, 'units')
        return 'break'

    def reveal_focus(self, event):
        widget = event.widget
        try:
            if not str(widget).startswith(str(self.content) + '.'):
                return
            self.update_idletasks()
            top = self.canvas.canvasy(0)
            y = widget.winfo_rooty() - self.content.winfo_rooty()
            total = max(1, self.content.winfo_height())
            if y < top:
                self.canvas.yview_moveto(y / total)
            elif y + widget.winfo_height() > top + self.canvas.winfo_height():
                self.canvas.yview_moveto((y + widget.winfo_height() - self.canvas.winfo_height()) / total)
        except tk.TclError:
            pass

    def finish(self, first_focus=None):
        self.update_idletasks()
        available_width = max(300, self.winfo_screenwidth() - 60)
        available_height = max(240, self.winfo_screenheight() - 120)
        width = min(available_width, max(620, self.actions.winfo_reqwidth() + 24, self.content.winfo_reqwidth() + 30))
        height = min(available_height, max(460, self.content.winfo_reqheight() + self.actions.winfo_reqheight() + 30))
        self.geometry(f'{width}x{height}')
        self.minsize(min(width, max(380, self.actions.winfo_reqwidth())), min(height, 280))
        self.grab_set()
        if first_focus:
            first_focus.focus_set()
