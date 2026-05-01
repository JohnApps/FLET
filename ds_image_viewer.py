# ds_image_viewer.py
# cl1_image_viewer.py
# An enhanced GROK (gr_image_viewer.py) version
#
# gr_image_viewer.py
# V2 - Added thumbnail scrolling (scrollbar + mouse wheel + arrow keys)
#      Restructured thumbnail pane geometry so nav buttons don't squeeze the canvas
#      Fixed find_withtag tuple handling in highlight/unhighlight
# V3 - Added save/restore of last displayed image
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import os
from PIL import Image, ImageTk

# -------------- IMPORTANT: Disable Decompression Bomb Warning --------------
# This setting prevents Pillow from raising an error for potentially very large images.
# It's generally safe for curated image collections, but be cautious if loading
# images from untrusted external sources.
Image.MAX_IMAGE_PIXELS = None
# --------------------------------------------------------------------------

# File to store last displayed image path
LAST_IMAGE_FILE = r"H:\FLET\cl1_last_image.txt"


class ImageViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Viewer")
        self.root.geometry("1000x700")

        # --- Global Variables ---
        self.image_dir = r"O:\Bilder"  # Default image directory
        self.current_folder = ""
        self.current_image_path = ""
        self.images_in_folder = []
        self.current_image_index = -1

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
        self.current_image_path = image_path
        full_path_and_name = self.current_image_path
        self.path_label.config(text=f"Path: {full_path_and_name}")
        self.image_canvas.delete("all")  # Clear previous image
        
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
        
        # Check if the folder is within the current image_dir
        if not last_folder.startswith(self.image_dir):
            # Try to navigate to the parent directory of the last image
            # Update image_dir to last_folder's parent or root
            temp_dir = last_folder
            while temp_dir and temp_dir != os.path.dirname(temp_dir):
                if os.path.exists(os.path.join(temp_dir, os.path.basename(last_folder))):
                    # Check parent to see if it's a valid directory in our folder list
                    pass
                temp_dir = os.path.dirname(temp_dir)
        
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
                img = Image.open(img_path)
                img.thumbnail((thumbnail_size, thumbnail_size), Image.Resampling.LANCZOS)

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


if __name__ == "__main__":
    root = tk.Tk()
    app = ImageViewer(root)
    root.mainloop()