# cl_image_viewer_stats.py
#
# cl1_image_viewer.py
# An enhanced GROK (gr_image_viewer.py) version
#
# gr_image_viewer.py
# V2 - Added thumbnail scrolling (scrollbar + mouse wheel + arrow keys)
#      Restructured thumbnail pane geometry so nav buttons don't squeeze the canvas
#      Fixed find_withtag tuple handling in highlight/unhighlight
# V3 - Added save/restore of last displayed image
# V4 - Added resource usage monitoring per image and overall statistics
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import os
import io
import time
import psutil
import diskcache
from PIL import Image, ImageTk

# -------------- IMPORTANT: Disable Decompression Bomb Warning --------------
# This setting prevents Pillow from raising an error for potentially very large images.
# It's generally safe for curated image collections, but be cautious if loading
# images from untrusted external sources.
Image.MAX_IMAGE_PIXELS = None
# --------------------------------------------------------------------------

# File to store last displayed image path (portable: ~/.image_viewer/)
_APP_DIR = os.path.join(os.path.expanduser("~"), ".image_viewer")
LAST_IMAGE_FILE = os.path.join(_APP_DIR, "cl1_last_image.txt")
CACHE_DIR = os.path.join(_APP_DIR, "thumbnail_cache")


class ResourceMonitor:
    """Monitor system resources (CPU, memory, I/O, network) for each image view."""
    
    def __init__(self):
        self.reset()
        
    def reset(self):
        """Reset all monitoring data."""
        self.per_image_stats = {}  # image_path -> {'cpu': [], 'memory': [], 'io_read': [], 'io_write': [], 'network_sent': [], 'network_recv': [], 'duration': 0}
        self.current_image = None
        self.current_image_start_time = None
        self.current_image_start_cpu = None
        self.current_image_start_memory = None
        self.current_image_start_io = None
        self.current_image_start_network = None
        self.process = psutil.Process()
        
        # Get initial network counters (to calculate deltas)
        self.initial_network = psutil.net_io_counters()
        
        # Overall totals
        self.total_duration = 0
        self.total_cpu_samples = []
        self.total_memory_samples = []
        self.total_io_read = 0
        self.total_io_write = 0
        self.total_network_sent = 0
        self.total_network_recv = 0
        self.image_count = 0
        
    def start_monitoring(self, image_path):
        """Start monitoring resources for a new image."""
        # Stop monitoring previous image if any
        if self.current_image is not None:
            self.stop_monitoring()
        
        self.current_image = image_path
        self.current_image_start_time = time.time()
        
        # Get initial resource stats
        self.current_image_start_cpu = self.process.cpu_percent(interval=None)
        self.current_image_start_memory = self.process.memory_info().rss / (1024 * 1024)  # MB
        
        # I/O counters
        io_counters = self.process.io_counters()
        self.current_image_start_io = (io_counters.read_bytes, io_counters.write_bytes)
        
        # Network counters (system-wide, not per-process)
        network = psutil.net_io_counters()
        self.current_image_start_network = (network.bytes_sent, network.bytes_recv)
        
    def stop_monitoring(self):
        """Stop monitoring current image and record statistics."""
        if self.current_image is None:
            return
            
        duration = time.time() - self.current_image_start_time
        
        # Get final resource stats
        final_cpu = self.process.cpu_percent(interval=None)
        final_memory = self.process.memory_info().rss / (1024 * 1024)  # MB
        
        # I/O counters
        io_counters = self.process.io_counters()
        final_io_read = io_counters.read_bytes
        final_io_write = io_counters.write_bytes
        io_read_delta = final_io_read - self.current_image_start_io[0]
        io_write_delta = final_io_write - self.current_image_start_io[1]
        
        # Network counters (system-wide)
        network = psutil.net_io_counters()
        network_sent_delta = network.bytes_sent - self.current_image_start_network[0]
        network_recv_delta = network.bytes_recv - self.current_image_start_network[1]
        
        # Calculate average CPU and memory during the period
        # (Taking average of start and end for simplicity)
        avg_cpu = (self.current_image_start_cpu + final_cpu) / 2
        avg_memory = (self.current_image_start_memory + final_memory) / 2
        
        # Store stats for this image
        self.per_image_stats[self.current_image] = {
            'cpu': avg_cpu,
            'memory': avg_memory,
            'io_read': io_read_delta / (1024 * 1024),  # Convert to MB
            'io_write': io_write_delta / (1024 * 1024),  # Convert to MB
            'network_sent': network_sent_delta / (1024 * 1024),  # Convert to MB
            'network_recv': network_recv_delta / (1024 * 1024),  # Convert to MB
            'duration': duration
        }
        
        # Update overall totals
        self.total_duration += duration
        self.total_cpu_samples.append(avg_cpu)
        self.total_memory_samples.append(avg_memory)
        self.total_io_read += io_read_delta / (1024 * 1024)
        self.total_io_write += io_write_delta / (1024 * 1024)
        self.total_network_sent += network_sent_delta / (1024 * 1024)
        self.total_network_recv += network_recv_delta / (1024 * 1024)
        self.image_count += 1
        
        # Reset current image
        self.current_image = None
        
    def get_image_stats(self, image_path):
        """Get statistics for a specific image."""
        return self.per_image_stats.get(image_path, None)
    
    def get_overall_stats(self):
        """Get overall statistics for all images viewed."""
        if self.image_count == 0:
            return None
            
        return {
            'avg_cpu': sum(self.total_cpu_samples) / len(self.total_cpu_samples),
            'avg_memory': sum(self.total_memory_samples) / len(self.total_memory_samples),
            'total_io_read': self.total_io_read,
            'total_io_write': self.total_io_write,
            'total_network_sent': self.total_network_sent,
            'total_network_recv': self.total_network_recv,
            'total_duration': self.total_duration,
            'image_count': self.image_count
        }
    
    def display_statistics(self, parent, on_close_window=None):
        """Display resource usage statistics in a new window.
        
        on_close_window: optional callable invoked when user clicks 'Close Window'.
        """
        stats_window = tk.Toplevel(parent)
        stats_window.title("Resource Usage Statistics")
        stats_window.geometry("800x600")
        
        # Create notebook for tabs
        notebook = ttk.Notebook(stats_window)
        notebook.pack(fill=tk.BOTH, expand=1, padx=5, pady=5)
        
        # Tab 1: Overall Statistics
        overall_frame = ttk.Frame(notebook)
        notebook.add(overall_frame, text="Overall Statistics")
        
        overall_stats = self.get_overall_stats()
        if overall_stats:
            stats_text = f"""
            ╔══════════════════════════════════════════════════════════════╗
            ║                    OVERALL STATISTICS                         ║
            ╚══════════════════════════════════════════════════════════════╝
            
            Images Viewed:     {overall_stats['image_count']}
            Total Duration:    {overall_stats['total_duration']:.2f} seconds
            
            ┌─────────────────────────────────────────────────────────────┐
            │                      AVERAGE VALUES                          │
            ├─────────────────────────────────────────────────────────────┤
            │ CPU Usage:        {overall_stats['avg_cpu']:.2f}%                                │
            │ Memory Usage:     {overall_stats['avg_memory']:.2f} MB                            │
            └─────────────────────────────────────────────────────────────┘
            
            ┌─────────────────────────────────────────────────────────────┐
            │                       TOTAL I/O                              │
            ├─────────────────────────────────────────────────────────────┤
            │ Disk Read:        {overall_stats['total_io_read']:.2f} MB                           │
            │ Disk Write:       {overall_stats['total_io_write']:.2f} MB                          │
            └─────────────────────────────────────────────────────────────┘
            
            ┌─────────────────────────────────────────────────────────────┐
            │                    TOTAL NETWORK                             │
            ├─────────────────────────────────────────────────────────────┤
            │ Data Sent:        {overall_stats['total_network_sent']:.2f} MB                         │
            │ Data Received:    {overall_stats['total_network_recv']:.2f} MB                       │
            └─────────────────────────────────────────────────────────────┘
            """
        else:
            stats_text = "No images were viewed during this session."
        
        overall_label = tk.Label(overall_frame, text=stats_text, font=("Courier", 10), justify=tk.LEFT)
        overall_label.pack(padx=10, pady=10, anchor=tk.NW)
        
        # Tab 2: Per-Image Statistics
        per_image_frame = ttk.Frame(notebook)
        notebook.add(per_image_frame, text="Per-Image Statistics")
        
        # Create treeview for per-image stats
        columns = ('Image', 'CPU %', 'Memory (MB)', 'Duration (s)', 'I/O Read (MB)', 'I/O Write (MB)', 'Net Sent (MB)', 'Net Recv (MB)')
        tree = ttk.Treeview(per_image_frame, columns=columns, show='headings', height=20)
        
        # Define headings
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=100)
        
        # Special width for image column
        tree.column('Image', width=300)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(per_image_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Populate tree
        for image_path, stats in self.per_image_stats.items():
            filename = os.path.basename(image_path)
            tree.insert('', tk.END, values=(
                filename,
                f"{stats['cpu']:.2f}",
                f"{stats['memory']:.2f}",
                f"{stats['duration']:.2f}",
                f"{stats['io_read']:.2f}",
                f"{stats['io_write']:.2f}",
                f"{stats['network_sent']:.2f}",
                f"{stats['network_recv']:.2f}"
            ))
        
        # Add button to export statistics
        export_frame = ttk.Frame(stats_window)
        export_frame.pack(fill=tk.X, padx=5, pady=5)
        
        def export_stats():
            from datetime import datetime
            export_file = os.path.join(_APP_DIR, f"resource_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            try:
                os.makedirs(os.path.dirname(export_file), exist_ok=True)
                with open(export_file, 'w', encoding='utf-8') as f:
                    f.write("IMAGE VIEWER RESOURCE USAGE STATISTICS\n")
                    f.write("=" * 80 + "\n\n")
                    
                    if overall_stats:
                        f.write("OVERALL STATISTICS\n")
                        f.write("-" * 40 + "\n")
                        f.write(f"Images Viewed:     {overall_stats['image_count']}\n")
                        f.write(f"Total Duration:    {overall_stats['total_duration']:.2f} seconds\n\n")
                        f.write(f"Average CPU:       {overall_stats['avg_cpu']:.2f}%\n")
                        f.write(f"Average Memory:    {overall_stats['avg_memory']:.2f} MB\n\n")
                        f.write(f"Total I/O Read:    {overall_stats['total_io_read']:.2f} MB\n")
                        f.write(f"Total I/O Write:   {overall_stats['total_io_write']:.2f} MB\n\n")
                        f.write(f"Total Network Sent: {overall_stats['total_network_sent']:.2f} MB\n")
                        f.write(f"Total Network Recv: {overall_stats['total_network_recv']:.2f} MB\n\n")
                        
                        f.write("PER-IMAGE STATISTICS\n")
                        f.write("-" * 40 + "\n")
                        f.write(f"{'Image':<40} {'CPU%':<8} {'Mem(MB)':<10} {'Dur(s)':<8} {'IO-R(MB)':<10} {'IO-W(MB)':<10} {'Net-S(MB)':<10} {'Net-R(MB)':<10}\n")
                        f.write("-" * 116 + "\n")
                        
                        for image_path, stats in self.per_image_stats.items():
                            filename = os.path.basename(image_path)
                            f.write(f"{filename:<40} {stats['cpu']:<8.2f} {stats['memory']:<10.2f} {stats['duration']:<8.2f} {stats['io_read']:<10.2f} {stats['io_write']:<10.2f} {stats['network_sent']:<10.2f} {stats['network_recv']:<10.2f}\n")
                    
                messagebox.showinfo("Export Complete", f"Statistics exported to:\n{export_file}")
            except Exception as e:
                messagebox.showerror("Export Failed", f"Failed to export statistics:\n{e}")
        
        export_button = ttk.Button(export_frame, text="Export Statistics to File", command=export_stats)
        export_button.pack(side=tk.RIGHT, padx=5, pady=5)
        
        close_stats_button = ttk.Button(export_frame, text="Close", command=stats_window.destroy)
        close_stats_button.pack(side=tk.RIGHT, padx=5, pady=5)

        def _close_window():
            stats_window.destroy()
            if on_close_window:
                on_close_window()

        close_window_button = ttk.Button(export_frame, text="Close Window", command=_close_window)
        close_window_button.pack(side=tk.LEFT, padx=5, pady=5)


class ImageViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Viewer")
        self.root.geometry("1000x700")
        
        # Handle window close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- Global Variables ---
        self.image_dir = r"O:\Bilder"  # Default image directory
        self.current_folder = ""
        self.current_image_path = ""
        self.images_in_folder = []
        self.current_image_index = -1

        # --- Resource Monitor ---
        self.resource_monitor = ResourceMonitor()

        # --- Thumbnail disk cache (persists across sessions) ---
        os.makedirs(CACHE_DIR, exist_ok=True)
        self.thumb_cache = diskcache.Cache(CACHE_DIR)

        # --- Main Layout Panes ---
        self.paned_window = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=1, padx=5, pady=5)

        # Left Pane (Folders)
        self.left_frame = ttk.Frame(self.paned_window, width=200, relief=tk.SUNKEN)
        self.paned_window.add(self.left_frame, weight=1)
        self.create_folder_pane()

        # Right Pane (Images)
        self.right_frame = ttk.Frame(self.paned_window, relief=tk.SUNKEN)
        self.paned_window.add(self.right_frame, weight=3)
        self.create_image_pane()

        # --- Keyboard navigation ---
        self.root.bind("<Left>", lambda e: self.show_previous_image())
        self.root.bind("<Right>", lambda e: self.show_next_image())

        # --- Load initial data ---
        self.load_folders()
        
        # --- Restore last displayed image after UI is ready ---
        self.root.after(100, self.restore_last_image)

    def create_folder_pane(self):
        folder_label = ttk.Label(self.left_frame, text="Folders", font=("Arial", 12, "bold"))
        folder_label.pack(pady=5)

        self.folder_listbox = tk.Listbox(self.left_frame, selectmode=tk.SINGLE, width=30)
        self.folder_listbox.pack(fill=tk.BOTH, expand=1, padx=5, pady=5)
        self.folder_listbox.bind("<<ListboxSelect>>", self.on_folder_select)

        # Button to browse for directory
        browse_button = ttk.Button(self.left_frame, text="Browse Folder", command=self.browse_directory)
        browse_button.pack(pady=5)

    def create_image_pane(self):
        # Top Pane: Filename and Path
        self.path_frame = ttk.Frame(self.right_frame)
        self.path_frame.pack(fill=tk.X, padx=5, pady=5)

        self.path_label = ttk.Label(self.path_frame, text="Path: ", anchor=tk.W, justify=tk.LEFT)
        self.path_label.pack(side=tk.LEFT, fill=tk.X, expand=1)

        copy_button = ttk.Button(self.path_frame, text="Copy Path", command=self.copy_path_to_clipboard)
        copy_button.pack(side=tk.RIGHT, padx=5)

        # Navigation buttons — packed at the bottom FIRST so they reserve their space
        nav_frame = ttk.Frame(self.right_frame)
        nav_frame.pack(side=tk.BOTTOM, pady=2)

        prev_button = ttk.Button(nav_frame, text="Previous", command=self.show_previous_image)
        prev_button.pack(side=tk.LEFT, padx=5)

        next_button = ttk.Button(nav_frame, text="Next", command=self.show_next_image)
        next_button.pack(side=tk.LEFT, padx=5)

        # Thumbnail area: its own frame with canvas + horizontal scrollbar
        self.thumbnail_frame = ttk.Frame(self.right_frame, height=120, relief=tk.RIDGE)
        self.thumbnail_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)
        self.thumbnail_frame.pack_propagate(False)

        self.thumbnail_canvas = tk.Canvas(self.thumbnail_frame, bg="lightgray", height=100)
        self.thumbnail_scrollbar = ttk.Scrollbar(
            self.thumbnail_frame, orient=tk.HORIZONTAL, command=self.thumbnail_canvas.xview
        )
        self.thumbnail_canvas.configure(xscrollcommand=self.thumbnail_scrollbar.set)

        self.thumbnail_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.thumbnail_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=1)

        # Mouse wheel scrolling — only active while cursor is over the thumbnail area
        self.thumbnail_canvas.bind("<Enter>", self._bind_thumb_wheel)
        self.thumbnail_canvas.bind("<Leave>", self._unbind_thumb_wheel)

        # Main Image Display (packed last so it fills all remaining space above)
        self.image_canvas = tk.Canvas(self.right_frame, bg="gray")
        self.image_canvas.pack(fill=tk.BOTH, expand=1, padx=5, pady=5)
        self.image_canvas.bind("<Configure>", self.on_canvas_resize)

    # ---- Mouse wheel handlers for thumbnail canvas ----

    def _bind_thumb_wheel(self, event):
        # Windows/macOS use <MouseWheel>; Linux uses <Button-4>/<Button-5>
        self.thumbnail_canvas.bind_all("<MouseWheel>", self._on_thumb_wheel)
        self.thumbnail_canvas.bind_all("<Button-4>", self._on_thumb_wheel)
        self.thumbnail_canvas.bind_all("<Button-5>", self._on_thumb_wheel)

    def _unbind_thumb_wheel(self, event):
        self.thumbnail_canvas.unbind_all("<MouseWheel>")
        self.thumbnail_canvas.unbind_all("<Button-4>")
        self.thumbnail_canvas.unbind_all("<Button-5>")

    def _on_thumb_wheel(self, event):
        # Normalize wheel event across platforms
        if event.num == 4:
            delta = -1
        elif event.num == 5:
            delta = 1
        else:
            delta = -1 if event.delta > 0 else 1
        self.thumbnail_canvas.xview_scroll(delta, "units")

    # ---------------------------------------------------

    def browse_directory(self):
        directory = filedialog.askdirectory(initialdir=self.image_dir)
        if directory:
            self.image_dir = directory
            self.load_folders()
            # If a folder was selected and we change directory, clear the current selection
            self.current_folder = ""
            self.current_image_index = -1
            self.images_in_folder = []
            self.path_label.config(text="Path: ")
            self.image_canvas.delete("all")
            self.thumbnail_canvas.delete("all")
            self.folder_listbox.selection_clear(0, tk.END)

    def load_folders(self):
        self.folder_listbox.delete(0, tk.END)
        if not os.path.isdir(self.image_dir):
            messagebox.showerror("Error", f"Directory not found: {self.image_dir}")
            return

        try:
            for item in os.listdir(self.image_dir):
                full_path = os.path.join(self.image_dir, item)
                if os.path.isdir(full_path):
                    self.folder_listbox.insert(tk.END, item)
        except Exception as e:
            messagebox.showerror("Error", f"Could not list directories: {e}")

    def on_folder_select(self, event):
        selected_indices = self.folder_listbox.curselection()
        if not selected_indices:
            return

        selected_folder_name = self.folder_listbox.get(selected_indices[0])
        self.current_folder = os.path.join(self.image_dir, selected_folder_name)
        self.load_images_from_folder()

    def load_images_from_folder(self):
        self.images_in_folder = []
        self.thumbnail_canvas.delete("all")
        self.image_canvas.delete("all")
        self.path_label.config(text="Path: ")
        self.current_image_index = -1

        if not os.path.isdir(self.current_folder):
            return

        supported_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff')
        try:
            for item in os.listdir(self.current_folder):
                full_path = os.path.join(self.current_folder, item)
                if os.path.isfile(full_path) and item.lower().endswith(supported_extensions):
                    self.images_in_folder.append(full_path)

            if self.images_in_folder:
                self.current_image_index = 0
                self.display_image(self.images_in_folder[self.current_image_index])
                self.load_thumbnails()
                # Highlight the first thumbnail initially
                self.highlight_thumbnail(0)
            else:
                self.path_label.config(text="Path: No images found in this folder.")

        except Exception as e:
            messagebox.showerror("Error", f"Could not load images from {self.current_folder}: {e}")

    def display_image(self, image_path):
        # Stop monitoring previous image
        if self.current_image_path:
            self.resource_monitor.stop_monitoring()
        
        self.current_image_path = image_path
        full_path_and_name = self.current_image_path
        self.path_label.config(text=f"Path: {full_path_and_name}")
        self.image_canvas.delete("all")  # Clear previous image
        
        # Start monitoring this image
        self.resource_monitor.start_monitoring(image_path)
        
        # Save the last displayed image to file
        self.save_last_image(image_path)

        try:
            # Open image, resize proportionally to fit canvas
            img = Image.open(image_path)
            canvas_width = self.image_canvas.winfo_width()
            canvas_height = self.image_canvas.winfo_height()

            if canvas_width <= 1 or canvas_height <= 1:  # Canvas not yet rendered, or too small
                self.root.after(100, lambda: self.display_image(image_path))  # Try again
                return

            img_width, img_height = img.size
            ratio = min(canvas_width / img_width, canvas_height / img_height)
            new_width = int(img_width * ratio)
            new_height = int(img_height * ratio)

            # Ensure dimensions are at least 1x1 to avoid errors
            if new_width < 1 or new_height < 1:
                return

            resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            self.tk_img = ImageTk.PhotoImage(resized_img)

            # Center the image on the canvas
            x_center = (canvas_width - new_width) // 2
            y_center = (canvas_height - new_height) // 2
            self.image_canvas.create_image(x_center, y_center, anchor=tk.NW, image=self.tk_img)

        except FileNotFoundError:
            self.path_label.config(text=f"Path: File not found - {image_path}")
            messagebox.showerror("Error", f"Image file not found: {image_path}")
        except Exception as e:
            self.path_label.config(text=f"Path: Error loading image - {image_path}")
            messagebox.showerror("Error", f"Could not load image: {image_path}\n{e}")

    def save_last_image(self, image_path):
        """Save the last displayed image path to a text file."""
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(LAST_IMAGE_FILE), exist_ok=True)
            
            with open(LAST_IMAGE_FILE, 'w', encoding='utf-8') as f:
                f.write(image_path)
        except Exception as e:
            print(f"Warning: Could not save last image path: {e}")

    def load_last_image(self):
        """Load the last displayed image path from the text file."""
        try:
            if os.path.exists(LAST_IMAGE_FILE):
                with open(LAST_IMAGE_FILE, 'r', encoding='utf-8') as f:
                    last_path = f.read().strip()
                return last_path
        except Exception as e:
            print(f"Warning: Could not read last image path: {e}")
        return None

    def restore_last_image(self):
        """Attempt to restore the last displayed image when the application starts."""
        last_path = self.load_last_image()
        
        if not last_path or not os.path.isfile(last_path):
            return  # No valid last image to restore
        
        # Get the folder containing the last image
        last_folder = os.path.dirname(last_path)
        last_filename = os.path.basename(last_path)
        
        # Find the folder name relative to image_dir
        if last_folder.startswith(self.image_dir):
            rel_folder = os.path.relpath(last_folder, self.image_dir)
            # Handle case where image is directly in image_dir (not in subfolder)
            if rel_folder == '.':
                # Image is in the root image_dir - but our folder list only shows subfolders
                # In this case, we can't restore the image directly
                print("Last image is in root directory, cannot restore automatically")
                return
        else:
            # Last image is outside image_dir - can't restore automatically
            print("Last image is outside default directory, cannot restore automatically")
            return
        
        # Look for the folder in the listbox and select it
        folder_found = False
        for i in range(self.folder_listbox.size()):
            if self.folder_listbox.get(i) == rel_folder:
                self.folder_listbox.selection_set(i)
                self.folder_listbox.see(i)
                folder_found = True
                break
        
        if not folder_found:
            print(f"Folder '{rel_folder}' not found in folder list")
            return
        
        # Trigger folder selection (this will load images and thumbnails)
        self.on_folder_select(None)
        
        # After folder loads, find and select the specific image
        self.root.after(200, lambda: self.select_image_by_path(last_path))
    
    def select_image_by_path(self, image_path):
        """Select and display an image by its full path."""
        if not self.images_in_folder:
            return
        
        try:
            # Find index of the image in the current folder's image list
            index = self.images_in_folder.index(image_path)
            
            # Select the thumbnail (this will also display the image)
            self.select_thumbnail(index)
            
        except ValueError:
            # Image not found in current folder list
            print(f"Image '{image_path}' not found in current folder")
        except Exception as e:
            print(f"Error selecting image by path: {e}")

    def on_canvas_resize(self, event):
        if self.current_image_path and self.images_in_folder:
            self.display_image(self.current_image_path)

    def load_thumbnails(self):
        self.thumbnail_canvas.delete("all")
        if not self.images_in_folder:
            return

        thumbnail_size = 80
        padding = 5
        current_x = padding
        self.thumbnail_image_objects = []  # To store PhotoImage objects

        for i, img_path in enumerate(self.images_in_folder):
            try:
                mtime = os.path.getmtime(img_path)
                cache_key = f"{img_path}|{mtime}|{thumbnail_size}"

                if cache_key in self.thumb_cache:
                    png_bytes = self.thumb_cache[cache_key]
                    img = Image.open(io.BytesIO(png_bytes))
                else:
                    img = Image.open(img_path)
                    img.thumbnail((thumbnail_size, thumbnail_size), Image.Resampling.LANCZOS)
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    self.thumb_cache.set(cache_key, buf.getvalue())

                tk_img = ImageTk.PhotoImage(img)
                self.thumbnail_image_objects.append(tk_img)  # Keep reference

                # Create a clickable rectangle for the thumbnail
                rect_id = self.thumbnail_canvas.create_rectangle(
                    current_x, padding,
                    current_x + thumbnail_size + padding, padding + thumbnail_size + padding,
                    fill="white", outline="gray", width=1, tags=f"thumbnail_rect_{i}"
                )
                img_id = self.thumbnail_canvas.create_image(
                    current_x + padding, padding, anchor=tk.NW, image=tk_img, tags=f"thumbnail_img_{i}"
                )

                self.thumbnail_canvas.tag_bind(rect_id, "<Button-1>", lambda e, idx=i: self.select_thumbnail(idx))
                self.thumbnail_canvas.tag_bind(img_id, "<Button-1>", lambda e, idx=i: self.select_thumbnail(idx))

                current_x += thumbnail_size + 2 * padding

            except Exception as e:
                print(f"Error loading thumbnail for {img_path}: {e}")

        # Update scrollregion so the scrollbar knows the full extent
        self.thumbnail_canvas.config(scrollregion=self.thumbnail_canvas.bbox("all"))

    def highlight_thumbnail(self, index):
        # find_withtag returns a tuple of IDs — iterate to be safe
        for rect_id in self.thumbnail_canvas.find_withtag(f"thumbnail_rect_{index}"):
            self.thumbnail_canvas.itemconfig(rect_id, outline="blue", width=3)

    def unhighlight_thumbnail(self, index):
        for rect_id in self.thumbnail_canvas.find_withtag(f"thumbnail_rect_{index}"):
            self.thumbnail_canvas.itemconfig(rect_id, outline="gray", width=1)

    def select_thumbnail(self, index):
        if 0 <= index < len(self.images_in_folder):
            # Unhighlight previous thumbnail
            if self.current_image_index != -1:
                self.unhighlight_thumbnail(self.current_image_index)

            self.current_image_index = index
            self.display_image(self.images_in_folder[self.current_image_index])

            # Highlight current thumbnail
            self.highlight_thumbnail(self.current_image_index)

            # Scroll thumbnail canvas to show selected thumbnail
            self.scroll_thumbnail_to_index(index)

    def scroll_thumbnail_to_index(self, index):
        thumbnail_size = 80
        padding = 5
        # Calculate the starting x-coordinate of the thumbnail
        x_pos = padding + index * (thumbnail_size + 2 * padding)

        bbox = self.thumbnail_canvas.bbox("all")
        if not bbox:
            return

        total_width = bbox[2]
        canvas_width = self.thumbnail_canvas.winfo_width()

        if total_width <= canvas_width:
            return  # Nothing to scroll — everything fits

        # Try to center the selected thumbnail in the visible area
        target_x = max(0, x_pos - canvas_width // 2)
        ratio = target_x / total_width
        ratio = max(0.0, min(1.0, ratio))
        self.thumbnail_canvas.xview_moveto(ratio)

    def show_previous_image(self):
        if self.images_in_folder and self.current_image_index > 0:
            self.select_thumbnail(self.current_image_index - 1)

    def show_next_image(self):
        if self.images_in_folder and self.current_image_index < len(self.images_in_folder) - 1:
            self.select_thumbnail(self.current_image_index + 1)

    def copy_path_to_clipboard(self):
        if self.current_image_path:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.current_image_path)
            messagebox.showinfo("Copied", "Image path copied to clipboard.")
    
    def on_closing(self):
        """Handle window closing event — show stats, destroy only after 'Close Window'."""
        if self.current_image_path:
            self.resource_monitor.stop_monitoring()
        
        # Withdraw instead of destroy so the stats window has a live parent
        self.root.withdraw()
        self.resource_monitor.display_statistics(
            parent=self.root,
            on_close_window=self.root.destroy
        )


if __name__ == "__main__":
    root = tk.Tk()
    app = ImageViewer(root)
    root.mainloop()