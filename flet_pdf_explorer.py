import os
from pathlib import Path
import flet as ft
import fitz  # PyMuPDF


def main(page: ft.Page):
    page.title = "PDF Explorer (PyMuPDF)"
    page.padding = 10

    # --- Resolve AI_BOOK ---
    root_dir = os.environ.get("AI_BOOK")
    if not root_dir or not os.path.isdir(root_dir):
        page.add(ft.Text("AI_BOOK not set or invalid", color="red"))
        return

    root = Path(root_dir)

    # --- UI controls ---
    folder_label = ft.Text(f"Folder: {root}", size=16, weight="bold")
    file_list = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO)

    # Flet 0.83 requires src as a positional argument
    preview = ft.Image("", width=400, height=600, fit="contain")

    # --- Populate file list ---
    def load_files():
        file_list.controls.clear()
        for f in sorted(root.iterdir()):
            if f.is_file() and f.suffix.lower() == ".pdf":
                file_list.controls.append(
                    ft.TextButton(
                        content=ft.Text(f.name),
                        on_click=lambda e, p=f: show_preview(p),
                    )
                )
        file_list.update()

    # --- Preview PDF using PyMuPDF ---
    def show_preview(pdf_path: Path):
        try:
            doc = fitz.open(str(pdf_path))
            page0 = doc.load_page(0)

            # Render at 2x resolution for clarity
            pix = page0.get_pixmap(matrix=fitz.Matrix(2, 2))

            img_path = pdf_path.parent / f"__preview_{pdf_path.stem}.png"
            pix.save(str(img_path))

            preview.src = str(img_path)
        except Exception as e:
            preview.src = ""
            print("Preview error:", e)

        preview.update()

    # --- Layout ---
    page.add(
        folder_label,
        ft.Row(
            [
                ft.Container(file_list, width=250),
                ft.VerticalDivider(),
                preview,
            ],
            expand=True,
        ),
    )

    load_files()


ft.run(main)
