# H:\FLET\qw_image_viewer.py
# V1
# V2
#!/usr/bin/env python
# qw_image_viewer.py - Tkinter Image Viewer with Thumbnail Caching & Threading
# Target: Windows 11 | Python 3.14.3 | Miniconda 26.1.1 | venv: winnie
# Location: H:\FLET

import os
import sys
import hashlib
import queue
import warnings
import traceback
import faulthandler
import threading
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageOps
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── SAFETY OVERRIDES ───────────────────────────────────────────────────────
faulthandler.enable()
sys.excepthook = lambda *args: traceback.print_exception(*args)
Image.MAX_IMAGE_PIXELS = None
warnings.filterwarnings("ignore", category=Image.DecompressionBombWarning)
# ────────────────────────────────────────────────────────────────────────────


class DiskCache:
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
        except Exception:
            pass


class ImageViewerApp:
    ROOT_DIR = r"O:\bilder"
    CACHE_DIR = r"H:\FLET\.qw_thumb_cache"
    THUMB_SIZE = (110, 110)
    # Excluded *.tif / *.tiff per request
    SUPPORTED_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.ico'}

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("QW Image Viewer")
        self.root.geometry("1280x850")
        self.root.minsize(900, 600)

        self.cache = DiskCache(self.CACHE_DIR)
        self.thumb_refs: list[ImageTk.PhotoImage] = []
        self.large_img_ref: ImageTk.PhotoImage | None = None
        self.current_folder = ""
        
        # Threading & Load Token
        self._load_token = 0
        self._stop_event = threading.Event()
        self._result_queue: queue.Queue = queue.Queue()
        self._load_thread: threading.Thread | None = None
        self._load_count = 0

        if not os.path.isdir(self.ROOT_DIR):
            tk.messagebox.showerror("Path Error", f"Root directory not found:\n{self.ROOT_DIR}")
            self.root.quit()
            return

        self._setup_ui()
        self._init_tree()
        self.status_var.set("Ready. Select a folder to browse images.")

    # ─── UI LAYOUT ────────────────────────────────────────────────────────
    def _setup_ui(self):
        self.status_var = tk.StringVar(value="Initializing...")
        ttk.Label(self.root, textvariable=self.status_var, anchor=tk.W, relief=tk.SUNKEN, borderwidth=1).pack(fill=tk.X, padx=5, pady=2)

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

        # CENTER: Selectable Path + Copy + Image
        center_frame = ttk.Frame(right_frame)
        center_frame.pack(fill=tk.BOTH, expand=True)
        center_frame.rowconfigure(0, weight=0)
        center_frame.rowconfigure(1, weight=1)
        center_frame.columnconfigure(0, weight=1)
        center_frame.columnconfigure(1, weight=0)

        self.path_var = tk.StringVar()
        self.path_entry = tk.Entry(
            center_frame, textvariable=self.path_var, state="readonly",
            bg="#2b2b2b", fg="#00e676", font=("Lucida Console", 10), relief=tk.FLAT, cursor="ibeam", exportselection=True
        )
        self.path_entry.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        # Auto-select text on click/focus
        self.path_entry.bind("<FocusIn>", lambda e: self.path_entry.select_range(0, tk.END))
        self.path_entry.bind("<Button-1>", lambda e: self.path_entry.select_range(0, tk.END))

        copy_btn = ttk.Button(center_frame, text="📋 Copy Path", command=self._copy_path)
        copy_btn.grid(row=0, column=1, padx=(5, 0), pady=(0, 5), sticky="e")

        self.image_label = tk.Label(center_frame, bg="#1e1e1e", relief=tk.SUNKEN)
        self.image_label.grid(row=1, column=0, columnspan=2, sticky="nsew")

        # BOTTOM: Thumbnails
        bottom_frame = ttk.Frame(right_frame)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(5, 0))

        self.thumb_canvas = tk.Canvas(bottom_frame, height=140, bg="#2b2b2b", highlightthickness=0)
        hsb = ttk.Scrollbar(bottom_frame, orient=tk.HORIZONTAL, command=self.thumb_canvas.xview)
        self.thumb_canvas.configure(xscrollcommand=hsb.set)
        hsb.pack(fill=tk.X, side=tk.BOTTOM)
        self.thumb_canvas.pack(fill=tk.X, side=tk.TOP, padx=2, pady=2)

        self.thumb_frame = ttk.Frame(self.thumb_canvas)
        self.thumb_canvas.create_window((0, 0), window=self.thumb_frame, anchor="nw")
        self.thumb_frame.bind("<Configure>", lambda e: self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all")))

    def _copy_path(self):
        path = self.path_var.get()
        if path:
            self.root.clipboard_clear()
            self.root.clipboard_append(path)
            self.root.update()
            self.status_var.set("✅ Path copied to clipboard!")
            self.root.after(1500, lambda: self.status_var.set("Ready"))

    # ─── TREE NAVIGATION ──────────────────────────────────────────────────
    def _init_tree(self):
        root_node = self.tree.insert("", tk.END, text="bilder", open=True, values=(self.ROOT_DIR,))
        self._populate_node(root_node, self.ROOT_DIR)

    def _populate_node(self, parent: str, path: str) -> None:
        try:
            entries = sorted(os.scandir(path), key=lambda e: e.name.lower())
        except (PermissionError, OSError) as e:
            print(f"[Tree Scan Warning] {e}")
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
        try:
            selected = self.tree.selection()
            if not selected: return
            item_data = self.tree.item(selected[0])
            path = item_data.get("values", [None])[0]
            if not path or not os.path.isdir(path):
                return
            self.current_folder = path
            self._cancel_loading()
            self.status_var.set(f"Scanning: {path}...")
            self.root.update_idletasks()
            self._start_thumbnail_load(path)
        except Exception as e:
            print(f"[Tree Select Error] {e}")
            traceback.print_exc()

    # ─── THUMBNAIL LOADING (Threaded & Tokenized) ─────────────────────────
    def _cancel_loading(self):
        self._stop_event.set()
        if self._load_thread and self._load_thread.is_alive():
            self._load_thread.join(timeout=0.5)
        self._load_token += 1  # Invalidate stale results
        self._result_queue = queue.Queue()
        self._stop_event.clear()
        self._clear_thumbnails()

    def _clear_thumbnails(self):
        for w in self.thumb_frame.winfo_children():
            w.destroy()
        self.thumb_refs.clear()
        self._load_count = 0
        self.thumb_canvas.configure(scrollregion=(0, 0, 0, 0))

    def _start_thumbnail_load(self, folder: str):
        try:
            files = [
                f.path for f in os.scandir(folder)
                if f.is_file(follow_symlinks=False) and os.path.splitext(f.name.lower())[1] in self.SUPPORTED_EXT
            ]
        except Exception as e:
            print(f"[SCANDIR FAILED] {e}")
            self.status_var.set("❌ Cannot read directory. Check permissions.")
            return

        if not files:
            self.status_var.set("No supported images found.")
            return

        self._load_thread = threading.Thread(target=self._background_load, args=(files, self._load_token), daemon=True)
        self._load_thread.start()
        self.root.after(10, self._poll_queue)

    def _background_load(self, file_list: list[str], token: int):
        processed = 0
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Submit all, process as they complete
            future_map = {executor.submit(self._process_single_thumb, fp): fp for fp in file_list}
            for future in as_completed(future_map):
                if self._stop_event.is_set() or self._load_token != token:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                try:
                    result = future.result()
                    if result:
                        self._result_queue.put(result)
                        processed += 1
                        if processed % 20 == 0:
                            self.status_var.set(f"Processing {processed}/{len(file_list)} thumbnails...")
                except Exception as e:
                    print(f"[Worker Error] {e}")
        self._result_queue.put(("DONE", None))

    def _process_single_thumb(self, filepath: str) -> tuple[str, Image.Image] | None:
        try:
            cached = self.cache.get(filepath, self.THUMB_SIZE)
            if cached:
                return filepath, cached

            with Image.open(filepath) as src:
                src.load()
                try:
                    src = ImageOps.exif_transpose(src)
                except Exception:
                    pass
                src.thumbnail(self.THUMB_SIZE, Image.Resampling.LANCZOS)
                img = src.copy()
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGB")
                self.cache.save(filepath, img, self.THUMB_SIZE)
                return filepath, img
        except Exception:
            return None

    def _poll_queue(self):
        # Ignore if token changed (folder switched)
        current_token = self._load_token
        
        batch = []
        try:
            while not self._result_queue.empty():
                item = self._result_queue.get_nowait()
                if item == ("DONE", None):
                    self.status_var.set(f"✅ Ready: {self._load_count} thumbnails loaded.")
                    return
                batch.append(item)
        except queue.Empty:
            pass

        if batch and self._load_token == current_token:
            for fp, img in batch:
                self._add_thumb_to_ui(fp, img)
            self._load_count += len(batch)
            self.status_var.set(f"Loading... {len(batch)}/{self._load_count}")
            bbox = self.thumb_canvas.bbox("all")
            if bbox:
                self.thumb_canvas.configure(scrollregion=bbox)

        self.root.after(5, self._poll_queue)

    def _add_thumb_to_ui(self, filepath: str, img: Image.Image):
        tk_img = ImageTk.PhotoImage(img)
        self.thumb_refs.append(tk_img)
        btn = tk.Label(self.thumb_frame, image=tk_img, bg="#333333", cursor="hand2", bd=0)
        btn.pack(side=tk.LEFT, padx=2, pady=2)
        btn.bind("<Button-1>", lambda e, fp=filepath: self._show_large_image(fp))

    # ─── LARGE IMAGE DISPLAY ──────────────────────────────────────────────
    def _show_large_image(self, filepath: str):
        self.path_var.set(filepath)
        self.image_label.config(image="", text="Loading...", fg="#ffcc00")
        self.root.update_idletasks()

        self.large_img_ref = None

        try:
            with Image.open(filepath) as src:
                src.load()
                try:
                    src = ImageOps.exif_transpose(src)
                except Exception:
                    pass

                w = max(self.image_label.winfo_width(), 200)
                h = max(self.image_label.winfo_height(), 200)
                w, h = min(w, 4000), min(h, 3000)

                src.thumbnail((w, h), Image.Resampling.LANCZOS)
                if src.mode not in ("RGB", "RGBA", "L"):
                    src = src.convert("RGB")

                if src.width == 0 or src.height == 0:
                    raise ValueError("Zero dimensions after resize")

                self.large_img_ref = ImageTk.PhotoImage(src)
                self.image_label.config(image=self.large_img_ref, text="")
                self.status_var.set(f"🖼️ {os.path.basename(filepath)}")
        except Exception as e:
            print(f"[Image Load Error] {e}")
            self.image_label.config(image="", text=f"❌ {type(e).__name__}: {e}", fg="#ff6b6b")
            self.status_var.set("Error loading image")

    def _cleanup(self):
        self._stop_event.set()
        if self._load_thread and self._load_thread.is_alive():
            self._load_thread.join(timeout=1.0)
        self.root.destroy()


# ─── ENTRY POINT ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        from PIL import Image
    except ImportError:
        print("❌ Pillow is required. Run: pip install Pillow")
        sys.exit(1)

    root = tk.Tk()
    try:
        root.call("tk", "scaling", 1.5)
    except tk.TclError:
        pass

    app = ImageViewerApp(root)
    root.protocol("WM_DELETE_WINDOW", app._cleanup)
    root.mainloop()