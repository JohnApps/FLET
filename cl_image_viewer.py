# cl_image_viewer.py
# Claude code using pyqt6
# V1
# V2
# V3
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cl_image_viewer.py - Tkinter Image Viewer with Thumbnail Caching

A desktop image viewer featuring:
- Left pane: Folder tree navigation rooted at O:\\bilder
- Center pane: Large image display with path info
- Bottom strip: Scrollable thumbnail gallery
- DiskCache: Reduces I/O by caching thumbnails

Target: Windows 11, Python 3.14.3, Miniconda 26.1.1, venv 'winnie'
Location: H:\\FLET

Usage:
    conda activate winnie
    pip install Pillow diskcache
    python cl_image_viewer.py
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Optional
from io import BytesIO
import logging

from PIL import Image, ImageTk
import diskcache

# Setup logging to file and console
LOG_FILE = Path.home() / "cl_image_viewer.log"
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Reduce PIL debug spam
logging.getLogger('PIL').setLevel(logging.WARNING)

logger.info(f"Starting Image Viewer - Log file: {LOG_FILE}")

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
ROOT_PATH = r"O:\bilder"
CACHE_DIR = Path.home() / ".cache" / "cl_image_viewer"
THUMBNAIL_SIZE = (100, 100)
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif'}

# Dark theme colors
COLORS = {
    'bg_dark': '#1e1e1e',
    'bg_medium': '#252525',
    'bg_light': '#2d2d2d',
    'bg_hover': '#3a3a3a',
    'fg': '#dcdcdc',
    'fg_dim': '#888888',
    'accent': '#0078d4',
    'accent_dark': '#1a3a5c',
    'border': '#3a3a3a',
    'status_bg': '#007acc',
}


# -----------------------------------------------------------------------------
# Thumbnail Cache Manager
# -----------------------------------------------------------------------------
class ThumbnailCache:
    """Manages thumbnail caching using diskcache to reduce disk I/O."""
    
    def __init__(self, cache_dir: Path, size: tuple = THUMBNAIL_SIZE):
        self.cache = diskcache.Cache(str(cache_dir), size_limit=500 * 1024 * 1024)
        self.size = size
    
    def get_cache_key(self, image_path: str) -> str:
        """Generate cache key from path and modification time."""
        try:
            mtime = os.path.getmtime(image_path)
            return f"{image_path}:{mtime}:{self.size[0]}x{self.size[1]}"
        except OSError:
            return f"{image_path}:0:{self.size[0]}x{self.size[1]}"
    
    def get_thumbnail(self, image_path: str) -> Optional[bytes]:
        """Retrieve cached thumbnail or generate and cache it."""
        key = self.get_cache_key(image_path)
        
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        
        try:
            with Image.open(image_path) as img:
                # Handle orientation from EXIF
                try:
                    from PIL import ImageOps
                    img = ImageOps.exif_transpose(img)
                except Exception:
                    pass
                
                img.thumbnail(self.size, Image.Resampling.LANCZOS)
                
                if img.mode not in ('RGB', 'L'):
                    img = img.convert('RGB')
                
                buffer = BytesIO()
                img.save(buffer, format='JPEG', quality=85)
                thumb_bytes = buffer.getvalue()
                
                self.cache.set(key, thumb_bytes)
                return thumb_bytes
                
        except Exception as e:
            print(f"Error creating thumbnail for {image_path}: {e}")
            return None
    
    def close(self):
        """Close the cache."""
        self.cache.close()


# -----------------------------------------------------------------------------
# Folder Tree Widget
# -----------------------------------------------------------------------------
class FolderTree(ttk.Frame):
    """Treeview showing folder hierarchy."""
    
    def __init__(self, parent, root_path: str, on_select_callback):
        super().__init__(parent)
        self.root_path = root_path
        self.on_select = on_select_callback
        self._setup_ui()
        self._populate_root()
    
    def _setup_ui(self):
        """Build the treeview with scrollbar."""
        # Scrollbar
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Treeview
        self.tree = ttk.Treeview(
            self, 
            selectmode='browse',
            yscrollcommand=scrollbar.set,
            show='tree'
        )
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.tree.yview)
        
        # Events
        self.tree.bind('<<TreeviewSelect>>', self._on_select)
        self.tree.bind('<<TreeviewOpen>>', self._on_expand)
    
    def _populate_root(self):
        """Add root folder to tree."""
        if os.path.exists(self.root_path):
            root_name = os.path.basename(self.root_path) or self.root_path
            node = self.tree.insert('', 'end', text=f"📁 {root_name}", 
                                    values=(self.root_path,), open=False)
            self._add_placeholder(node)
    
    def _add_placeholder(self, parent):
        """Add dummy child so folder shows as expandable."""
        self.tree.insert(parent, 'end', text='__placeholder__')
    
    def _on_expand(self, event):
        """Load children when folder is expanded."""
        node = self.tree.focus()
        children = self.tree.get_children(node)
        
        # Remove placeholder and load real children
        if len(children) == 1:
            first_child = self.tree.item(children[0])
            if first_child['text'] == '__placeholder__':
                self.tree.delete(children[0])
                self._load_children(node)
    
    def _load_children(self, parent_node):
        """Load subdirectories into tree node."""
        parent_path = self.tree.item(parent_node)['values'][0]
        
        try:
            entries = sorted(os.scandir(parent_path), key=lambda e: e.name.lower())
            for entry in entries:
                if entry.is_dir() and not entry.name.startswith('.'):
                    node = self.tree.insert(
                        parent_node, 'end',
                        text=f"📁 {entry.name}",
                        values=(entry.path,)
                    )
                    # Check if has subdirectories
                    try:
                        has_subdirs = any(
                            e.is_dir() for e in os.scandir(entry.path) 
                            if not e.name.startswith('.')
                        )
                        if has_subdirs:
                            self._add_placeholder(node)
                    except PermissionError:
                        pass
        except PermissionError:
            pass
    
    def _on_select(self, event):
        """Handle folder selection."""
        selection = self.tree.selection()
        if selection:
            item = self.tree.item(selection[0])
            if item['values']:
                folder_path = item['values'][0]
                if os.path.isdir(folder_path):
                    self.on_select(folder_path)


# -----------------------------------------------------------------------------
# Thumbnail Strip Widget
# -----------------------------------------------------------------------------
class ThumbnailStrip(ttk.Frame):
    """Horizontal scrollable strip of thumbnail images."""
    
    def __init__(self, parent, on_select_callback):
        super().__init__(parent)
        self.on_select = on_select_callback
        self.thumbnails: dict[str, dict] = {}  # path -> {label, photo, frame}
        self.current_selection: Optional[str] = None
        self._setup_ui()
    
    def _setup_ui(self):
        """Build scrollable thumbnail area."""
        # Canvas for scrolling
        self.canvas = tk.Canvas(
            self, 
            height=THUMBNAIL_SIZE[1] + 30,
            bg=COLORS['bg_dark'],
            highlightthickness=0
        )
        
        # Scrollbar
        self.scrollbar = ttk.Scrollbar(
            self, orient=tk.HORIZONTAL, 
            command=self.canvas.xview
        )
        
        # Inner frame for thumbnails
        self.inner_frame = tk.Frame(self.canvas, bg=COLORS['bg_dark'])
        
        # Layout
        self.scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # Create window in canvas
        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.inner_frame, anchor='nw'
        )
        
        # Configure scrolling
        self.canvas.configure(xscrollcommand=self.scrollbar.set)
        self.inner_frame.bind('<Configure>', self._on_frame_configure)
        self.canvas.bind('<Configure>', self._on_canvas_configure)
        
        # Mouse wheel scrolling
        self.canvas.bind('<MouseWheel>', self._on_mousewheel)
        self.inner_frame.bind('<MouseWheel>', self._on_mousewheel)
    
    def _on_frame_configure(self, event):
        """Update scroll region when content changes."""
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
    
    def _on_canvas_configure(self, event):
        """Adjust inner frame height to match canvas."""
        self.canvas.itemconfig(self.canvas_window, height=event.height)
    
    def _on_mousewheel(self, event):
        """Scroll horizontally with mouse wheel."""
        self.canvas.xview_scroll(int(-1 * (event.delta / 120)), 'units')
    
    def clear(self):
        """Remove all thumbnails."""
        for widget in self.inner_frame.winfo_children():
            widget.destroy()
        self.thumbnails.clear()
        self.current_selection = None
    
    def add_placeholder(self, image_path: str):
        """Add placeholder for a thumbnail."""
        frame = tk.Frame(
            self.inner_frame,
            bg=COLORS['bg_light'],
            padx=3, pady=3
        )
        frame.pack(side=tk.LEFT, padx=4, pady=5)
        
        label = tk.Label(
            frame,
            text="⏳",
            width=THUMBNAIL_SIZE[0] // 8,
            height=THUMBNAIL_SIZE[1] // 16,
            bg=COLORS['bg_light'],
            fg=COLORS['fg_dim'],
            font=('Segoe UI Emoji', 20)
        )
        label.pack()
        
        # Bind click
        frame.bind('<Button-1>', lambda e, p=image_path: self._on_click(p))
        label.bind('<Button-1>', lambda e, p=image_path: self._on_click(p))
        
        # Hover effects
        frame.bind('<Enter>', lambda e, f=frame: self._on_hover(f, True))
        frame.bind('<Leave>', lambda e, f=frame: self._on_hover(f, False))
        
        self.thumbnails[image_path] = {
            'frame': frame,
            'label': label,
            'photo': None
        }
    
    def update_thumbnail(self, image_path: str, photo: ImageTk.PhotoImage):
        """Update placeholder with actual thumbnail."""
        if image_path in self.thumbnails:
            data = self.thumbnails[image_path]
            data['photo'] = photo  # Keep reference!
            data['label'].configure(
                image=photo, 
                text='',
                width=THUMBNAIL_SIZE[0],
                height=THUMBNAIL_SIZE[1]
            )
    
    def _on_click(self, image_path: str):
        """Handle thumbnail click."""
        self.select(image_path)
        self.on_select(image_path)
    
    def _on_hover(self, frame: tk.Frame, entering: bool):
        """Handle hover effect."""
        if entering:
            frame.configure(bg=COLORS['bg_hover'])
            for child in frame.winfo_children():
                child.configure(bg=COLORS['bg_hover'])
        else:
            # Check if selected
            is_selected = False
            for path, data in self.thumbnails.items():
                if data['frame'] == frame and path == self.current_selection:
                    is_selected = True
                    break
            
            bg = COLORS['accent_dark'] if is_selected else COLORS['bg_light']
            frame.configure(bg=bg)
            for child in frame.winfo_children():
                child.configure(bg=bg)
    
    def select(self, image_path: str):
        """Highlight selected thumbnail."""
        # Deselect previous
        if self.current_selection and self.current_selection in self.thumbnails:
            data = self.thumbnails[self.current_selection]
            data['frame'].configure(bg=COLORS['bg_light'])
            data['label'].configure(bg=COLORS['bg_light'])
        
        # Select new
        if image_path in self.thumbnails:
            self.current_selection = image_path
            data = self.thumbnails[image_path]
            data['frame'].configure(bg=COLORS['accent_dark'])
            data['label'].configure(bg=COLORS['accent_dark'])
            
            # Scroll into view (with safety checks)
            try:
                self.canvas.update_idletasks()
                frame = data['frame']
                x = frame.winfo_x()
                width = self.canvas.winfo_width()
                scroll_x = self.canvas.canvasx(0)
                inner_width = self.inner_frame.winfo_width()
                
                if inner_width > 0 and width > 0:
                    if x < scroll_x:
                        self.canvas.xview_moveto(x / inner_width)
                    elif x + frame.winfo_width() > scroll_x + width:
                        target = (x - width + frame.winfo_width() + 20) / inner_width
                        self.canvas.xview_moveto(max(0, min(1, target)))
            except Exception:
                pass  # Ignore scroll errors


# -----------------------------------------------------------------------------
# Main Image Display
# -----------------------------------------------------------------------------
class ImageDisplay(tk.Frame):
    """Main image display area with path info."""
    
    def __init__(self, parent):
        super().__init__(parent, bg=COLORS['bg_dark'])
        self.current_photo: Optional[ImageTk.PhotoImage] = None
        self.current_path: Optional[str] = None
        self._setup_ui()
    
    def _setup_ui(self):
        """Build display area."""
        # Path info bar
        self.path_label = tk.Label(
            self,
            text="Path: (none)",
            bg=COLORS['bg_medium'],
            fg=COLORS['fg'],
            font=('Consolas', 10),
            anchor='w',
            padx=10, pady=6
        )
        self.path_label.pack(side=tk.TOP, fill=tk.X)
        
        # Image canvas
        self.canvas = tk.Canvas(
            self,
            bg=COLORS['bg_dark'],
            highlightthickness=0
        )
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # Placeholder text
        self.placeholder_id = self.canvas.create_text(
            0, 0,
            text="📷 Select a folder to browse images",
            fill=COLORS['fg_dim'],
            font=('Segoe UI', 14)
        )
        
        # Resize handling
        self.canvas.bind('<Configure>', self._on_resize)
        self._image_id = None
        self._original_image: Optional[Image.Image] = None
    
    def _on_resize(self, event):
        """Reposition/rescale on resize."""
        # Center placeholder
        self.canvas.coords(
            self.placeholder_id,
            event.width // 2,
            event.height // 2
        )
        
        # Rescale image if loaded
        if self._original_image:
            self._display_scaled(event.width, event.height)
    
    def _display_scaled(self, canvas_width: int, canvas_height: int):
        """Scale and display current image to fit canvas."""
        if not self._original_image:
            return
        
        img = self._original_image
        
        # Calculate scale to fit
        scale = min(
            canvas_width / img.width,
            canvas_height / img.height
        )
        
        if scale < 1:
            new_size = (int(img.width * scale), int(img.height * scale))
            scaled = img.resize(new_size, Image.Resampling.LANCZOS)
        else:
            scaled = img
        
        self.current_photo = ImageTk.PhotoImage(scaled)
        
        if self._image_id:
            self.canvas.delete(self._image_id)
        
        self._image_id = self.canvas.create_image(
            canvas_width // 2,
            canvas_height // 2,
            image=self.current_photo,
            anchor='center'
        )
        
        # Hide placeholder
        self.canvas.itemconfigure(self.placeholder_id, state='hidden')
    
    def load_image(self, image_path: str) -> bool:
        """Load and display an image."""
        logger.debug(f"load_image called: {image_path}")
        self.current_path = image_path
        
        # Update path label
        folder = os.path.dirname(image_path)
        filename = os.path.basename(image_path)
        self.path_label.configure(text=f"Path: {folder}  |  File: {filename}")
        
        try:
            logger.debug("Opening image with PIL")
            img = Image.open(image_path)
            img.load()  # Force load the image data
            logger.debug(f"Image opened: {img.size}, mode={img.mode}")
            
            # Handle EXIF orientation
            try:
                from PIL import ImageOps
                img = ImageOps.exif_transpose(img)
            except Exception as e:
                logger.debug(f"EXIF transpose failed (ok): {e}")
            
            # Convert for display
            if img.mode not in ('RGB', 'RGBA'):
                logger.debug(f"Converting from {img.mode} to RGB")
                img = img.convert('RGB')
            
            self._original_image = img.copy()  # Keep a copy
            logger.debug("Image copied to _original_image")
            
            # Display
            canvas_w = self.canvas.winfo_width()
            canvas_h = self.canvas.winfo_height()
            logger.debug(f"Canvas size: {canvas_w}x{canvas_h}")
            if canvas_w > 1 and canvas_h > 1:
                self._display_scaled(canvas_w, canvas_h)
                logger.debug("Image displayed")
            else:
                logger.warning("Canvas too small, skipping display")
            return True
            
        except Exception as e:
            logger.exception(f"Error loading image {image_path}: {e}")
            self.canvas.itemconfigure(self.placeholder_id, state='normal')
            self.canvas.itemconfigure(
                self.placeholder_id,
                text=f"❌ Failed to load: {e}"
            )
            return False
    
    def show_placeholder(self, text: str = "📷 Select a folder to browse images"):
        """Show placeholder text."""
        self._original_image = None
        if self._image_id:
            self.canvas.delete(self._image_id)
            self._image_id = None
        self.canvas.itemconfigure(self.placeholder_id, state='normal', text=text)


# -----------------------------------------------------------------------------
# Status Bar
# -----------------------------------------------------------------------------
class StatusBar(tk.Frame):
    """Bottom status bar."""
    
    def __init__(self, parent):
        super().__init__(parent, bg=COLORS['status_bg'])
        self.label = tk.Label(
            self,
            text="Ready",
            bg=COLORS['status_bg'],
            fg='white',
            font=('Segoe UI', 9),
            anchor='w',
            padx=10
        )
        self.label.pack(fill=tk.X)
    
    def set_message(self, text: str):
        """Update status message."""
        self.label.configure(text=text)


# -----------------------------------------------------------------------------
# Main Application
# -----------------------------------------------------------------------------
class ImageViewerApp:
    """Main application controller."""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("🖼️ Image Viewer - O:\\bilder")
        self.root.geometry("1400x900")
        self.root.configure(bg=COLORS['bg_dark'])
        
        # Initialize cache
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.cache = ThumbnailCache(CACHE_DIR)
        
        # Thumbnail loading state (main thread only - no threading!)
        self._thumbnail_queue: list[str] = []
        self._current_folder: Optional[str] = None
        self._photo_refs: list[ImageTk.PhotoImage] = []  # MUST keep references!
        
        # Image list
        self.image_list: list[str] = []
        self.current_index: int = -1
        
        # Setup UI
        self._setup_styles()
        self._setup_ui()
        self._setup_bindings()
        
        # Cleanup on close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        logger.info("ImageViewerApp initialized")
    
    def _setup_styles(self):
        """Configure ttk styles for dark theme."""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Treeview
        style.configure(
            'Treeview',
            background=COLORS['bg_medium'],
            foreground=COLORS['fg'],
            fieldbackground=COLORS['bg_medium'],
            borderwidth=0
        )
        style.configure(
            'Treeview.Heading',
            background=COLORS['bg_light'],
            foreground=COLORS['fg']
        )
        style.map(
            'Treeview',
            background=[('selected', COLORS['accent'])],
            foreground=[('selected', 'white')]
        )
        
        # Scrollbars
        style.configure(
            'TScrollbar',
            background=COLORS['bg_light'],
            troughcolor=COLORS['bg_dark'],
            borderwidth=0
        )
        
        # Frames
        style.configure(
            'TFrame',
            background=COLORS['bg_dark']
        )
    
    def _setup_ui(self):
        """Build the main UI layout."""
        # Main paned window (horizontal split)
        self.paned = tk.PanedWindow(
            self.root,
            orient=tk.HORIZONTAL,
            bg=COLORS['border'],
            sashwidth=4,
            sashrelief=tk.FLAT
        )
        self.paned.pack(fill=tk.BOTH, expand=True)
        
        # Left pane: Folder tree
        left_frame = tk.Frame(self.paned, bg=COLORS['bg_medium'])
        self.folder_tree = FolderTree(
            left_frame, 
            ROOT_PATH, 
            self._on_folder_select
        )
        self.folder_tree.pack(fill=tk.BOTH, expand=True)
        self.paned.add(left_frame, width=280, minsize=200)
        
        # Right pane: Image + thumbnails
        right_frame = tk.Frame(self.paned, bg=COLORS['bg_dark'])
        
        # Image display
        self.image_display = ImageDisplay(right_frame)
        self.image_display.pack(fill=tk.BOTH, expand=True)
        
        # Thumbnail strip
        self.thumbnail_strip = ThumbnailStrip(right_frame, self._on_thumbnail_select)
        self.thumbnail_strip.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.paned.add(right_frame, minsize=400)
        
        # Status bar
        self.status_bar = StatusBar(self.root)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
    
    def _setup_bindings(self):
        """Setup keyboard shortcuts."""
        self.root.bind('<Right>', lambda e: self._navigate(1))
        self.root.bind('<Down>', lambda e: self._navigate(1))
        self.root.bind('<space>', lambda e: self._navigate(1))
        self.root.bind('<Left>', lambda e: self._navigate(-1))
        self.root.bind('<Up>', lambda e: self._navigate(-1))
        self.root.bind('<Home>', lambda e: self._goto_image(0))
        self.root.bind('<End>', lambda e: self._goto_image(-1))
    
    def _on_folder_select(self, folder_path: str):
        """Handle folder selection from tree."""
        logger.info(f"Folder selected: {folder_path}")
        try:
            self._current_folder = folder_path
            self._thumbnail_queue.clear()
            self._photo_refs.clear()
            
            # Clear current thumbnails
            logger.debug("Clearing thumbnails")
            self.thumbnail_strip.clear()
            
            # Find images in folder
            self.image_list = []
            try:
                for entry in os.scandir(folder_path):
                    if entry.is_file():
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in SUPPORTED_EXTENSIONS:
                            self.image_list.append(entry.path)
            except PermissionError:
                logger.warning(f"Permission denied: {folder_path}")
                self.status_bar.set_message(f"Permission denied: {folder_path}")
                return
            except Exception as e:
                logger.exception(f"Error scanning folder: {e}")
                self.status_bar.set_message(f"Error: {e}")
                return
            
            # Sort by name
            self.image_list.sort(key=lambda p: os.path.basename(p).lower())
            logger.info(f"Found {len(self.image_list)} images")
            
            if not self.image_list:
                self.status_bar.set_message(f"No images in {folder_path}")
                self.image_display.show_placeholder("📭 No images in this folder")
                return
            
            # Add placeholders
            logger.debug("Adding thumbnail placeholders")
            for img_path in self.image_list:
                self.thumbnail_strip.add_placeholder(img_path)
            
            self.status_bar.set_message(f"Loading {len(self.image_list)} images...")
            
            # Queue thumbnails for loading on main thread (no threading!)
            self._thumbnail_queue = list(self.image_list)
            self.root.after(50, self._load_next_thumbnail)
            
            # Display first image
            logger.debug("Displaying first image")
            self._goto_image(0)
            logger.debug("Folder selection complete")
            
        except Exception as e:
            logger.exception(f"Error in _on_folder_select: {e}")
    
    def _load_next_thumbnail(self):
        """Load next thumbnail from queue (on main thread via after)."""
        if not self._thumbnail_queue:
            # Done loading
            logger.info("All thumbnails loaded")
            self.status_bar.set_message(
                f"Loaded {len(self.image_list)} images from {self._current_folder}"
            )
            return
        
        # Get next image
        image_path = self._thumbnail_queue.pop(0)
        
        # Check if folder changed
        if self._current_folder and not image_path.startswith(self._current_folder):
            logger.debug("Folder changed, stopping thumbnail load")
            return
        
        try:
            thumb_bytes = self.cache.get_thumbnail(image_path)
            if thumb_bytes:
                img = Image.open(BytesIO(thumb_bytes))
                photo = ImageTk.PhotoImage(img)
                self._photo_refs.append(photo)  # MUST keep reference!
                self.thumbnail_strip.update_thumbnail(image_path, photo)
        except Exception as e:
            logger.debug(f"Error loading thumbnail {image_path}: {e}")
        
        # Update status
        remaining = len(self._thumbnail_queue)
        if remaining > 0 and remaining % 10 == 0:
            self.status_bar.set_message(f"Loading... {remaining} remaining")
        
        # Schedule next thumbnail
        if self._thumbnail_queue:
            self.root.after(5, self._load_next_thumbnail)
        else:
            logger.info("All thumbnails loaded")
            self.status_bar.set_message(
                f"Loaded {len(self.image_list)} images from {self._current_folder}"
            )
    
    def _on_thumbnail_select(self, image_path: str):
        """Handle thumbnail click."""
        try:
            self.current_index = self.image_list.index(image_path)
            self._display_current()
        except ValueError:
            pass
    
    def _navigate(self, delta: int):
        """Navigate to next/previous image."""
        if not self.image_list:
            return
        self.current_index = (self.current_index + delta) % len(self.image_list)
        self._display_current()
    
    def _goto_image(self, index: int):
        """Go to specific image index."""
        if not self.image_list:
            return
        if index < 0:
            index = len(self.image_list) + index
        self.current_index = max(0, min(index, len(self.image_list) - 1))
        self._display_current()
    
    def _display_current(self):
        """Display current image."""
        try:
            if 0 <= self.current_index < len(self.image_list):
                image_path = self.image_list[self.current_index]
                logger.debug(f"Displaying image: {image_path}")
                
                if self.image_display.load_image(image_path):
                    logger.debug("Image loaded, selecting thumbnail")
                    self.thumbnail_strip.select(image_path)
                    
                    # Update status with image info
                    try:
                        with Image.open(image_path) as img:
                            w, h = img.size
                            fmt = img.format or "Unknown"
                            size_kb = os.path.getsize(image_path) / 1024
                            filename = os.path.basename(image_path)
                            self.status_bar.set_message(
                                f"{filename}  •  {w}×{h}  •  {fmt}  •  {size_kb:.1f} KB  "
                                f"[{self.current_index + 1}/{len(self.image_list)}]"
                            )
                    except Exception as e:
                        logger.debug(f"Could not get image info: {e}")
                else:
                    logger.warning(f"Failed to load image: {image_path}")
        except Exception as e:
            logger.exception(f"Error in _display_current: {e}")
    
    def _on_close(self):
        """Clean up on window close."""
        logger.info("Closing application")
        self._thumbnail_queue.clear()
        self.cache.close()
        self.root.destroy()


# -----------------------------------------------------------------------------
# Entry Point
# -----------------------------------------------------------------------------
def handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception handler."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


def main():
    """Application entry point."""
    # Set global exception handler
    sys.excepthook = handle_exception
    
    logger.info(f"Python version: {sys.version}")
    logger.info(f"ROOT_PATH: {ROOT_PATH}")
    
    # Check root path
    if not os.path.exists(ROOT_PATH):
        logger.error(f"Root path does not exist: {ROOT_PATH}")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Error",
            f"Root path does not exist: {ROOT_PATH}\n\n"
            f"Please update ROOT_PATH in the script."
        )
        sys.exit(1)
    
    # Create and run app
    try:
        logger.info("Creating Tk root window")
        root = tk.Tk()
        
        logger.info("Creating ImageViewerApp")
        app = ImageViewerApp(root)
        
        logger.info("Starting mainloop")
        root.mainloop()
        
        logger.info("Mainloop exited normally")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        input("Press Enter to exit...")
        sys.exit(1)


if __name__ == "__main__":
    main()