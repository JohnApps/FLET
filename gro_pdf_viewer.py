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
# V16 - base64 not known
# V17 - 'simple' version to comply with flet 0.84
# gro_pdf_viewer.py - Minimal working version for Flet 0.84.0
import flet as ft
import os
import base64
from pathlib import Path
import fitz  # PyMuPDF

FONT_SIZE = 16

class PDFViewer:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "gro_pdf_viewer"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.window_min_width = 1000
        self.page.window_min_height = 600

        self.pdf_dir = Path(os.getenv("AI_BOOK", os.getcwd()))
        self.current_doc = None
        self.current_page = 0

        self.build_ui()
        self.load_pdfs()

    def build_ui(self):
        self.pdf_list = ft.ListView(expand=True, spacing=5)

        self.preview = ft.Image(
            src="", 
            fit=ft.BoxFit.CONTAIN, 
            expand=True,
            border_radius=5
        )

        self.status = ft.Text("No PDF selected", size=FONT_SIZE)

        left = ft.Container(
            content=ft.Column([
                ft.Text("PDF Files", size=FONT_SIZE+2, weight=ft.FontWeight.BOLD),
                self.pdf_list
            ], expand=True),
            width=300,
            padding=10,
            border=ft.border.only(right=ft.BorderSide(1, ft.Colors.OUTLINE))
        )

        right = ft.Column([
            self.status,
            ft.Row([
                ft.IconButton(ft.Icons.ARROW_LEFT, on_click=self.prev_page),
                ft.Text("Page", size=FONT_SIZE),
                self.page_text := ft.Text("0/0", size=FONT_SIZE),
                ft.IconButton(ft.Icons.ARROW_RIGHT, on_click=self.next_page),
                ft.IconButton(ft.Icons.ZOOM_OUT, on_click=self.zoom_out),
                ft.IconButton(ft.Icons.ZOOM_IN, on_click=self.zoom_in),
            ], alignment=ft.MainAxisAlignment.CENTER),
            self.preview,
        ], expand=True, spacing=10)

        self.page.add(ft.Row([left, right], expand=True, spacing=0))

    def load_pdfs(self):
        self.pdf_list.controls.clear()
        for pdf in sorted(self.pdf_dir.rglob("*.pdf")):
            self.pdf_list.controls.append(
                ft.ListTile(
                    title=ft.Text(pdf.name, size=FONT_SIZE),
                    on_click=lambda e, p=pdf: self.load_selected_pdf(p)
                )
            )
        self.page.update()

    def load_selected_pdf(self, path: Path):
        try:
            if self.current_doc:
                self.current_doc.close()
            self.current_doc = fitz.open(path)
            self.current_page = 0
            self.status.value = str(path)
            self.render_current_page()
            self.page.update()
        except Exception as e:
            self.status.value = f"Error: {e}"
            self.page.update()

    def render_current_page(self):
        if not self.current_doc:
            return
        try:
            page = self.current_doc[self.current_page]
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))  # reasonable zoom
            img_bytes = pix.tobytes("jpeg", quality=85)

            b64 = base64.b64encode(img_bytes).decode("utf-8")
            self.preview.src = b64
            self.preview.update()

            self.page_text.value = f"{self.current_page + 1} / {len(self.current_doc)}"
            self.page.update()
        except Exception as e:
            self.status.value = f"Render error: {e}"
            self.page.update()

    def prev_page(self, e):
        if self.current_doc and self.current_page > 0:
            self.current_page -= 1
            self.render_current_page()

    def next_page(self, e):
        if self.current_doc and self.current_page < len(self.current_doc) - 1:
            self.current_page += 1
            self.render_current_page()

    def zoom_in(self, e):
        self.status.value = "Zoom not implemented in minimal version"
        self.page.update()

    def zoom_out(self, e):
        self.status.value = "Zoom not implemented in minimal version"
        self.page.update()


def main(page: ft.Page):
    PDFViewer(page)


if __name__ == "__main__":
    ft.run(main, view=ft.AppView.FLET_APP)