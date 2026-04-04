# Updated ca_pdf_viewer_app.py with working zoom buttons and mouse wheel

import os
from pathlib import Path
import flet as ft
import fitz  # PyMuPDF
import base64

PDF_DIR = Path(os.environ.get("AI_BOOK", "."))
FONT_SIZE = 16

class PDFApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "CA PDF Viewer (PyMuPDF)"
        self.page.window_maximized = True

        self.doc = None
        self.page_index = 0
        self.zoom = 1.0

        # UI
        self.search_field = ft.TextField(label="Search PDFs", on_change=self.search)
        self.file_list = ft.ListView(expand=True)

        self.image = ft.Image(src="", expand=True, fit="contain")

        self.path_text = ft.Text("", size=FONT_SIZE)

        # Controls
        self.prev_btn = ft.IconButton(ft.Icons.ARROW_BACK, on_click=self.prev_page)
        self.next_btn = ft.IconButton(ft.Icons.ARROW_FORWARD, on_click=self.next_page)
        self.zoom_in_btn = ft.IconButton(ft.Icons.ZOOM_IN, on_click=lambda e: self.adjust_zoom(1.25))
        self.zoom_out_btn = ft.IconButton(ft.Icons.ZOOM_OUT, on_click=lambda e: self.adjust_zoom(1/1.25))

        self.controls_row = ft.Row([
            self.prev_btn,
            self.next_btn,
            self.zoom_out_btn,
            self.zoom_in_btn
        ])

        # Enable mouse wheel zoom
        self.page.on_scroll = self.on_scroll

        self.current_files = []
        self.load_files()

        layout = ft.Row([
            ft.Container(
                content=ft.Column([
                    self.search_field,
                    self.file_list
                ]),
                width=300
            ),
            ft.VerticalDivider(),
            ft.Column([
                self.path_text,
                self.controls_row,
                self.image
            ], expand=True)
        ], expand=True)

        self.page.add(layout)

    # ---------- File handling ----------
    def load_files(self):
        self.current_files = list(PDF_DIR.glob("*.pdf"))
        self.refresh_list()

    def refresh_list(self):
        self.file_list.controls.clear()
        for i, f in enumerate(self.current_files):
            self.file_list.controls.append(
                ft.TextButton(f.name, on_click=lambda e, idx=i: self.open_file(idx))
            )
        self.page.update()

    def search(self, e):
        query = self.search_field.value.lower()
        self.current_files = [
            f for f in PDF_DIR.glob("*.pdf") if query in f.name.lower()
        ]
        self.refresh_list()

    def open_file(self, idx):
        path = self.current_files[idx]
        self.doc = fitz.open(path)
        self.page_index = 0
        self.zoom = 1.0
        self.path_text.value = str(path.resolve())
        self.render_page()

    # ---------- Rendering ----------
    def render_page(self):
        if not self.doc:
            return

        page = self.doc[self.page_index]
        mat = fitz.Matrix(self.zoom, self.zoom)
        pix = page.get_pixmap(matrix=mat)

        img_bytes = pix.tobytes("png")
        b64 = base64.b64encode(img_bytes).decode("utf-8")

        # Force refresh
        self.image.src = None
        self.page.update()

        self.image.src = f"data:image/png;base64,{b64}"
        self.page.update()

    # ---------- Controls ----------
    def adjust_zoom(self, factor):
        if self.doc:
            self.zoom *= factor
            self.zoom = max(0.2, min(self.zoom, 5.0))
            self.render_page()

    def next_page(self, e):
        if self.doc and self.page_index < len(self.doc) - 1:
            self.page_index += 1
            self.render_page()

    def prev_page(self, e):
        if self.doc and self.page_index > 0:
            self.page_index -= 1
            self.render_page()

    # ---------- Mouse wheel zoom ----------
    def on_scroll(self, e: ft.OnScrollEvent):
        if not self.doc:
            return

        if e.scroll_delta_y > 0:
            self.adjust_zoom(0.9)
        else:
            self.adjust_zoom(1.1)


def main(page: ft.Page):
    PDFApp(page)


if __name__ == "__main__":
    ft.run(main)