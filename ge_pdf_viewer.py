# ge_pdf_viewer.py
# The Gemini version
#
import os
import flet as ft
import fitz  # PyMuPDF
import base64

# Requirement: Load path from environment variable AI_BOOK
BASE_DIR = os.getenv("AI_BOOK", r"C:\Default\Path") 
FONT_SIZE = 16 # Requirement: Font size 16

class PDFExplorer:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "AI Book PDF Explorer"
        self.page.window_maximized = True
        self.page.padding = 0
        self.page.theme_mode = ft.ThemeMode.LIGHT
        
        # State Management
        self.pdf_doc = None
        self.current_page_num = 0
        self.zoom_factor = 1.0
        self.current_path = ""

        # UI Components
        self.file_list = ft.ListView(expand=1, spacing=5)
        self.search_field = ft.TextField(
            label="Search PDF Files", 
            on_change=self.handle_search,
            text_size=FONT_SIZE
        )
        
        # Requirement: Display path at top of right pane
        self.path_label = ft.Text(value="No file selected", size=FONT_SIZE, weight="bold")
        
        # The container holding our dynamic images
        self.image_container = ft.Container(
            expand=True, 
            alignment="center",
            on_click=self.toggle_fs 
        )
        
        self.page_info = ft.Text(size=FONT_SIZE)
        
        # Requirement: Search within the PDF
        self.pdf_search = ft.TextField(
            label="Find text...", 
            width=150, 
            text_size=14,
            on_submit=self.find_in_pdf
        )
        
        self.setup_layout()
        self.load_directory()

    def setup_layout(self):
        toolbar = ft.Row([
            ft.TextButton(content=ft.Text("< Prev"), on_click=self.prev_page), 
            self.page_info,
            ft.TextButton(content=ft.Text("Next >"), on_click=self.next_page), 
            ft.VerticalDivider(),
            ft.TextButton(content=ft.Text("Zoom +"), on_click=self.zoom_in),
            ft.TextButton(content=ft.Text("Zoom -"), on_click=self.zoom_out),
            self.pdf_search,
            ft.TextButton(content=ft.Text("Full Screen"), on_click=self.toggle_fs)
        ], alignment="center") 

        # Requirement: Split pane layout
        self.page.add(
            ft.Row([
                # Left Pane (Sidebar)
                ft.Container(
                    content=ft.Column([self.search_field, self.file_list]),
                    width=350,
                    bgcolor="grey100",
                    padding=15
                ),
                # Right Pane (Content)
                ft.Column([
                    ft.Container(self.path_label, padding=10, bgcolor="bluegrey50"),
                    toolbar,
                    self.image_container 
                ], expand=True)
            ], expand=True)
        )

    def load_directory(self, filter_text=""):
        self.file_list.controls.clear()
        if os.path.exists(BASE_DIR):
            for file in os.listdir(BASE_DIR):
                if file.lower().endswith(".pdf") and filter_text.lower() in file.lower():
                    self.file_list.controls.append(
                        ft.ListTile(
                            title=ft.Text(file, size=FONT_SIZE),
                            on_click=lambda e, f=file: self.open_pdf(f)
                        )
                    )
        self.page.update()

    def handle_search(self, e):
        self.load_directory(self.search_field.value)

    def open_pdf(self, filename):
        self.current_path = os.path.join(BASE_DIR, filename)
        self.path_label.value = self.current_path 
        self.pdf_doc = fitz.open(self.current_path)
        self.current_page_num = 0
        self.zoom_factor = 1.0 # Reset zoom on new file
        self.render_page()

    def find_in_pdf(self, e):
        if not self.pdf_doc or not self.pdf_search.value:
            return
        term = self.pdf_search.value.lower()
        for i in range(len(self.pdf_doc)):
            if term in self.pdf_doc[i].get_text().lower():
                self.current_page_num = i
                self.render_page()
                break

    def render_page(self):
        if not self.pdf_doc: return
        page = self.pdf_doc[self.current_page_num]
        
        matrix = fitz.Matrix(self.zoom_factor, self.zoom_factor)
        
        # alpha=False forces a solid white background
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        
        # CRITICAL FIX: Extract as JPEG!
        # This reduces the image data from ~5MB down to ~150KB. 
        # It completely stops Flet's WebSocket from choking and disconnecting (the "gray out" effect).
        jpeg_bytes = pix.tobytes("jpeg")
        b64_string = base64.b64encode(jpeg_bytes).decode("utf-8")
        
        # Build the fresh image control
        new_image = ft.Image(src="", fit="contain")
        new_image.expand = True
        new_image.src_base64 = b64_string
        
        # Inject the new image and explicitly update the container
        self.image_container.content = new_image
        self.image_container.update()
        
        self.page_info.value = f"Page {self.current_page_num + 1} of {len(self.pdf_doc)}"
        self.page_info.update()

    def next_page(self, e):
        if self.pdf_doc and self.current_page_num < len(self.pdf_doc) - 1:
            self.current_page_num += 1
            self.render_page()

    def prev_page(self, e):
        if self.pdf_doc and self.current_page_num > 0:
            self.current_page_num -= 1
            self.render_page()

    def zoom_in(self, e):
        self.zoom_factor += 0.2
        self.render_page()

    def zoom_out(self, e):
        if self.zoom_factor > 0.4:
            self.zoom_factor -= 0.2
            self.render_page()

    def toggle_fs(self, e):
        self.page.window_full_screen = not self.page.window_full_screen
        self.page.update()

def main(page: ft.Page):
    PDFExplorer(page)

if __name__ == "__main__":
    ft.run(main)