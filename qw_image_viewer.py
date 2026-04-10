# H:\FLET\qw_image_viewer.py
# V1
#!/usr/bin/env python
# qw_image_viewer.py - Tkinter Image Viewer with Thumbnail Caching
# Target: Windows 11 | Python 3.14.3 | Miniconda 26.1.1 | venv: winnie
# Location: H:\FLET

import os
import sys
import hashlib
import warnings
import traceback
import faulthandler
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageOps

# ─── SAFETY OVERRIDES ───────────────────────────────────────────────────────
faulthandler.enable()  # Catch C-level segfaults
Image.MAX_IMAGE_PIXELS = None  # Allow high-res images
warnings.filterwarnings("ignore", category=Image.DecompressionBombWarning)
# ────────────────────────────────────────────────────────────────────────────


class DiskCache:
    """Disk cache for thumbnails with mtime-based invalidation."""
    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _hash_path(self, path: str) -> str:
        return hashlib.sha256(os.path.abspath(path).encode()).hexdigest()[:16]

    def get(self, path: str, size: tuple[int, int]) -> Image.Image | None:
        cache_file = os.path.join(self.cache_dir, f"{self._hash_path(path)}_{size[0]}x{size[1]}.png")
        if not os.path.exists(cache_file):
            return None
        try:
            if os.path.getmtime(path) > os.path.getmtime(cache_file):
                os.remove(cache_file)
                return None
        except OSError:
            return None
        try:
            return Image.open(cache_file).copy()
        except Exception:
            return None

    def save(self, path: str, img: Image.Image, size: tuple[int, int]) -> None:
        cache_file = os.path.join(self.cache_dir, f"{self._hash_path(path)}_{size[0]}x{size[1]}.png")
        try:
            img.save(cache_file, format="PNG", optimize=True)
        except Exception as e:
            print(f"[Cache] Save failed: {e}")


class ImageViewerApp:
    ROOT_DIR = r"O:\bilder"
    CACHE_DIR = r"H:\FLET\.qw_thumb_cache"
    THUMB_SIZE = (110, 110)
    SUPPORTED_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.ico'}

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("QW Image Viewer")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)

        self.cache = DiskCache(self.CACHE_DIR)
        self.current_folder = ""
        self.thumb_refs: list[ImageTk.PhotoImage] = []
        self.large_img_ref: ImageTk.PhotoImage | None = None
        self._load_queue: list[str] = []
        self._load_index = 0
        self._after_id = None

        if not os.path.isdir(self.ROOT_DIR):
            tk.messagebox.showerror("Path Error", f"Root directory not found:\n{self.ROOT_DIR}")
            self.root.quit()
            return

        self._setup_ui()
        self._init_tree()
        self.status_var.set("Ready. Select a folder to browse images.")

    # ─── UI LAYOUT ────────────────────────────────────────────────────────
    def _setup_ui(self):
        # Status Bar
        self.status_var = tk.StringVar(value="Initializing...")
        ttk.Label(self.root, textvariable=self.status_var, anchor=tk.W, relief=tk.SUNKEN, borderwidth=1).pack(fill=tk.X, padx=5, pady=2)

        # Main Paned Window (Left/Right resizable)
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        left_pane = ttk.Frame(main_pane)
        main_pane.add(left_pane, weight=1)

        right_frame = ttk.Frame(main_pane)
        main_pane.add(right_frame, weight=4)

        # LEFT: Folder Tree
        tree_frame = ttk.Frame(left_pane)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(tree_frame, show="tree")
        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<<TreeviewOpen>>", self._on_tree_expand)

        # CENTER: Large Image + Path
        center_frame = ttk.Frame(right_frame)
        center_frame.pack(fill=tk.BOTH, expand=True)
        center_frame.rowconfigure(0, weight=0)
        center_frame.rowconfigure(1, weight=1)
        center_frame.columnconfigure(0, weight=1)

        self.path_label = ttk.Label(center_frame, text="", justify=tk.CENTER, wraplength=700, anchor=tk.CENTER)
        self.path_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))

        self.image_label = tk.Label(center_frame, bg="#1e1e1e", relief=tk.SUNKEN)
        self.image_label.grid(row=1, column=0, sticky="nsew")

        # BOTTOM: Scrollable Thumbnails
        bottom_frame = ttk.Frame(right_frame)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(5, 0))

        self.thumb_canvas = tk.Canvas(bottom_frame, height=140, bg="#2b2b2b", highlightthickness=0)
        hsb = ttk.Scrollbar(bottom_frame, orient=tk.HORIZONTAL, command=self.thumb_canvas.xview)
        self.thumb_canvas.configure(xscrollcommand=hsb.set)
        hsb.pack(fill=tk.X, side=tk.BOTTOM)
        self.thumb_canvas.pack(fill=tk.X, side=tk.TOP, padx=2, pady=2)

        self.thumb_frame = ttk.Frame(self.thumb_canvas)
        self.thumb_canvas.create_window((0, 0), window=self.thumb_frame, anchor="nw")
        self.thumb_frame.bind("<Configure>", self._on_thumb_frame_resize)

    def _on_thumb_frame_resize(self, event):
        bbox = self.thumb_canvas.bbox("all")
        if bbox:
            self.thumb_canvas.configure(scrollregion=bbox)

    # ─── TREE NAVIGATION ──────────────────────────────────────────────────
    def _init_tree(self):
        root_node = self.tree.insert("", tk.END, text="bilder", open=True, values=(self.ROOT_DIR,))
        self._populate_node(root_node, self.ROOT_DIR)

    def _populate_node(self, parent: str, path: str) -> None:
        try:
            entries = sorted(os.scandir(path), key=lambda e: e.name.lower())
        except (PermissionError, OSError):
            return
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                node = self.tree.insert(parent, tk.END, text=entry.name, open=False, values=(entry.path,))
                self.tree.insert(node, tk.END, text="placeholder")

    def _on_tree_expand(self, event):
        item = self.tree.focus()
        if not item: return
        children = self.tree.get_children(item)
        if len(children) == 1 and self.tree.item(children[0])["text"] == "placeholder":
            self.tree.delete(children)
            path = self.tree.item(item, "values")[0]
            self._populate_node(item, path)

    def _on_tree_select(self, event):
        selected = self.tree.selection()
        if not selected: return
        path = self.tree.item(selected[0], "values")[0]
        if os.path.isdir(path):
            self._clear_thumbnails()
            self.current_folder = path
            self.status_var.set(f"Scanning: {path}")
            self.root.update_idletasks()
            self._queue_thumbnails(path)

    # ─── THUMBNAIL QUEUE ──────────────────────────────────────────────────
    def _clear_thumbnails(self):
        self._cancel_load()
        for w in self.thumb_frame.winfo_children():
            w.destroy()
        self.thumb_refs.clear()
        self._load_queue.clear()
        self._load_index = 0

    def _cancel_load(self):
        if self._after_id:
            self.root.after_cancel(self._after_id)
            self._after_id = None

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
        self.status_var.set(f"Found {len(files)} images. Loading thumbnails...")
        # Small delay to let UI settle
        self._after_id = self.root.after(50, lambda: self._load_next_batch())

    def _load_next_batch(self, batch_size: int = 15):
        if self._load_index >= len(self._load_queue):
            self.status_var.set(f"Ready: {len(self._load_queue)} thumbnails loaded.")
            self._after_id = None
            return

        end = min(self._load_index + batch_size, len(self._load_queue))
        for idx in range(self._load_index, end):
            self._create_thumbnail_button(self._load_queue[idx])

        self._load_index = end
        bbox = self.thumb_canvas.bbox("all")
        if bbox:
            self.thumb_canvas.configure(scrollregion=bbox)
        
        self._after_id = self.root.after(5, lambda: self._load_next_batch(batch_size))

    def _create_thumbnail_button(self, filepath: str):
        try:
            cached = self.cache.get(filepath, self.THUMB_SIZE)
            if cached:
                img = cached
            else:
                with Image.open(filepath) as src:
                    src.load()
                    try:
                        src = ImageOps.exif_transpose(src)
                    except Exception:
                        pass
                    src.thumbnail(self.THUMB_SIZE, Image.Resampling.LANCZOS)
                    img = src.copy()
                self.cache.save(filepath, img, self.THUMB_SIZE)

            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")

            if img.width == 0 or img.height == 0:
                return

            tk_img = ImageTk.PhotoImage(img)
            self.thumb_refs.append(tk_img)

            btn = tk.Label(self.thumb_frame, image=tk_img, bg="#333333", cursor="hand2", bd=0)
            btn.pack(side=tk.LEFT, padx=2, pady=2)
            btn.bind("<Button-1>", lambda e, fp=filepath: self._show_large_image(fp))
        except Exception:
            pass  # Silently skip corrupted files

    # ─── LARGE IMAGE DISPLAY ──────────────────────────────────────────────
    def _show_large_image(self, filepath: str):
        self.path_label.config(text=filepath)
        self.image_label.config(image="", text="Loading...")
        self.root.update_idletasks()

        # Free previous large image memory
        self.large_img_ref = None

        try:
            with Image.open(filepath) as src:
                src.load()
                try:
                    src = ImageOps.exif_transpose(src)
                except Exception:
                    pass

                # Safe display dimensions (prevents Tk GDI overflow)
                max_w, max_h = 3000, 2000
                w = self.image_label.winfo_width()
                h = self.image_label.winfo_height()
                w = max(w, 200)
                h = max(h, 200)
                w, h = min(w, max_w), min(h, max_h)

                src.thumbnail((w, h), Image.Resampling.LANCZOS)

                if src.mode not in ("RGB", "RGBA", "L"):
                    src = src.convert("RGB")

                if src.width == 0 or src.height == 0:
                    raise ValueError("Zero dimensions after resize")

                self.large_img_ref = ImageTk.PhotoImage(src)
                self.image_label.config(image=self.large_img_ref, text="")
                self.status_var.set(f"Displaying: {os.path.basename(filepath)}")
        except Exception as e:
            traceback.print_exc()
            self.image_label.config(image="", text=f"❌ {type(e).__name__}: {e}", fg="#ff6b6b")
            self.large_img_ref = None
            self.status_var.set("Error loading image")


# ─── ENTRY POINT ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        from PIL import Image
    except ImportError:
        print("❌ Pillow is required. Run: pip install Pillow")
        sys.exit(1)

    root = tk.Tk()
    try:
        root.call("tk", "scaling", 1.5)  # HiDPI for Windows 11
    except tk.TclError:
        pass

    app = ImageViewerApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app._cancel_load(), root.destroy()))
    root.mainloop()