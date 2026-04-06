# gro_pdf_viewer.py
# V1 - by GROK
import flet as ft
import os
import base64
import io
from pathlib import Path
import fitz  # PyMuPDF
import pdfplumber
from typing import List, Optional, Tuple

# Configuration
FONT_SIZE = 16
PAGE_CACHE_SIZE = 5  # Number of pages to keep in memory for smoother navigation

class PDFViewer:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "AI Book PDF Viewer"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 10
        self.page.spacing = 10

        # Environment directory
        self.pdf_dir = Path(os.getenv("AI_BOOK", "."))
        if not self.pdf_dir.exists():
            self.pdf_dir = Path(".")

        # State
        self.pdf_files: List[Path] = []
        self.current_pdf: Optional[Path] = None
        self.doc: Optional[fitz.Document] = None
        self.current_page_idx: int = 0
        self.zoom_level: float = 1.0
        self.fit_mode: str = "width"  # "width" or "page"
        self.image_data: Optional[bytes] = None
        self.offset_x: float = 0.0
        self.offset_y: float = 0.0
        self.is_dragging: bool = False
        self.last_pointer_x: float = 0.0
        self.last_pointer_y: float = 0.0

        self.page_cache: dict[int, bytes] = {}  # page_idx -> image bytes

        self.build_ui()
        self.load_pdf_list()

    def build_ui(self):
        # Left pane: PDF list + search
        self.search_field = ft.TextField(
            label="Search PDFs",
            hint_text="Type to filter...",
            on_change=self.filter_pdfs,
            expand=True,
            text_size=FONT_SIZE,
        )

        self.pdf_list = ft.ListView(
            expand=True,
            spacing=5,
            padding=10,
            auto_scroll=False,
        )

        left_pane = ft.Container(
            content=ft.Column([
                self.search_field,
                ft.Text("PDF Files", size=FONT_SIZE + 2, weight=ft.FontWeight.BOLD),
                self.pdf_list,
            ], expand=True, spacing=10),
            width=300,
            border=ft.border.all(1, ft.colors.OUTLINE),
            padding=10,
        )

        # Right pane: Preview
        self.path_display = ft.Text(
            "No PDF selected",
            size=FONT_SIZE,
            color=ft.colors.ON_SURFACE_VARIANT,
            expand=True,
        )

        # Toolbar
        self.page_info = ft.Text("Page 0 / 0", size=FONT_SIZE)
        self.zoom_info = ft.Text("100%", size=FONT_SIZE)

        toolbar = ft.Row(
            controls=[
                ft.IconButton(ft.icons.NAVIGATE_BEFORE, on_click=self.prev_page, tooltip="Previous Page"),
                self.page_info,
                ft.IconButton(ft.icons.NAVIGATE_NEXT, on_click=self.next_page, tooltip="Next Page"),
                ft.VerticalDivider(),
                ft.IconButton(ft.icons.ZOOM_OUT, on_click=self.zoom_out, tooltip="Zoom Out"),
                self.zoom_info,
                ft.IconButton(ft.icons.ZOOM_IN, on_click=self.zoom_in, tooltip="Zoom In"),
                ft.IconButton(ft.icons.FIT_WIDTH, on_click=self.toggle_fit_mode, tooltip="Toggle Fit Mode (Width / Page)"),
                ft.IconButton(ft.icons.FULLSCREEN, on_click=self.open_fullscreen, tooltip="Full Screen"),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=10,
        )

        # PDF Preview area with pan support
        self.preview_container = ft.Container(
            expand=True,
            bgcolor=ft.colors.SURFACE,
            alignment=ft.alignment.center,
            content=ft.GestureDetector(
                content=ft.Image(
                    src_base64="",
                    fit=ft.ImageFit.CONTAIN,
                    repeat=ft.ImageRepeat.NO_REPEAT,
                ),
                on_pan_start=self.on_pan_start,
                on_pan_update=self.on_pan_update,
                on_double_tap=self.open_fullscreen,
                drag_interval=10,
            ),
        )

        right_pane = ft.Column(
            controls=[
                ft.Row([ft.Text("PDF Path:", size=FONT_SIZE), self.path_display], spacing=10),
                toolbar,
                self.preview_container,
            ],
            expand=True,
            spacing=10,
        )

        # Main layout
        self.page.add(
            ft.Row(
                controls=[left_pane, ft.VerticalDivider(), right_pane],
                expand=True,
                spacing=10,
            )
        )

        # Keyboard shortcuts
        self.page.on_keyboard_event = self.on_keyboard

    def load_pdf_list(self):
        self.pdf_files = sorted(
            [p for p in self.pdf_dir.rglob("*.pdf") if p.is_file()],
            key=lambda x: x.name.lower()
        )
        self.update_pdf_list_view(self.pdf_files)

    def update_pdf_list_view(self, files: List[Path]):
        self.pdf_list.controls.clear()
        for pdf_path in files:
            item = ft.ListTile(
                title=ft.Text(pdf_path.name, size=FONT_SIZE),
                subtitle=ft.Text(str(pdf_path.parent), size=FONT_SIZE - 2, color=ft.colors.ON_SURFACE_VARIANT),
                on_click=lambda e, p=pdf_path: self.load_pdf(p),
            )
            self.pdf_list.controls.append(item)
        self.page.update()

    def filter_pdfs(self, e):
        query = self.search_field.value.lower().strip() if self.search_field.value else ""
        filtered = [p for p in self.pdf_files if query in p.name.lower()]
        self.update_pdf_list_view(filtered)

    def load_pdf(self, pdf_path: Path):
        try:
            if self.doc:
                self.doc.close()

            self.current_pdf = pdf_path
            self.doc = fitz.open(pdf_path)
            self.current_page_idx = 0
            self.zoom_level = 1.0
            self.offset_x = 0.0
            self.offset_y = 0.0
            self.page_cache.clear()

            self.path_display.value = str(pdf_path)
            self.render_current_page()
            self.page.update()
        except Exception as ex:
            self.show_error(f"Failed to load PDF: {ex}")

    def render_current_page(self):
        if not self.doc or self.current_page_idx >= len(self.doc):
            return

        try:
            page_num = self.current_page_idx
            if page_num in self.page_cache:
                img_bytes = self.page_cache[page_num]
            else:
                page = self.doc[page_num]
                # Render with zoom
                matrix = fitz.Matrix(self.zoom_level, self.zoom_level)
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                img_bytes = pix.tobytes("jpeg", quality=95)

                # Cache management
                self.page_cache[page_num] = img_bytes
                if len(self.page_cache) > PAGE_CACHE_SIZE:
                    oldest = min(self.page_cache.keys())
                    if oldest != page_num:
                        del self.page_cache[oldest]

            # Update image
            img_control = self.preview_container.content.content
            img_control.src_base64 = base64.b64encode(img_bytes).decode("utf-8")
            img_control.width = None
            img_control.height = None

            self.page_info.value = f"Page {self.current_page_idx + 1} / {len(self.doc)}"
            self.zoom_info.value = f"{int(self.zoom_level * 100)}%"

            self.page.update()
        except Exception as ex:
            self.show_error(f"Render error: {ex}")

    def prev_page(self, e=None):
        if self.doc and self.current_page_idx > 0:
            self.current_page_idx -= 1
            self.render_current_page()

    def next_page(self, e=None):
        if self.doc and self.current_page_idx < len(self.doc) - 1:
            self.current_page_idx += 1
            self.render_current_page()

    def zoom_in(self, e=None):
        self.zoom_level = min(self.zoom_level * 1.2, 5.0)
        self.render_current_page()

    def zoom_out(self, e=None):
        self.zoom_level = max(self.zoom_level / 1.2, 0.2)
        self.render_current_page()

    def toggle_fit_mode(self, e=None):
        self.fit_mode = "page" if self.fit_mode == "width" else "width"
        # In this implementation we rely on ImageFit.CONTAIN + manual zoom
        # For better fit logic you could adjust zoom_level based on container size
        self.render_current_page()

    def on_pan_start(self, e: ft.DragStartEvent):
        self.is_dragging = True
        self.last_pointer_x = e.local_x
        self.last_pointer_y = e.local_y

    def on_pan_update(self, e: ft.DragUpdateEvent):
        if not self.is_dragging:
            return
        dx = e.local_x - self.last_pointer_x
        dy = e.local_y - self.last_pointer_y
        self.offset_x += dx
        self.offset_y += dy
        self.last_pointer_x = e.local_x
        self.last_pointer_y = e.local_y

        # Apply offset (limited implementation – full pan needs more complex Stack/Gesture handling)
        # For simplicity we reset offset on render for now; extend with a Stack if needed
        self.render_current_page()

    def open_fullscreen(self, e=None):
        if not self.current_pdf or not self.doc:
            return

        def close_fullscreen(e2):
            self.page.dialog.open = False
            self.page.update()

        fullscreen_img = ft.Image(
            src_base64=self.preview_container.content.content.src_base64,
            fit=ft.ImageFit.CONTAIN,
            expand=True,
        )

        dlg = ft.AlertDialog(
            modal=True,
            content=ft.Container(
                content=fullscreen_img,
                expand=True,
                padding=0,
                margin=0,
            ),
            actions=[ft.TextButton("Close", on_click=close_fullscreen)],
            actions_alignment=ft.MainAxisAlignment.END,
            full_screen=True,
        )
        self.page.dialog = dlg
        dlg.open = True
        self.page.update()

    def on_keyboard(self, e: ft.KeyboardEvent):
        if e.key == "ArrowLeft" or e.key == "Page Up":
            self.prev_page()
        elif e.key == "ArrowRight" or e.key == "Page Down":
            self.next_page()
        elif e.key == "+":
            self.zoom_in()
        elif e.key == "-":
            self.zoom_out()
        elif e.key.lower() == "f":
            self.open_fullscreen()

    def show_error(self, message: str):
        snack = ft.SnackBar(
            content=ft.Text(message, size=FONT_SIZE),
            bgcolor=ft.colors.ERROR,
        )
        self.page.snack_bar = snack
        snack.open = True
        self.page.update()

    # Search within current PDF
    def search_in_pdf(self, query: str) -> List[Tuple[int, str]]:
        results = []
        if not self.doc or not query:
            return results
        try:
            with pdfplumber.open(self.current_pdf) as pdf:
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    if query.lower() in text.lower():
                        results.append((i, text[:200] + "..." if len(text) > 200 else text))
        except Exception:
            # Fallback to PyMuPDF text extraction
            for i in range(len(self.doc)):
                text = self.doc[i].get_text()
                if query.lower() in text.lower():
                    results.append((i, text[:200] + "..."))
        return results


def main(page: ft.Page):
    PDFViewer(page)


if __name__ == "__main__":
    ft.app(main, view=ft.WEB_BROWSER)  # or ft.FLET_APP for desktop