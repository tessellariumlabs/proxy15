"""A local Tk desktop interface; importing this module does not open a window."""
from __future__ import annotations

import argparse
import queue
import threading
from dataclasses import replace
from pathlib import Path

from .cli import MAX_COPIES, PAPER_SIZES, collect_images, options_from_args
from .render import create_job, plan_layout


def launch() -> None:
    """Open a desktop exporter without issuing printer or network commands."""
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        raise RuntimeError("The desktop interface needs Tkinter. Install your system's Python Tk package, or use proxy15 render.") from exc
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise RuntimeError("The desktop interface needs a graphical display. Use proxy15 render in a terminal on this computer.") from exc
    root.title("Proxy 15 · Family card studio")
    root.geometry("880x850")
    root.minsize(720, 640)
    style = ttk.Style(root)
    style.configure("TLabel", padding=(0, 2))
    style.configure("TButton", padding=(10, 6))
    style.configure("Title.TLabel", font=("TkDefaultFont", 20, "bold"))
    style.configure("Help.TLabel", foreground="#405466")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)

    header = ttk.Frame(root, padding=(24, 18, 24, 10))
    header.grid(row=0, column=0, sticky="ew")
    ttk.Label(header, text="Create something to keep", style="Title.TLabel").pack(anchor="w")
    ttk.Label(header, text="Make Christmas and family cards for your own printer. Artwork stays on this computer.", wraplength=810, style="Help.TLabel").pack(anchor="w", pady=(5, 0))

    canvas_frame = ttk.Frame(root)
    canvas_frame.grid(row=1, column=0, sticky="nsew")
    canvas_frame.columnconfigure(0, weight=1)
    canvas_frame.rowconfigure(0, weight=1)
    canvas = tk.Canvas(canvas_frame, highlightthickness=0)
    scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")
    form = ttk.Frame(canvas, padding=(24, 6, 24, 16))
    window = canvas.create_window((0, 0), window=form, anchor="nw")
    form.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
    form.columnconfigure(0, weight=1)

    def scroll_wheel(event: object) -> str:
        direction = -1 if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0 else 1
        canvas.yview_scroll(direction, "units")
        return "break"

    root.bind("<MouseWheel>", scroll_wheel)
    root.bind("<Button-4>", scroll_wheel)
    root.bind("<Button-5>", scroll_wheel)

    def reveal_focus(event: object) -> None:
        widget = event.widget
        if not str(widget).startswith(str(form) + "."):
            return
        y = widget.winfo_y()
        parent = widget.master
        while parent is not form:
            y += parent.winfo_y()
            parent = parent.master
        top = canvas.canvasy(0)
        bottom = canvas.canvasy(canvas.winfo_height())
        height = max(1, form.winfo_height())
        if y < top:
            canvas.yview_moveto(y / height)
        elif y + widget.winfo_height() > bottom:
            canvas.yview_moveto((y + widget.winfo_height() - canvas.winfo_height()) / height)

    root.bind("<FocusIn>", reveal_focus)

    variables = {
        "fronts": tk.StringVar(), "back": tk.StringVar(),
        "output": tk.StringVar(value=str(Path.home() / "Proxy15-cards")),
        "paper": tk.StringVar(value="Letter"), "orientation": tk.StringVar(value="Portrait"),
        "units": tk.StringVar(value="in"), "paper_width": tk.StringVar(value="8.5"),
        "paper_height": tk.StringVar(value="11"), "card_width": tk.StringVar(value="2.5"),
        "card_height": tk.StringVar(value="3.5"), "margin": tk.StringVar(value="0.25"),
        "gutter": tk.StringVar(value="0.25"), "bleed": tk.StringVar(value="0"),
        "dpi": tk.StringVar(value="300"), "copies": tk.StringVar(value="1"),
        "fold": tk.StringVar(value="none"), "flip": tk.StringVar(value="long"),
        "fit": tk.StringVar(value="contain"), "rotate": tk.StringVar(value="auto"),
        "marks": tk.BooleanVar(value=True), "overwrite": tk.BooleanVar(value=False),
    }
    images_filter = [("Artwork images", "*.png *.jpg *.jpeg *.tif *.tiff *.webp *.bmp"), ("All files", "*")]

    def section(text: str, row: int) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(form, text=text, padding=12)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        frame.columnconfigure(1, weight=1)
        return frame

    source = section("1 · Artwork and destination", 0)

    def choose_file(key: str) -> None:
        value = filedialog.askopenfilename(parent=root, title="Choose artwork", filetypes=images_filter)
        if value:
            variables[key].set(value)

    def choose_directory(key: str) -> None:
        value = filedialog.askdirectory(parent=root, title="Choose folder", mustexist=key != "output")
        if value:
            variables[key].set(value)

    for row, (text, key) in enumerate([("Front artwork", "fronts"), ("Shared back (optional)", "back"), ("Output folder", "output")]):
        ttk.Label(source, text=text).grid(row=row, column=0, sticky="w", padx=(0, 10))
        ttk.Entry(source, textvariable=variables[key]).grid(row=row, column=1, sticky="ew", pady=4)
        if key == "fronts":
            ttk.Button(source, text="File...", command=lambda: choose_file("fronts")).grid(row=row, column=2, padx=(8, 3))
            ttk.Button(source, text="Folder...", command=lambda: choose_directory("fronts")).grid(row=row, column=3)
        elif key == "back":
            ttk.Button(source, text="File...", command=lambda: choose_file("back")).grid(row=row, column=2, padx=(8, 3))
            ttk.Button(source, text="Clear", command=lambda: variables["back"].set("")).grid(row=row, column=3)
        else:
            ttk.Button(source, text="Folder...", command=lambda: choose_directory("output")).grid(row=row, column=2, columnspan=2, sticky="ew", padx=(8, 0))
    ttk.Label(source, text="A folder uses images in filename order. Use 01, 02, ... to keep the order predictable.", wraplength=740, style="Help.TLabel").grid(row=3, column=0, columnspan=4, sticky="w", pady=(5, 0))

    paper = section("2 · Paper and finished card size", 1)

    def choice(parent: object, label: str, key: str, values: list[str], row: int, column: int = 0) -> ttk.Combobox:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=(0, 10))
        widget = ttk.Combobox(parent, textvariable=variables[key], values=values, state="readonly", width=16)
        widget.grid(row=row, column=column + 1, sticky="ew", pady=4, padx=(0, 12))
        return widget

    def number(parent: object, label: str, key: str, row: int, column: int = 0) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=(0, 10))
        widget = ttk.Entry(parent, textvariable=variables[key], width=16)
        widget.grid(row=row, column=column + 1, sticky="ew", pady=4, padx=(0, 12))
        return widget

    paper.columnconfigure(3, weight=1)
    choice(paper, "Paper", "paper", [*PAPER_SIZES, "Custom"], 0)
    units_box = choice(paper, "Dimensions in", "units", ["in", "mm"], 0, 2)
    custom_width = number(paper, "Custom paper width", "paper_width", 1)
    custom_height = number(paper, "Custom paper height", "paper_height", 1, 2)
    choice(paper, "Preset orientation", "orientation", ["Portrait", "Landscape"], 2)
    number(paper, "Copies (single image)", "copies", 2, 2)
    number(paper, "Finished card width", "card_width", 3)
    number(paper, "Finished card height", "card_height", 3, 2)
    choice(paper, "Fold", "fold", ["none", "vertical", "horizontal"], 4)
    choice(paper, "Duplex flip edge", "flip", ["long", "short"], 4, 2)
    ttk.Label(paper, text="Folded artwork contains a full spread: vertical = twice the width; horizontal = twice the height. A shared back is the full inside spread. For a flat card, choose none.", wraplength=740, style="Help.TLabel").grid(row=5, column=0, columnspan=4, sticky="w", pady=(6, 0))

    def set_paper_state(*_args: object) -> None:
        state = "normal" if variables["paper"].get() == "Custom" else "disabled"
        custom_width.configure(state=state)
        custom_height.configure(state=state)

    variables["paper"].trace_add("write", set_paper_state)
    set_paper_state()
    previous_units = "in"

    def change_units(_event: object = None) -> None:
        nonlocal previous_units
        current = variables["units"].get()
        if current != previous_units:
            factor = 25.4 if current == "mm" else 1 / 25.4
            for key in ("paper_width", "paper_height", "card_width", "card_height", "margin", "gutter", "bleed"):
                try:
                    variables[key].set(f"{float(variables[key].get()) * factor:.8g}")
                except ValueError:
                    pass
            previous_units = current

    units_box.bind("<<ComboboxSelected>>", change_units)

    settings = section("3 · Print layout", 2)
    settings.columnconfigure(3, weight=1)
    number(settings, "Printer margin", "margin", 0)
    number(settings, "Gutter between cards", "gutter", 0, 2)
    number(settings, "Bleed past cut edge", "bleed", 1)
    number(settings, "Resolution (DPI)", "dpi", 1, 2)
    choice(settings, "Artwork fit", "fit", ["contain", "cover"], 2)
    choice(settings, "Rotate on paper", "rotate", ["auto", "never", "always"], 2, 2)
    ttk.Checkbutton(settings, text="Include cut and fold guides", variable=variables["marks"]).grid(row=3, column=0, columnspan=2, sticky="w", pady=5)
    ttk.Checkbutton(settings, text="Replace existing generated files", variable=variables["overwrite"]).grid(row=3, column=2, columnspan=2, sticky="w", pady=5)
    ttk.Label(settings, text="Contain preserves the full image with white space; cover fills the card and crops edges. Allow a margin your printer supports. Gutter must be at least twice the bleed.", wraplength=740, style="Help.TLabel").grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))

    printing = section("Print with confidence", 3)
    ttk.Label(printing, text="Export a PDF, then open it in your PDF reader. Select the matching paper size and Actual size / 100%; disable fit-to-page. For two-sided artwork, enable duplex and match the selected flip edge. Test one sheet before your full batch. Manual duplex PDFs are included when there is back artwork.", wraplength=740, style="Help.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")

    footer = ttk.Frame(root, padding=(24, 12, 24, 18))
    footer.grid(row=2, column=0, sticky="ew")
    footer.columnconfigure(0, weight=1)
    status = tk.StringVar(value="Ready to export. No print jobs are sent automatically.")
    ttk.Label(footer, textvariable=status, wraplength=570).grid(row=0, column=0, sticky="w", padx=(0, 12))
    export = ttk.Button(footer, text="Export print PDFs")
    export.grid(row=0, column=1, sticky="e")
    messages: queue.Queue = queue.Queue()
    busy = False

    def submit() -> None:
        nonlocal busy
        if busy:
            return
        try:
            if not variables["fronts"].get().strip():
                raise ValueError("Choose a front image or artwork folder first.")
            if not variables["output"].get().strip():
                raise ValueError("Choose an output folder.")
            values = {key: variables[key].get() for key in variables}
            fronts_path = Path(values["fronts"]).expanduser()
            fronts = collect_images(fronts_path)
            copies = int(values["copies"])
            if copies < 1:
                raise ValueError("Copies must be a whole number greater than zero.")
            if copies > MAX_COPIES:
                raise ValueError(f"Copies is limited to {MAX_COPIES:,} per export. Split a larger batch into separate exports.")
            if copies != 1 and not fronts_path.is_file():
                raise ValueError("Copies applies to one image. Use 1 copy when selecting an artwork folder.")
            fronts *= copies
            backs = None
            if values["back"].strip():
                back = Path(values["back"]).expanduser()
                if not back.is_file():
                    raise ValueError("The shared back must be one image file.")
                backs = collect_images(back) * len(fronts)
            args = argparse.Namespace(
                paper=values["paper"], units=values["units"],
                paper_width=float(values["paper_width"]) if values["paper"] == "Custom" else None,
                paper_height=float(values["paper_height"]) if values["paper"] == "Custom" else None,
                card_width=float(values["card_width"]), card_height=float(values["card_height"]),
                margin=float(values["margin"]), gutter=float(values["gutter"]), bleed=float(values["bleed"]),
                dpi=int(values["dpi"]), flip=values["flip"], rotate=values["rotate"],
                fold=values["fold"], fit=values["fit"], no_marks=not values["marks"],
            )
            options = options_from_args(args)
            if values["paper"] != "Custom" and values["orientation"] == "Landscape":
                options = replace(options, page_width_in=options.page_height_in, page_height_in=options.page_width_in)
            plan_layout(options)
            output_dir = Path(values["output"]).expanduser()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Check the card settings", str(exc), parent=root)
            return
        busy = True
        export.configure(state="disabled")
        status.set("Creating PDFs and previews...")

        def worker() -> None:
            try:
                result = create_job(fronts, backs, output_dir, options, overwrite=values["overwrite"])
                messages.put((True, result, options, backs is not None))
            except Exception as exc:
                messages.put((False, str(exc), None, False))

        threading.Thread(target=worker, daemon=True).start()

    def poll() -> None:
        nonlocal busy
        try:
            success, payload, options, duplex = messages.get_nowait()
        except queue.Empty:
            root.after(100, poll)
            return
        busy = False
        export.configure(state="normal")
        if success:
            status.set(f"Saved {payload.sheet_count} sheet(s) to {payload.pdf_path.parent}")
            advice = f"\nEnable duplex and flip on the {options.duplex_flip} edge." if duplex else "\nDisable duplex for these one-sided cards."
            messagebox.showinfo("Cards are ready", f"PDF: {payload.pdf_path}\n\nPrint at Actual size / 100% with the matching paper size.{advice}\nTest one sheet before printing your batch.", parent=root)
        else:
            status.set("Export stopped. Adjust the settings and try again.")
            messagebox.showerror("Could not export cards", payload, parent=root)
        root.after(100, poll)

    export.configure(command=submit)
    root.after(100, poll)
    root.mainloop()
