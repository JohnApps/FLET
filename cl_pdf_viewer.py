# cl_pdf_viewer.py
#!/usr/bin/env python3
"""
PDF Viewer Application using Flet
Author: Claude (Anthropic)
Target: Windows 11, Python 3.14.3
Location: H:\\FLET\\cl_pdf_viewer.py

Features:
- Browse PDF files from AI_BOOK environment variable directory
- Preview PDFs with page navigation (next/previous)
- Zoom controls (+/-)
- Page width and full page viewing modes
- Search within PDF files list
- Search within displayed PDF content
- Full-screen view on click
- Display PDF path at top of viewer
"""

import flet as ft
import fitz  # PyMuPDF
import os
import base64
from pathlib import Path
from typing import Optional, List
import re


class PDFDocument:
    """Handles PDF document operations using PyMuPDF."""
    
    def __init__(self, path: str):
        self.path = path
        self.doc: Optional[fitz.Document] = None
        self.current_page = 0
        self.total_pages = 0
        self.zoom_level = 1.0
        self.fit_mode = "width"  # "width" or "page"
        self.text_cache: dict[int, str] = {}
        
    def open(self) -> bool:
        """Open the PDF document."""
        try:
            self.doc = fitz.open(self.path)
            self.total_pages = len(self.doc)
            self.current_page = 0
            self.text_cache.clear()
            return True
        except Exception as e:
            print(f"Error opening PDF: {e}")
            return False
    
    def close(self):
        """Close the document."""
        if self.doc:
            self.doc.close()
            self.doc = None
            self.text_cache.clear()
    
    def get_page_image(self, page_num: int, container_width: int, container_height: int) -> Optional[str]:
        """Render a page to a base64 image string."""
        if not self.doc or page_num < 0 or page_num >= self.total_pages:
            return None
        
        try:
            page = self.doc[page_num]
            
            # Calculate zoom based on fit mode and container size
            page_rect = page.rect
            page_width = page_rect.width
            page_height = page_rect.height
            
            if self.fit_mode == "width":
                # Fit to container width
                base_zoom = (container_width - 40) / page_width if page_width > 0 else 1.0
            else:  # "page" - fit entire page
                width_zoom = (container_width - 40) / page_width if page_width > 0 else 1.0
                height_zoom = (container_height - 40) / page_height if page_height > 0 else 1.0
                base_zoom = min(width_zoom, height_zoom)
            
            # Apply user zoom level
            final_zoom = base_zoom * self.zoom_level
            
            # Clamp zoom to reasonable limits
            final_zoom = max(0.1, min(final_zoom, 5.0))
            
            # Create transformation matrix
            mat = fitz.Matrix(final_zoom, final_zoom)
            
            # Render page to pixmap
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            # Convert to PNG bytes
            png_bytes = pix.tobytes("png")
            
            # Encode to base64
            return base64.b64encode(png_bytes).decode('utf-8')
            
        except Exception as e:
            print(f"Error rendering page {page_num}: {e}")
            return None
    
    def get_page_text(self, page_num: int) -> str:
        """Extract text from a page (cached)."""
        if not self.doc or page_num < 0 or page_num >= self.total_pages:
            return ""
        
        if page_num not in self.text_cache:
            try:
                page = self.doc[page_num]
                self.text_cache[page_num] = page.get_text()
            except Exception:
                self.text_cache[page_num] = ""
        
        return self.text_cache[page_num]
    
    def search_in_document(self, query: str) -> List[tuple[int, str]]:
        """Search for text in all pages. Returns list of (page_num, context)."""
        if not self.doc or not query:
            return []
        
        results = []
        query_lower = query.lower()
        
        for page_num in range(self.total_pages):
            text = self.get_page_text(page_num)
            if query_lower in text.lower():
                # Find context around the match
                idx = text.lower().find(query_lower)
                start = max(0, idx - 30)
                end = min(len(text), idx + len(query) + 30)
                context = "..." + text[start:end].replace('\n', ' ') + "..."
                results.append((page_num, context))
        
        return results


class PDFViewerApp:
    """Main PDF Viewer Application."""
    
    def __init__(self):
        self.pdf_directory = os.environ.get('AI_BOOK', os.getcwd())
        self.pdf_files: List[Path] = []
        self.filtered_files: List[Path] = []
        self.current_pdf: Optional[PDFDocument] = None
        self.is_fullscreen = False
        
        # UI References
        self.page: Optional[ft.Page] = None
        self.file_list: Optional[ft.ListView] = None
        self.pdf_image: Optional[ft.Image] = None
        self.path_text: Optional[ft.Text] = None
        self.page_info: Optional[ft.Text] = None
        self.search_field: Optional[ft.TextField] = None
        self.pdf_search_field: Optional[ft.TextField] = None
        self.search_results: Optional[ft.ListView] = None
        self.main_container: Optional[ft.Container] = None
        self.pdf_container: Optional[ft.Container] = None
        
    def scan_pdf_files(self):
        """Scan the directory for PDF files."""
        self.pdf_files = []
        try:
            pdf_path = Path(self.pdf_directory)
            if pdf_path.exists():
                # Recursively find all PDFs
                self.pdf_files = sorted(pdf_path.rglob("*.pdf"))
            self.filtered_files = self.pdf_files.copy()
        except Exception as e:
            print(f"Error scanning directory: {e}")
    
    def filter_files(self, query: str):
        """Filter PDF files based on search query."""
        if not query:
            self.filtered_files = self.pdf_files.copy()
        else:
            query_lower = query.lower()
            self.filtered_files = [
                f for f in self.pdf_files 
                if query_lower in f.name.lower()
            ]
        self.update_file_list(update_ui=True)
    
    def update_file_list(self, update_ui: bool = True):
        """Update the file list UI."""
        if not self.file_list:
            return
        
        self.file_list.controls.clear()
        
        for pdf_path in self.filtered_files:
            # Create a clickable list tile for each PDF
            tile = ft.ListTile(
                leading=ft.Icon(ft.Icons.PICTURE_AS_PDF, color=ft.Colors.RED_400),
                title=ft.Text(
                    pdf_path.name, 
                    size=14,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS
                ),
                subtitle=ft.Text(
                    str(pdf_path.parent.name),
                    size=11,
                    color=ft.Colors.GREY_500
                ),
                on_click=lambda e, p=pdf_path: self.open_pdf(p),
                dense=True,
            )
            self.file_list.controls.append(tile)
        
        # Only call update() if the control is already on the page
        if update_ui and self.page and self.file_list.page:
            self.file_list.update()
    
    def open_pdf(self, pdf_path: Path):
        """Open a PDF file for viewing."""
        # Close previous document
        if self.current_pdf:
            self.current_pdf.close()
        
        # Create new document
        self.current_pdf = PDFDocument(str(pdf_path))
        
        if self.current_pdf.open():
            self.path_text.value = str(pdf_path)
            self.render_current_page()
            self.clear_search_results()
        else:
            self.path_text.value = f"Error opening: {pdf_path.name}"
            self.pdf_image.src = ""
        
        if self.page:
            self.page.update()
    
    def render_current_page(self):
        """Render the current page of the PDF."""
        if not self.current_pdf or not self.current_pdf.doc:
            return
        
        # Get container dimensions - use reasonable defaults
        container_width = 900
        container_height = 700
        
        # Render page
        img_base64 = self.current_pdf.get_page_image(
            self.current_pdf.current_page,
            container_width,
            container_height
        )
        
        if img_base64:
            # Use data URI format for base64 images in Flet 0.83+
            self.pdf_image.src = f"data:image/png;base64,{img_base64}"
            
            # Calculate displayed image size based on zoom and fit mode
            page = self.current_pdf.doc[self.current_pdf.current_page]
            page_rect = page.rect
            
            if self.current_pdf.fit_mode == "width":
                base_zoom = (container_width - 40) / page_rect.width
            else:
                width_zoom = (container_width - 40) / page_rect.width
                height_zoom = (container_height - 40) / page_rect.height
                base_zoom = min(width_zoom, height_zoom)
            
            final_zoom = base_zoom * self.current_pdf.zoom_level
            final_zoom = max(0.1, min(final_zoom, 5.0))
            
            # Set image dimensions
            self.pdf_image.width = int(page_rect.width * final_zoom)
            self.pdf_image.height = int(page_rect.height * final_zoom)
        
        # Update page info
        self.page_info.value = f"Page {self.current_pdf.current_page + 1} of {self.current_pdf.total_pages}"
        
        if self.page and self.pdf_image.page:
            self.pdf_image.update()
            self.page_info.update()
    
    def next_page(self, e):
        """Go to next page."""
        if self.current_pdf and self.current_pdf.current_page < self.current_pdf.total_pages - 1:
            self.current_pdf.current_page += 1
            self.render_current_page()
    
    def prev_page(self, e):
        """Go to previous page."""
        if self.current_pdf and self.current_pdf.current_page > 0:
            self.current_pdf.current_page -= 1
            self.render_current_page()
    
    def zoom_in(self, e):
        """Zoom in."""
        if self.current_pdf:
            self.current_pdf.zoom_level = min(5.0, self.current_pdf.zoom_level + 0.25)
            self.render_current_page()
    
    def zoom_out(self, e):
        """Zoom out."""
        if self.current_pdf:
            self.current_pdf.zoom_level = max(0.25, self.current_pdf.zoom_level - 0.25)
            self.render_current_page()
    
    def set_fit_width(self, e):
        """Set fit to width mode."""
        if self.current_pdf:
            self.current_pdf.fit_mode = "width"
            self.current_pdf.zoom_level = 1.0
            self.render_current_page()
    
    def set_fit_page(self, e):
        """Set fit to page mode."""
        if self.current_pdf:
            self.current_pdf.fit_mode = "page"
            self.current_pdf.zoom_level = 1.0
            self.render_current_page()
    
    def toggle_fullscreen(self, e):
        """Toggle fullscreen mode."""
        if self.page:
            self.is_fullscreen = not self.is_fullscreen
            self.page.window.full_screen = self.is_fullscreen
            self.page.update()
    
    def on_file_search(self, e):
        """Handle file search input."""
        self.filter_files(e.control.value)
    
    def on_pdf_search(self, e):
        """Handle PDF content search."""
        if not self.current_pdf:
            return
        
        query = e.control.value
        if not query:
            self.clear_search_results()
            return
        
        results = self.current_pdf.search_in_document(query)
        self.display_search_results(results)
    
    def display_search_results(self, results: List[tuple[int, str]]):
        """Display search results."""
        if not self.search_results:
            return
        
        self.search_results.controls.clear()
        
        if not results:
            self.search_results.controls.append(
                ft.Text("No results found", size=14, color=ft.Colors.GREY_500)
            )
        else:
            for page_num, context in results:
                result_tile = ft.ListTile(
                    leading=ft.Text(f"P{page_num + 1}", size=12, weight=ft.FontWeight.BOLD),
                    title=ft.Text(context, size=12, max_lines=2),
                    on_click=lambda e, pn=page_num: self.go_to_page(pn),
                    dense=True,
                )
                self.search_results.controls.append(result_tile)
        
        self.search_results.visible = True
        if self.page and self.search_results.page:
            self.search_results.update()
    
    def clear_search_results(self):
        """Clear search results."""
        if self.search_results:
            self.search_results.controls.clear()
            self.search_results.visible = False
            if self.page and self.search_results.page:
                self.search_results.update()
    
    def go_to_page(self, page_num: int):
        """Navigate to a specific page."""
        if self.current_pdf and 0 <= page_num < self.current_pdf.total_pages:
            self.current_pdf.current_page = page_num
            self.render_current_page()
    
    def on_keyboard(self, e: ft.KeyboardEvent):
        """Handle keyboard shortcuts."""
        if e.key == "Escape" and self.is_fullscreen:
            self.toggle_fullscreen(None)
        elif e.key == "Arrow Right" or e.key == "Page Down":
            self.next_page(None)
        elif e.key == "Arrow Left" or e.key == "Page Up":
            self.prev_page(None)
        elif e.key == "+" or e.key == "=":
            self.zoom_in(None)
        elif e.key == "-":
            self.zoom_out(None)
        elif e.key == "F11":
            self.toggle_fullscreen(None)
    
    def build_ui(self, page: ft.Page):
        """Build the main UI."""
        self.page = page
        
        # Configure page
        page.title = "PDF Viewer"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.padding = 0
        page.window.width = 1400
        page.window.height = 900
        page.on_keyboard_event = self.on_keyboard
        
        # Scan for PDF files
        self.scan_pdf_files()
        
        # Left pane: File browser
        self.search_field = ft.TextField(
            hint_text="Search PDF files...",
            prefix_icon=ft.Icons.SEARCH,
            on_change=self.on_file_search,
            text_size=16,
            border_radius=8,
        )
        
        self.file_list = ft.ListView(
            expand=True,
            spacing=2,
            padding=10,
        )
        # Populate the file list controls before adding to page (no UI update yet)
        self.update_file_list(update_ui=False)
        
        left_pane = ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Text(
                        f"PDF Library ({len(self.pdf_files)} files)",
                        size=16,
                        weight=ft.FontWeight.BOLD
                    ),
                    padding=10,
                ),
                ft.Container(
                    content=self.search_field,
                    padding=ft.Padding.only(left=10, right=10, bottom=10),
                ),
                ft.Divider(height=1),
                self.file_list,
            ]),
            width=320,
            bgcolor=ft.Colors.GREY_100,
            border=ft.Border.only(right=ft.BorderSide(1, ft.Colors.GREY_300)),
        )
        
        # Right pane: PDF viewer
        self.path_text = ft.Text(
            "Select a PDF file to view",
            size=14,
            color=ft.Colors.GREY_700,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        
        self.page_info = ft.Text(
            "",
            size=14,
            weight=ft.FontWeight.BOLD,
        )
        
        # Navigation controls
        nav_controls = ft.Row([
            ft.IconButton(
                icon=ft.Icons.ARROW_BACK,
                tooltip="Previous Page (←)",
                on_click=self.prev_page,
            ),
            self.page_info,
            ft.IconButton(
                icon=ft.Icons.ARROW_FORWARD,
                tooltip="Next Page (→)",
                on_click=self.next_page,
            ),
            ft.VerticalDivider(width=20),
            ft.IconButton(
                icon=ft.Icons.ZOOM_OUT,
                tooltip="Zoom Out (-)",
                on_click=self.zoom_out,
            ),
            ft.IconButton(
                icon=ft.Icons.ZOOM_IN,
                tooltip="Zoom In (+)",
                on_click=self.zoom_in,
            ),
            ft.VerticalDivider(width=20),
            ft.TextButton(
                "Fit Width",
                on_click=self.set_fit_width,
            ),
            ft.TextButton(
                "Fit Page",
                on_click=self.set_fit_page,
            ),
            ft.VerticalDivider(width=20),
            ft.IconButton(
                icon=ft.Icons.FULLSCREEN,
                tooltip="Fullscreen (F11)",
                on_click=self.toggle_fullscreen,
            ),
        ], alignment=ft.MainAxisAlignment.CENTER)
        
        # PDF search
        self.pdf_search_field = ft.TextField(
            hint_text="Search in PDF...",
            prefix_icon=ft.Icons.SEARCH,
            on_submit=self.on_pdf_search,
            text_size=14,
            width=300,
            border_radius=8,
            dense=True,
        )
        
        self.search_results = ft.ListView(
            visible=False,
            height=150,
            spacing=2,
        )
        
        # PDF image display - needs explicit dimensions to render
        self.pdf_image = ft.Image(
            src="",
            fit="contain",
            width=800,
            height=600,
        )
        
        # Scrollable container for the PDF image
        self.pdf_scroll = ft.Column(
            controls=[self.pdf_image],
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )
        
        self.pdf_container = ft.Container(
            content=self.pdf_scroll,
            expand=True,
            bgcolor=ft.Colors.GREY_200,
            on_click=self.toggle_fullscreen,
        )
        
        # Header with path and search
        header = ft.Container(
            content=ft.Row([
                ft.Container(
                    content=self.path_text,
                    expand=True,
                ),
                self.pdf_search_field,
            ]),
            padding=10,
            bgcolor=ft.Colors.WHITE,
            border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.GREY_300)),
        )
        
        right_pane = ft.Column([
            header,
            self.search_results,
            nav_controls,
            ft.Divider(height=1),
            self.pdf_container,
        ], expand=True, spacing=0)
        
        # Main layout
        self.main_container = ft.Row([
            left_pane,
            ft.Container(
                content=right_pane,
                expand=True,
            ),
        ], expand=True, spacing=0)
        
        page.add(self.main_container)
        
        # Show directory info
        page.snack_bar = ft.SnackBar(
            content=ft.Text(f"PDF Directory: {self.pdf_directory}"),
            action="OK",
        )
        page.snack_bar.open = True
        page.update()


def main(page: ft.Page):
    """Application entry point."""
    app = PDFViewerApp()
    app.build_ui(page)


if __name__ == "__main__":
    ft.run(main)