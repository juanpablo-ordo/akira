"""Browsable, paginated previews of the exact illustrations used in the app."""
import tkinter as tk
from tkinter import ttk

from akira_expressions import get_catalog, UI_REVISION
from akira_live2d import _root
from cyber_ui import BG, PANEL, CYAN, GREEN, MUTED, TEXT, label, button
from desktop_layout import scroll_frame


def open_expression_gallery(app):
    previous = getattr(app, '_expression_gallery', None)
    if previous is not None:
        try:
            if previous.winfo_exists():
                previous.lift()
                return previous
        except tk.TclError:
            pass
    from PIL import ImageTk
    catalog = get_catalog(_root())
    win = app.service_dialog('Expresiones de Akira · R6', 900, 720)
    app._expression_gallery = win
    label(win, f'{len(catalog.entries)} caras dibujadas · elige una para verla en Akira', MUTED, 10,
          anchor='w', justify='left', wraplength=760).pack(fill='x', padx=18, pady=(0, 8))
    controls = tk.Frame(win, bg=BG)
    controls.pack(fill='x', padx=18, pady=4)
    categories = {'Todas': None}
    categories.update({entry.group_label: entry.group for entry in catalog.entries})
    selected_group = tk.StringVar(value='Todas')
    combo = ttk.Combobox(controls, textvariable=selected_group, values=tuple(categories),
                         state='readonly', style='Akira.TCombobox', width=18)
    combo.pack(side='left')
    count = label(controls, '', CYAN, 10)
    count.pack(side='right')
    feedback = label(win, UI_REVISION, CYAN, 10, anchor='w', wraplength=760)
    feedback.pack(fill='x', padx=18, pady=6)
    shell, body = scroll_frame(win, BG)
    shell.pack(fill='both', expand=True, padx=15)
    navigation = tk.Frame(win, bg=BG)
    navigation.pack(fill='x', padx=18, pady=12)
    position = [0]
    columns = [3]
    photos = []

    def use(entry):
        for avatar in app.avatars:
            avatar.set_expression(entry.id)
        feedback.configure(text=entry.id + ' · ' + entry.label)

    def render(reset=False):
        if reset:
            position[0] = 0
        group = categories[selected_group.get()]
        entries = [entry for entry in catalog.entries if group is None or entry.group == group]
        position[0] = min(position[0], max(0, (len(entries) - 1) // 9))
        start = position[0] * 9
        for child in body.winfo_children():
            child.destroy()
        photos.clear()
        for column in range(4):
            body.columnconfigure(column, weight=1 if column < columns[0] else 0,
                                 uniform='faces' if column < columns[0] else '', minsize=0)
        for i, entry in enumerate(entries[start:start + 9]):
            card = tk.Frame(body, bg=PANEL, padx=8, pady=10)
            card.grid(row=i // columns[0], column=i % columns[0], sticky='nsew', padx=4, pady=4)
            photo = ImageTk.PhotoImage(catalog.image(entry, 145, 145), master=win)
            photos.append(photo)
            preview = tk.Label(card, image=photo, bg=PANEL, cursor='hand2')
            preview.pack()
            preview.bind('<Button-1>', lambda event, chosen=entry: use(chosen))
            label(card, entry.label, TEXT, 9, anchor='center', justify='center', wraplength=185).pack(fill='x', pady=5)
            action = button(card, 'VER EN AKIRA', lambda chosen=entry: use(chosen), GREEN)
            action.configure(padx=4, pady=5)
            action.pack(fill='x')
        count.configure(text=f'{start + 1} - {min(start + 9, len(entries))} / {len(entries)}')
        back.configure(state='normal' if position[0] else 'disabled')
        forward.configure(state='normal' if start + 9 < len(entries) else 'disabled')
        shell._scroll_canvas.yview_moveto(0)
        shell._scroll_canvas._schedule_sync()

    def move(step):
        position[0] += step
        render()

    back = button(navigation, 'ANTERIORES', lambda: move(-1), MUTED)
    back.pack(side='left')
    forward = button(navigation, 'SIGUIENTES', lambda: move(1), CYAN)
    forward.pack(side='right')
    combo.bind('<<ComboboxSelected>>', lambda event: render(True))

    def fit(event):
        new_columns = 3 if event.width >= 610 else 2 if event.width >= 390 else 1
        if new_columns != columns[0]:
            columns[0] = new_columns
            win.after_idle(render)

    # The canvas is the viewport. Listening to the content frame instead
    # rebuilt cards again while their requested heights were being measured.
    shell._scroll_canvas.bind('<Configure>', fit, add='+')
    render()
    win._catalog = catalog
    win._photos = photos
    win._render_page = render
    win._next_page = lambda: move(1)
    return win
