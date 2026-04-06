# flet_dispay_files.py
# flet_display_files.py
import os
import json
from pathlib import Path

import flet as ft
import fitz  # PyMuPDF


def main(page: ft.Page):
    page.title = "PDF Explorer (Offset Pan + Fit‑to‑Page + Zoom)"
    page.padding = 10
    page.horizontal_alignment = "stretch"
    page.vertical_alignment = "stretch"

    # --- Resolve AI_BOOK ---
    root_dir = os.environ.get("AI_BOOK")
    if not root_dir or not os.path.isdir(root_dir):
        page.add(ft.Text("AI_BOOK not set or invalid", color="red"))
        return

    root = Path(root_dir)
    current_folder = root

    # --- UI controls ---
    search_box = ft.TextField(
        hint_text="Search PDFs...",
        expand=True,
        text_size=18,
        on_change=lambda e: load_files(),
    )

    folder_list = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO)
    file_list = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO)

    page_label = ft.Text("Page: - / -", size=18)

    # Image with dynamic size (for true zoom)
    preview = ft.Image("", fit="none")

    # Offset pan state
    pan_x = 0.0
    pan_y = 0.0
    preview_ready = False

    # --- Offset-based pan (no absolute positioning) ---
    def pan(e):
        nonlocal preview_ready, pan_x, pan_y

        if not preview_ready:
            return
        if not e.data:
            return

        try:
            d = json.loads(e.data)
            dx = d.get("dx", 0)
            dy = d.get("dy", 0)

            # Scale movement for smooth panning
            pan_x += dx / 500
            pan_y += dy / 500

            preview.offset = ft.Offset(pan_x, pan_y)
            preview.update()

        except Exception as err:
            print("PAN ERROR:", err)

    preview_gesture = ft.GestureDetector(
        content=preview,
        on_pan_update=pan,
    )

    # No Stack needed — offset works anywhere
    preview_container = ft.Container(
        content=preview_gesture,
        expand=True,
        bgcolor=ft.Colors.BLACK_12,
    )

    zoom_level = 1.0
    current_pdf = None
    current_page = 0
    total_pages = 0

    # --- Load folders ---
    def load_folders():
        folder_list.controls.clear()

        if current_folder != root:
            folder_list.controls.append(
                ft.TextButton(".. (Up)", on_click=lambda e: navigate_up())
            )

        for f in sorted(current_folder.iterdir()):
            if f.is_dir():
                folder_list.controls.append(
                    ft.TextButton(f.name + "/", on_click=lambda e, p=f: open_folder(p))
                )

        folder_list.update()

    def open_folder(folder: Path):
        nonlocal current_folder
        current_folder = folder
        load_folders()
        load_files()

    def navigate_up():
        nonlocal current_folder
        current_folder = current_folder.parent
        load_folders()
        load_files()

    # --- Load files ---
    def load_files():
        file_list.controls.clear()
        query = (search_box.value or "").lower().strip()

        for f in sorted(current_folder.iterdir()):
            if f.is_file() and f.suffix.lower() == ".pdf":
                if query and query not in f.name.lower():
                    continue

                file_list.controls.append(
                    ft.TextButton(f.name, on_click=lambda e, p=f: open_pdf(p))
                )

        file_list.update()

    # --- Open PDF ---
    def open_pdf(pdf_path: Path):
        nonlocal current_pdf, current_page, total_pages, zoom_level
        nonlocal preview_ready, pan_x, pan_y

        try:
            preview_ready = False
            pan_x = 0.0
            pan_y = 0.0
            preview.offset = ft.Offset(0, 0)

            current_pdf = fitz.open(str(pdf_path))
            total_pages = current_pdf.page_count
            current_page = 0
            zoom_level = 1.0

            render_page()
        except Exception as e:
            print("PDF open error:", e)

    # --- Render page ---
    def render_page():
        nonlocal current_page, zoom_level, preview_ready
        nonlocal pan_x, pan_y

        preview_ready = False

        if current_pdf is None:
            return

        try:
            page_obj = current_pdf.load_page(current_page)
            mat = fitz.Matrix(zoom_level, zoom_level)
            pix = page_obj.get_pixmap(matrix=mat)

            zoom_tag = int(zoom_level * 100)
            img_path = current_folder / f"__preview_{current_page}_z{zoom_tag}.png"
            pix.save(str(img_path))

            preview.src = str(img_path)
            preview.width = pix.width
            preview.height = pix.height

            # Reset pan
            pan_x = 0.0
            pan_y = 0.0
            preview.offset = ft.Offset(0, 0)

            page_label.value = f"Page: {current_page + 1} / {total_pages}"

            preview_ready = True

        except Exception as e:
            print("Render error:", e)
            preview.src = ""
            preview_ready = False

        preview.update()
        page_label.update()

    # --- Fit to page ---
    def fit_to_page(e):
        nonlocal zoom_level, preview_ready, pan_x, pan_y

        if current_pdf is None:
            return

        preview_ready = False

        container_height = preview_container.height or page.height - 200
        pdf_height = current_pdf.load_page(current_page).rect.height

        zoom_level = container_height / pdf_height

        pan_x = 0.0
        pan_y = 0.0
        preview.offset = ft.Offset(0, 0)

        render_page()

    # --- Navigation ---
    def next_page(e):
        nonlocal current_page
        if current_pdf and current_page < total_pages - 1:
            current_page += 1
            render_page()

    def prev_page(e):
        nonlocal current_page
        if current_pdf and current_page > 0:
            current_page -= 1
            render_page()

    # --- Zoom ---
    def zoom_in(e):
        nonlocal zoom_level, preview_ready, pan_x, pan_y
        preview_ready = False
        zoom_level *= 1.25
        pan_x = 0.0
        pan_y = 0.0
        preview.offset = ft.Offset(0, 0)
        render_page()

    def zoom_out(e):
        nonlocal zoom_level, preview_ready, pan_x, pan_y
        preview_ready = False
        zoom_level /= 1.25
        pan_x = 0.0
        pan_y = 0.0
        preview.offset = ft.Offset(0, 0)
        render_page()

    # --- Layout ---
    page.add(
        ft.Row(
            [
                ft.Container(
                    ft.Column(
                        [
                            ft.Text("Folders", size=18, weight="bold"),
                            folder_list,
                            ft.Divider(),
                            search_box,
                            file_list,
                        ],
                        expand=True,
                    ),
                    width=350,
                ),
                ft.VerticalDivider(),
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.TextButton("Prev", on_click=prev_page),
                                ft.TextButton("Next", on_click=next_page),
                                ft.TextButton("Zoom +", on_click=zoom_in),
                                ft.TextButton("Zoom -", on_click=zoom_out),
                                ft.TextButton("Fit‑to‑Page", on_click=fit_to_page),
                                page_label,
                            ]
                        ),
                        preview_container,
                    ],
                    expand=True,
                ),
            ],
            expand=True,
        )
    )

    load_folders()
    load_files()


ft.run(main)
