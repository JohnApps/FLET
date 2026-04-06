# gro_pdf_viewer.py
# V1 - by GROK
# V2 - corrected flet version incompatabilities
# V3 - Recommended (native desktop window)
# V4 - correct use of colors
# V5 - use of ARROW not supported
# V6 - removed target keyword
# V7 - added text for arrows
# V8 - more arrow key errors
# V9 - arrow keys still invalid
# V10 - more attribute erors
# V11 - missing 1 required positional argument: 'src'
# V12 -  module 'flet.controls.alignment' has no attribute 'center
# V13 - more center problems
# V14 - no valid src supplied
# V15 - invalid src values
# gro_pdf_viewer.py
import flet as ft
import os
import base64
from pathlib import Path
import fitz  # PyMuPDF
import pdfplumber
from typing import List, Optional

FONT_SIZE = 16

class PDFViewer:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "gro_pdf_viewer - AI Book PDF Viewer"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0
        self.page.spacing = 0
        self.page.window_min_width = 1100
        self.page.window_min_height = 700

        # PDF directory from AI_BOOK environment variable
        self.pdf_dir = Path(os.getenv("AI_BOOK", os.getcwd()))
        if not self.pdf_dir.exists():
            self.pdf_dir = Path(os.getcwd())

        # State
        self.pdf_files: List[Path] = []
        self.current_pdf: Optional[Path] = None
        self.doc: Optional[fitz.Document] = None
        self.current_page_idx: int = 0
        self.zoom_level: float = 1.0
        self.fit_mode: str = "width"
        self.page_cache: dict = {}

        self.build_ui()
        self.load_pdf_list()

    def build_ui(self):
        # LEFT PANE
        self.search_field = ft.TextField(
            label="Search PDFs",
            hint_text="Filter by filename...",
            on_change=self.filter_pdfs,
            expand=True,
            text_size=FONT_SIZE,
            height=50,
        )

        self.pdf_listview = ft.ListView(expand=True, spacing=4, padding=10)

        left_pane = ft.Container(
            content=ft.Column([
                self.search_field,
                ft.Text("Available PDFs", size=FONT_SIZE + 2, weight=ft.FontWeight.BOLD),
                self.pdf_listview,
            ], expand=True, spacing=10),
            width=340,
            border=ft.Border.only(right=ft.BorderSide(1, ft.Colors.OUTLINE)),
            padding=15,
        )

        # RIGHT PANE
        self.path_text = ft.Text(
            "No PDF loaded",
            size=FONT_SIZE,
            color=ft.Colors.ON_SURFACE_VARIANT,
            expand=True
        )

        self.page_label = ft.Text("0 / 0", size=FONT_SIZE, width=110)
        self.zoom_label = ft.Text("100%", size=FONT_SIZE, width=70)

        toolbar = ft.Row(
            [
                ft.IconButton(ft.Icons.ARROW_LEFT, tooltip="Previous Page (←)", on_click=self.prev_page),
                ft.Text("Page", size=FONT_SIZE),
                self.page_label,
                ft.IconButton(ft.Icons.ARROW_RIGHT, tooltip="Next Page (→)", on_click=self.next_page),
                ft.VerticalDivider(),
                ft.IconButton(ft.Icons.ZOOM_OUT, tooltip="Zoom Out (-)", on_click=self.zoom_out),
                self.zoom_label,
                ft.IconButton(ft.Icons.ZOOM_IN, tooltip="Zoom In (+)", on_click=self.zoom_in),
                ft.IconButton(ft.Icons.FIT_SCREEN, tooltip="Toggle Fit Mode", on_click=self.toggle_fit_mode),
                ft.IconButton(ft.Icons.FULLSCREEN, tooltip="Full Screen", on_click=self.show_fullscreen),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=10,
            height=60,
        )

        # PDF Preview - create with src only (no src_base64 in constructor)
        self.preview_image = ft.Image(
            src="", 
            fit=ft.BoxFit.CONTAIN, 
            expand=True
        )

        self.gesture_detector = ft.GestureDetector(
            content=ft.Stack([self.preview_image], expand=True),
            on_pan_start=self.on_pan_start,
            on_pan_update=self.on_pan_update,
            on_double_tap=self.show_fullscreen,
            drag_interval=10,
        )

        self.preview_container = ft.Container(
            content=self.gesture_detector,
            expand=True,
            bgcolor=ft.Colors.SURFACE,
            alignment=ft.Alignment(0.5, 0.5),
        )

        # Search inside PDF
        self.pdf_search_field = ft.TextField(
            label="Search inside current PDF",
            hint_text="Type text and press Enter...",
            on_submit=self.search_in_current_pdf,
            text_size=FONT_SIZE,
            expand=True,
        )

        right_top = ft.Row([ft.Text("PDF Path:", size=FONT_SIZE), self.path_text], spacing=10)

        right_pane = ft.Column([
            right_top,
            toolbar,
            self.preview_container,
            self.pdf_search_field,
        ], expand=True, spacing=10)

        self.page.add(ft.Row([left_pane, right_pane], expand=True, spacing=0))

        self.page.on_keyboard_event = self.on_keyboard

    def load_pdf_list(self):
        self.pdf_files = sorted(self.pdf_dir.rglob("*.pdf"), key=lambda p: p.name.lower())
        self.refresh_pdf_list(self.pdf_files)

    def refresh_pdf_list(self, files: List[Path]):
        self.pdf_listview.controls.clear()
        for pdf in files:
            tile = ft.ListTile(
                title=ft.Text(pdf.name, size=FONT_SIZE),
                subtitle=ft.Text(str(pdf.parent), size=FONT_SIZE - 2, color=ft.Colors.ON_SURFACE_VARIANT),
                on_click=lambda e, p=pdf: self.open_pdf(p),
            )
            self.pdf_listview.controls.append(tile)
        self.page.update()

    def filter_pdfs(self, e):
        query = self.search_field.value.lower() if self.search_field.value else ""
        filtered = [p for p in self.pdf_files if query in p.name.lower()]
        self.refresh_pdf_list(filtered)

    def open_pdf(self, pdf_path: Path):
        try:
            if self.doc:
                self.doc.close()
                self.page_cache.clear()

            self.current_pdf = pdf_path
            self.doc = fitz.open(pdf_path)
            self.current_page_idx = 0
            self.zoom_level = 1.0

            self.path_text.value = str(pdf_path)
            self.render_page()
            self.page.update()
        except Exception as ex:
            self.show_snack(f"Error opening PDF: {ex}", ft.Colors.ERROR)

    def render_page(self):
        if not self.doc or self.current_page_idx >= len(self.doc):
            return

        try:
            page_num = self.current_page_idx
            if page_num in self.page_cache:
                img_bytes = self.page_cache[page_num]
            else:
                page = self.doc[page_num]
                matrix = fitz.Matrix(self.zoom_level, self.zoom_level)
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                img_bytes = pix.tobytes("jpeg", quality=92)
                self.page_cache[page_num] = img_bytes
                if len(self.page_cache) > 8:
                    self.page_cache.pop(next(iter(self.page_cache)), None)

            # Update the image using src_base64 (after creation)
            self.preview_image.src_base64 = base64.b64encode(img_bytes).decode()

            self.page_label.value = f"{self.current_page_idx + 1} / {len(self.doc)}"
            self.zoom_label.value = f"{int(self.zoom_level * 100)}%"

            self.page.update()
        except Exception as ex:
            self.show_snack(f"Render error: {ex}", ft.Colors.ERROR)

    def prev_page(self, e=None):
        if self.doc and self.current_page_idx > 0:
            self.current_page_idx -= 1
            self.render_page()

    def next_page(self, e=None):
        if self.doc and self.current_page_idx < len(self.doc) - 1:
            self.current_page_idx += 1
            self.render_page()

    def zoom_in(self, e=None):
        self.zoom_level = min(self.zoom_level * 1.25, 5.0)
        self.render_page()

    def zoom_out(self, e=None):
        self.zoom_level = max(self.zoom_level / 1.25, 0.3)
        self.render_page()

    def toggle_fit_mode(self, e=None):
        self.fit_mode = "page" if self.fit_mode == "width" else "width"
        self.zoom_level = 1.0
        self.render_page()

    def on_pan_start(self, e: ft.DragStartEvent):
        pass

    def on_pan_update(self, e: ft.DragUpdateEvent):
        pass

    def show_fullscreen(self, e=None):
        if not self.preview_image.src_base64:
            return
        dlg = ft.AlertDialog(
            modal=True,
            content=ft.Image(src_base64=self.preview_image.src_base64, fit=ft.BoxFit.CONTAIN),
            actions=[ft.TextButton("Close", on_click=lambda _: self.close_dialog())],
            full_screen=True,
        )
        self.page.dialog = dlg
        dlg.open = True
        self.page.update()

    def close_dialog(self):
        if self.page.dialog:
            self.page.dialog.open = False
            self.page.update()

    def search_in_current_pdf(self, e):
        if not self.current_pdf or not self.pdf_search_field.value:
            return
        query = self.pdf_search_field.value.strip().lower()
        try:
            results = []
            with pdfplumber.open(self.current_pdf) as pdf:
                for i, page in enumerate(pdf.pages):
                    text = (page.extract_text() or "").lower()
                    if query in text:
                        results.append(i)
            if results:
                self.current_page_idx = results[0]
                self.render_page()
                self.show_snack(f"Found on page {results[0]+1}", ft.Colors.GREEN)
            else:
                self.show_snack(f"'{query}' not found", ft.Colors.ORANGE)
        except Exception:
            self.show_snack("Text search failed (PDF may be image-only)", ft.Colors.ORANGE)

    def on_keyboard(self, e: ft.KeyboardEvent):
        if e.key == "ArrowLeft":
            self.prev_page()
        elif e.key == "ArrowRight":
            self.next_page()
        elif e.key in ("+", "="):
            self.zoom_in()
        elif e.key == "-":
            self.zoom_out()
        elif e.key.lower() == "f":
            self.show_fullscreen()

    def show_snack(self, message: str, color=ft.Colors.ON_SURFACE):
        self.page.show_snack_bar(
            ft.SnackBar(ft.Text(message, size=FONT_SIZE), bgcolor=color)
        )
        self.page.update()


def main(page: ft.Page):
    PDFViewer(page)


if __name__ == "__main__":
    ft.run(main, view=ft.AppView.FLET_APP)