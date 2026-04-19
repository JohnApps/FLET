# gr_pdf_viewer.py
# V1
# V2
# V3
r"""
ca_pdf_viewer.py - PDF Viewer Application using Flet 0.84.0 and PyMuPDF
All errors are logged to flet_errors.txt
Source: H:\FLET
"""

import os
import sys
import base64
import traceback
import datetime

try:
    import fitz  # PyMuPDF
except ImportError:
    print("PyMuPDF is required. Install with: pip install PyMuPDF")
    sys.exit(1)

try:
    import flet as ft
except ImportError:
    print("Flet is required. Install with: pip install flet")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ERROR_LOG = os.path.join(SCRIPT_DIR, "flet_errors.txt")
FONT_SIZE = 16
DEFAULT_ZOOM = 1.0
ZOOM_STEP = 0.25
MIN_ZOOM = 0.25
MAX_ZOOM = 5.0
LEFT_PANE_WIDTH = 320
INITIAL_DPI = 150


# ---------------------------------------------------------------------------
# Error logging
# ---------------------------------------------------------------------------
def log_error(message: str) -> None:
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as fh:
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            fh.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# PDF helper functions
# ---------------------------------------------------------------------------
def get_pdf_directory() -> str:
    directory = os.environ.get("AI_BOOK", "")
    if not directory:
        log_error("AI_BOOK environment variable is not set.")
    elif not os.path.isdir(directory):
        log_error(f"AI_BOOK directory does not exist: {directory}")
        directory = ""
    return directory


def list_pdf_files(directory: str) -> list:
    if not directory or not os.path.isdir(directory):
        return []
    try:
        return sorted(
            f for f in os.listdir(directory)
            if f.lower().endswith(".pdf")
            and os.path.isfile(os.path.join(directory, f))
        )
    except Exception as exc:
        log_error(f"list_pdf_files: {exc}\n{traceback.format_exc()}")
        return []


def get_page_count(pdf_path: str) -> int:
    try:
        doc = fitz.open(pdf_path)
        count = len(doc)
        doc.close()
        return count
    except Exception as exc:
        log_error(f"get_page_count: {exc}\n{traceback.format_exc()}")
        return 0


def render_page(
    pdf_path: str,
    page_number: int,
    zoom: float = 1.0,
    dpi: int = INITIAL_DPI,
    fit_width: bool = False,
    fit_page: bool = False,
    container_w: int = 800,
    container_h: int = 600,
) -> str:
    """Render one PDF page to a base64-encoded PNG string."""
    try:
        doc = fitz.open(pdf_path)
        if page_number < 0 or page_number >= len(doc):
            doc.close()
            return ""

        pg = doc[page_number]

        if fit_page and container_w and container_h:
            sx = container_w / pg.rect.width
            sy = container_h / pg.rect.height
            scale = min(sx, sy) * zoom
        elif fit_width and container_w:
            scale = (container_w / pg.rect.width) * zoom
        else:
            scale = (dpi / 72.0) * zoom

        mat = fitz.Matrix(scale, scale)
        pix = pg.get_pixmap(matrix=mat, alpha=False)
        png_bytes = pix.tobytes("png")
        doc.close()
        return base64.b64encode(png_bytes).decode("ascii")
    except Exception as exc:
        log_error(f"render_page: {exc}\n{traceback.format_exc()}")
        return ""


def search_in_pdf(pdf_path: str, query: str) -> list:
    """Return list of dicts with page number and text snippets."""
    results = []
    if not query or not pdf_path:
        return results
    try:
        doc = fitz.open(pdf_path)
        lq = query.lower()
        for i in range(len(doc)):
            pg = doc[i]
            hits = pg.search_for(query)
            if hits:
                text = pg.get_text("text")
                lt = text.lower()
                snippets = []
                idx = 0
                while True:
                    idx = lt.find(lq, idx)
                    if idx == -1:
                        break
                    s = max(0, idx - 40)
                    e = min(len(text), idx + len(query) + 40)
                    snippet = text[s:e].replace("\n", " ").strip()
                    snippets.append(snippet)
                    idx += len(query)
                results.append({"page": i, "snippets": snippets[:5]})
        doc.close()
    except Exception as exc:
        log_error(f"search_in_pdf: {exc}\n{traceback.format_exc()}")
    return results


# ---------------------------------------------------------------------------
# Main Flet application
# ---------------------------------------------------------------------------
def main(page: ft.Page):
    page.title = "CA PDF Viewer"
    page.padding = 0
    page.spacing = 0
    page.window.width = 1400
    page.window.height = 900

    # -- application state --
    st = dict(
        pdf_dir=get_pdf_directory(),
        all_files=[],
        cur_file="",
        cur_path="",
        pg_num=0,
        pg_count=0,
        zoom=DEFAULT_ZOOM,
        fit="width",
        fullscreen=False,
        pan_x=0.0,
        pan_y=0.0,
        drag_sx=0.0,
        drag_sy=0.0,
    )
    st["all_files"] = list_pdf_files(st["pdf_dir"])

    # ---------------------------------------------------------------
    # Widgets – left pane
    # ---------------------------------------------------------------
    file_filter = ft.TextField(
        hint_text="Filter PDF files\u2026",
        text_size=FONT_SIZE,
        height=48,
        expand=True,
        border_radius=8,
    )
    file_listview = ft.ListView(expand=True, spacing=2, padding=10)

    # ---------------------------------------------------------------
    # Widgets – right pane
    # ---------------------------------------------------------------
    path_text = ft.Text(
        "Select a PDF from the list",
        size=FONT_SIZE,
        weight=ft.FontWeight.BOLD,
        selectable=True,
        max_lines=2,
        expand=True,
    )
    info_text = ft.Text("Page: 0 / 0", size=FONT_SIZE)

    # Use a simple string for fit instead of an enum
    pdf_image = ft.Image(
        src_base64="",
        fit="contain",
        expand=True,
    )

    img_stack = ft.Stack(
        controls=[pdf_image],
        expand=True,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )

    gesture = ft.GestureDetector(
        content=img_stack,
        expand=True,
        drag_interval=30,
    )

    pdf_search = ft.TextField(
        hint_text="Search in PDF\u2026",
        text_size=FONT_SIZE,
        height=48,
        expand=True,
        border_radius=8,
    )

    search_list = ft.ListView(visible=False, height=0, spacing=2, padding=5)

    # ---------------------------------------------------------------
    # Refresh the rendered page
    # ---------------------------------------------------------------
    def refresh():
        if not st["cur_path"]:
            pdf_image.src_base64 = ""
            info_text.value = "Page: 0 / 0"
            page.update()
            return

        cw = max(400, int(page.window.width or 1000) - LEFT_PANE_WIDTH - 80)
        ch = max(300, int(page.window.height or 800) - 220)

        b64 = render_page(
            pdf_path=st["cur_path"],
            page_number=st["pg_num"],
            zoom=st["zoom"],
            fit_width=(st["fit"] == "width"),
            fit_page=(st["fit"] == "page"),
            container_w=cw,
            container_h=ch,
        )
        pdf_image.src_base64 = b64

        # apply pan offset
        pdf_image.left = st["pan_x"]
        pdf_image.top = st["pan_y"]

        info_text.value = (
            f"Page {st['pg_num'] + 1} / {st['pg_count']}  |  "
            f"Zoom {int(st['zoom'] * 100)}%"
        )
        page.update()

    # ---------------------------------------------------------------
    # Build file list
    # ---------------------------------------------------------------
    def build_list(filt=""):
        file_listview.controls.clear()
        lf = filt.lower()
        for fn in st["all_files"]:
            if lf and lf not in fn.lower():
                continue
            file_listview.controls.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.PICTURE_AS_PDF, color=ft.Colors.RED_700),
                    title=ft.Text(fn, size=FONT_SIZE - 2, max_lines=1),
                    on_click=lambda e, name=fn: select_file(name),
                    dense=True,
                )
            )
        page.update()

    # ---------------------------------------------------------------
    # Event handlers
    # ---------------------------------------------------------------
    def select_file(name):
        try:
            st["cur_file"] = name
            st["cur_path"] = os.path.join(st["pdf_dir"], name)
            st["pg_num"] = 0
            st["zoom"] = DEFAULT_ZOOM
            st["pan_x"] = 0.0
            st["pan_y"] = 0.0
            st["pg_count"] = get_page_count(st["cur_path"])
            path_text.value = st["cur_path"]
            search_list.visible = False
            search_list.height = 0
            refresh()
        except Exception as exc:
            log_error(f"select_file: {exc}\n{traceback.format_exc()}")

    def on_filter(e):
        build_list(file_filter.value or "")

    def prev_page(e):
        if st["pg_num"] > 0:
            st["pg_num"] -= 1
            st["pan_x"] = 0.0
            st["pan_y"] = 0.0
            refresh()

    def next_page(e):
        if st["pg_num"] < st["pg_count"] - 1:
            st["pg_num"] += 1
            st["pan_x"] = 0.0
            st["pan_y"] = 0.0
            refresh()

    def zoom_in(e):
        if st["zoom"] < MAX_ZOOM:
            st["zoom"] = round(st["zoom"] + ZOOM_STEP, 2)
            refresh()

    def zoom_out(e):
        if st["zoom"] > MIN_ZOOM:
            st["zoom"] = round(st["zoom"] - ZOOM_STEP, 2)
            refresh()

    def fit_width(e):
        st["fit"] = "width"
        st["pan_x"] = 0.0
        st["pan_y"] = 0.0
        refresh()

    def fit_page(e):
        st["fit"] = "page"
        st["pan_x"] = 0.0
        st["pan_y"] = 0.0
        refresh()

    def toggle_fs(e):
        st["fullscreen"] = not st["fullscreen"]
        page.window.full_screen = st["fullscreen"]
        page.update()
        refresh()

    # pan
    def pan_start(e: ft.DragStartEvent):
        st["drag_sx"] = st["pan_x"]
        st["drag_sy"] = st["pan_y"]

    def pan_update(e: ft.DragUpdateEvent):
        st["pan_x"] = st["drag_sx"] + e.delta_x
        st["pan_y"] = st["drag_sy"] + e.delta_y
        pdf_image.left = st["pan_x"]
        pdf_image.top = st["pan_y"]
        page.update()

    gesture.on_pan_start = pan_start
    gesture.on_pan_update = pan_update
    gesture.on_double_tap = toggle_fs

    # search inside pdf
    def do_pdf_search(e):
        q = (pdf_search.value or "").strip()
        if not q or not st["cur_path"]:
            search_list.visible = False
            search_list.height = 0
            page.update()
            return
        hits = search_in_pdf(st["cur_path"], q)
        search_list.controls.clear()
        if not hits:
            search_list.controls.append(
                ft.Text("No results found.", size=FONT_SIZE - 2, italic=True)
            )
        else:
            for h in hits:
                pn = h["page"]
                for snip in h["snippets"]:
                    search_list.controls.append(
                        ft.ListTile(
                            title=ft.Text(
                                f"Page {pn + 1}: \u2026{snip}\u2026",
                                size=FONT_SIZE - 3,
                                max_lines=2,
                            ),
                            on_click=lambda ev, p=pn: goto_page(p),
                            dense=True,
                        )
                    )
        search_list.visible = True
        search_list.height = min(220, max(60, len(search_list.controls) * 46))
        page.update()

    def goto_page(p):
        st["pg_num"] = p
        st["pan_x"] = 0.0
        st["pan_y"] = 0.0
        refresh()

    file_filter.on_change = on_filter
    pdf_search.on_submit = do_pdf_search

    # ---------------------------------------------------------------
    # Toolbar
    # ---------------------------------------------------------------
    toolbar = ft.Row(
        controls=[
            ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Previous", on_click=prev_page, icon_size=24),
            ft.IconButton(ft.Icons.ARROW_FORWARD, tooltip="Next", on_click=next_page, icon_size=24),
            ft.VerticalDivider(width=1),
            ft.IconButton(ft.Icons.ZOOM_OUT, tooltip="Zoom Out", on_click=zoom_out, icon_size=24),
            ft.IconButton(ft.Icons.ZOOM_IN, tooltip="Zoom In", on_click=zoom_in, icon_size=24),
            ft.VerticalDivider(width=1),
            ft.TextButton("Fit Width", on_click=fit_width),
            ft.TextButton("Fit Page", on_click=fit_page),
            ft.VerticalDivider(width=1),
            ft.IconButton(ft.Icons.FULLSCREEN, tooltip="Fullscreen", on_click=toggle_fs, icon_size=24),
            ft.VerticalDivider(width=1),
            info_text,
        ],
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    # ---------------------------------------------------------------
    # Layout
    # ---------------------------------------------------------------
    left_pane = ft.Container(
        width=LEFT_PANE_WIDTH,
        bgcolor=ft.Colors.GREY_100,
        border=ft.border.only(right=ft.BorderSide(1, ft.Colors.GREY_400)),
        padding=10,
        content=ft.Column(
            [
                ft.Text("PDF Files", size=FONT_SIZE + 2, weight=ft.FontWeight.BOLD),
                ft.Text(
                    st["pdf_dir"] if st["pdf_dir"] else "Set AI_BOOK env variable!",
                    size=FONT_SIZE - 4,
                    italic=True,
                    color=ft.Colors.GREY_600,
                    max_lines=2,
                ),
                ft.Row([file_filter]),
                ft.Divider(height=1),
                file_listview,
            ],
            spacing=6,
            expand=True,
        ),
    )

    right_pane = ft.Container(
        expand=True,
        padding=10,
        content=ft.Column(
            [
                path_text,
                ft.Divider(height=1),
                toolbar,
                ft.Row([pdf_search, ft.IconButton(ft.Icons.SEARCH, on_click=do_pdf_search, icon_size=24)], spacing=4),
                search_list,
                ft.Divider(height=1),
                gesture,
            ],
            spacing=6,
            expand=True,
        ),
    )

    page.add(
        ft.Row(
            [left_pane, right_pane],
            expand=True,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    )

    build_list()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        ft.run(main)
    except Exception as exc:
        log_error(f"Startup error: {exc}\n{traceback.format_exc()}")
        print(f"Fatal error. See {ERROR_LOG}")
        sys.exit(1)