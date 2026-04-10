# H:\FLET\qw_image_viewer.py
# V1
#!/usr/bin/env python
# qw_image_viewer.py - Tkinter Image Viewer with Thumbnail Caching
# Target: Windows 11 | Python 3.14.3 | Miniconda 26.1.1 | venv: winnie
# Location: H:\FLET

import os
import hashlib
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import sys

# ---------------------------------------------------------------------------
# Disk Cache Implementation
# ---------------------------------------------------------------------------
class DiskCache:
    """Lightweight disk cache for thumbnails with modification-time validation."""
    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    def _hash_path(self, image_path: str) -> str:
        abs_path = os.path.abspath(image_path)
        return hashlib.sha256(abs_path.encode()).hexdigest()[:16]

    def get(self, image_path: str, size: tuple[int, int]) -> Image.Image | None:
        cache_file = os.path.join(self.cache_dir, f"{self._hash_path(image_path)}_{size[0]}x{size[1]}.png")
        if not os.path.exists(cache_file):
            return None
        # Invalidate if source image is newer than cache
        try:
            if os.path.getmtime(image_path) > os.path.getmtime(cache_file):
                return None
        except OSError:
            return None
        return Image.open(cache_file)

    def save(self, image_path: str, thumb: Image.Image, size: tuple[int, int]) -> None:
        cache_file = os.path.join(self.cache_dir, f"{self._hash_path(image_path)}_{size[0]}x{size[1]}.png")
        thumb.save(cache_file, format="PNG", optimize=True)


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------
class ImageViewerApp:
    ROOT_DIR = r"O:\bilder"
    CACHE_DIR = r"H:\FLET\.qw_thumb_cache"
    THUMB_SIZE = (110, 110)
    SUPPORTED_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp'}

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("QW Image Viewer")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)

        self.cache = DiskCache(self.CACHE_DIR)
        self.current_folder = ""
        self.thumb_refs: list[ImageTk.PhotoImage] = []
        self.large_img_ref: ImageTk.PhotoImage | None = None
        self._load_queue = []
        self._load_index = 0

        if not os.path.isdir(self.ROOT_DIR):
            tk.messagebox.showerror("Path Error", f"Root directory not found:\n{self.ROOT_DIR}")
            self.root.quit()
            return

        self._setup_ui()
        self._init_tree()
        self.status_var.set("Ready")

    # -----------------------------------------------------------------------
    # UI Construction
    # -----------------------------------------------------------------------
    def _setup_ui(self):
        # Status bar
        self.status_var = tk.StringVar(value="Initializing...")
        ttk.Label(self.root, textvariable=self.status_var, anchor=tk.W).pack(fill=tk.X, padx=5, pady=2)

        main_pane = ttk.Frame(self.root)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        main_pane.columnconfigure(1, weight=1)
        main_pane.rowconfigure(1, weight=1)

        # LEFT PANE: Folder Tree
        tree_frame = ttk.Frame(main_pane)
        tree_frame.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 5))
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(tree_frame, show="tree")
        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<<TreeviewOpen>>", self._on_tree_expand)

        # CENTER PANE: Large Image + Path
        center_frame = ttk.Frame(main_pane)
        center_frame.grid(row=0, column=1, sticky="nsew", pady=(0, 5))
        center_frame.columnconfigure(0, weight=1)
        center_frame.rowconfigure(1, weight=1)

        self.path_label = ttk.Label(center_frame, text="", justify=tk.CENTER, wraplength=800)
        self.path_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))

        self.image_label = tk.Label(center_frame, bg="#2b2b2b")
        self.image_label.grid(row=1, column=0, sticky="nsew")

        # BOTTOM PANE: Scrollable Thumbnails
        bottom_frame = ttk.Frame(main_pane)
        bottom_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(5, 0))
        bottom_frame.columnconfigure(0, weight=1)

        self.thumb_canvas = tk.Canvas(bottom_frame, height=140, bg="#1e1e1e")
        hsb = ttk.Scrollbar(bottom_frame, orient=tk.HORIZONTAL, command=self.thumb_canvas.xview)
        self.thumb_canvas.configure(xscrollcommand=hsb.set)
        self.thumb_frame = ttk.Frame(self.thumb_canvas)
        self.thumb_canvas.create_window((0, 0), window=self.thumb_frame, anchor="nw")

        self.thumb_canvas.grid(row=0, column=0, sticky="ew")
        hsb.grid(row=1, column=0, sticky="ew")

        self.thumb_frame.bind("<Configure>", self._on_thumb_frame_resize)

    def _on_thumb_frame_resize(self, event):
        self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all"))

    # -----------------------------------------------------------------------
    # Tree Navigation
    # -----------------------------------------------------------------------
    def _init_tree(self):
        root_node = self.tree.insert("", tk.END, text="bilder", open=True, values=(self.ROOT_DIR,))
        self._populate_node(root_node, self.ROOT_DIR)

    def _populate_node(self, parent: str, path: str) -> None:
        try:
            entries = sorted(os.scandir(path), key=lambda e: e.name.lower())
        except PermissionError:
            return

        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                node = self.tree.insert(parent, tk.END, text=entry.name, open=False, values=(entry.path,))
                # Pre-insert dummy to show expand arrow
                self.tree.insert(node, tk.END, text="placeholder")

    def _on_tree_expand(self, event):
        item = self.tree.focus()
        children = self.tree.get_children(item)
        if len(children) == 1 and self.tree.item(children[0])["text"] == "placeholder":
            self.tree.delete(children)
            path = self.tree.item(item, "values")[0]
            self._populate_node(item, path)

    def _on_tree_select(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        path = self.tree.item(selected[0], "values")[0]
        if os.path.isdir(path):
            self._clear_thumbnails()
            self.current_folder = path
            self.status_var.set(f"Scanning: {path}")
            self.root.update_idletasks()
            self._queue_thumbnails(path)

    # -----------------------------------------------------------------------
    # Thumbnail Loading & Caching
    # -----------------------------------------------------------------------
    def _clear_thumbnails(self):
        for w in self.thumb_frame.winfo_children():
            w.destroy()
        self.thumb_refs.clear()
        self._load_queue.clear()
        self._load_index = 0

    def _queue_thumbnails(self, folder: str):
        try:
            files = [
                f.path for f in os.scandir(folder)
                if f.is_file(follow_symlinks=False) and os.path.splitext(f.name.lower())[1] in self.SUPPORTED_EXT
            ]
        except PermissionError:
            files = []
        files.sort(key=os.path.basename)

        self._load_queue = files
        self._load_index = 0
        self.status_var.set(f"Found {len(files)} images in {os.path.basename(folder)}")
        self._load_next_batch()

    def _load_next_batch(self, batch_size: int = 15):
        if self._load_index >= len(self._load_queue):
            self.status_var.set(f"Loaded {len(self._load_queue)} thumbnails")
            return

        end = min(self._load_index + batch_size, len(self._load_queue))
        for idx in range(self._load_index, end):
            filepath = self._load_queue[idx]
            self._create_thumbnail_button(filepath)

        self._load_index = end
        self.thumb_canvas.update_idletasks()
        self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all"))
        # Schedule next batch to keep UI responsive
        self.root.after(5, lambda: self._load_next_batch(batch_size))

    def _create_thumbnail_button(self, filepath: str):
        # Check cache first
        cached = self.cache.get(filepath, self.THUMB_SIZE)
        if cached:
            img = cached.copy()
        else:
            try:
                with Image.open(filepath) as src:
                    src.load()
                    src.thumbnail(self.THUMB_SIZE, Image.Resampling.LANCZOS)
                    img = src.convert("RGB")
                self.cache.save(filepath, img, self.THUMB_SIZE)
            except Exception as e:
                self.status_var.set(f"Skip: {os.path.basename(filepath)} ({e})")
                return

        tk_img = ImageTk.PhotoImage(img)
        self.thumb_refs.append(tk_img)

        btn = tk.Label(self.thumb_frame, image=tk_img, bg="#333333", cursor="hand2", bd=1, relief="solid")
        btn.pack(side=tk.LEFT, padx=2, pady=2)
        btn.bind("<Button-1>", lambda e, fp=filepath: self._show_large_image(fp))

    # -----------------------------------------------------------------------
    # Large Image Display
    # -----------------------------------------------------------------------
    def _show_large_image(self, filepath: str):
        self.path_label.config(text=filepath)
        try:
            with Image.open(filepath) as src:
                src.load()
                w, h = self.image_label.winfo_width(), self.image_label.winfo_height()
                if w < 20: w = 800
                if h < 20: h = 600
                src.thumbnail((w, h), Image.Resampling.LANCZOS)
                self.large_img_ref = ImageTk.PhotoImage(src.convert("RGB"))
                self.image_label.config(image=self.large_img_ref)
        except Exception as e:
            self.image_label.config(image="", text=f"Error: {e}", fg="red")
            self.large_img_ref = None

# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Ensure Pillow is available
    try:
        import PIL
    except ImportError:
        print("❌ Pillow is required. Install with: pip install Pillow")
        sys.exit(1)

    root = tk.Tk()
    # High DPI scaling for Windows 11
    root.call("tk", "scaling", 1.5)
    app = ImageViewerApp(root)
    root.mainloop()