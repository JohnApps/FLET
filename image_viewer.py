# image_viewer.py
# Build by OpenCode
#build an image viewer from photos in O:\bilder using flet

"""Features:
Folder tree on the left (click folders to navigate)
Large image preview in center
Thumbnail strip at bottom
Navigate with arrow buttons or clicking thumbnails
Up button to go to parent folder
add a search button (ilike) in the left pane
Done. Search field added to left pane - searches recursively through all subdirectories for matching image names (case-insensitive). Results are limited to 100 matches, click "← Back" to return to folder view.
"""
from pathlib import Path
import flet as ft
from flet import icons as icon_module
from diskcache import Cache

Icons = icon_module.Icons

ROOT_DIR = Path("O:/bilder")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".bmp"}
CACHE = Cache(".image_cache", size_limit=1024 * 1024 * 500)


def main(page: ft.Page):
    page.title = "Image Viewer"
    page.padding = 10
    page.theme_mode = ft.ThemeMode.DARK

    current_index = [0]
    current_images = [[]]
    folder_contents = ft.Column(scroll=ft.ScrollMode.AUTO, width=250)
    thumbnails = ft.GridView(expand=True, runs_count=4, max_extent=150, spacing=10, run_spacing=10)
    preview = ft.Image(src="", fit=ft.BoxFit.CONTAIN, expand=True)
    status_text = ft.Text(size=14)
    folder_path = ft.Text(size=12, color=ft.Colors.GREY_400)
    current_file_label = ft.Text(size=12, selectable=True)
    search_field = ft.TextField(hint_text="Search...", prefix_icon=Icons.SEARCH, on_submit=lambda e: do_search(search_field.value), autofocus=False)
    search_results_mode = [False]

    def get_images(folder: Path) -> list[Path]:
        key = ("images", str(folder))
        mtime = folder.stat().st_mtime
        if key in CACHE and CACHE.get((*key, "mtime")) == mtime:
            return CACHE.get(key)
        images = []
        for f in sorted(folder.iterdir()):
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
                images.append(f)
        CACHE.set(key, images)
        CACHE.set((*key, "mtime"), mtime)
        return images

    def get_subdirs(folder: Path) -> list[Path]:
        key = ("subdirs", str(folder))
        mtime = folder.stat().st_mtime
        if key in CACHE and CACHE.get((*key, "mtime")) == mtime:
            return CACHE.get(key)
        dirs = sorted([d for d in folder.iterdir() if d.is_dir()])
        CACHE.set(key, dirs)
        CACHE.set((*key, "mtime"), mtime)
        return dirs

    def search_recursive(folder: Path, term: str) -> list[Path]:
        key = ("search", str(folder), term.lower())
        if key in CACHE:
            return CACHE.get(key)
        results = []
        term_lower = term.lower()
        for item in folder.rglob("*"):
            if item.is_file() and item.suffix.lower() in IMAGE_EXTS and term_lower in item.name.lower():
                results.append(item)
        results = sorted(results)[:100]
        CACHE.set(key, results, expire=300)
        return results

    def search_recursive(folder: Path, term: str) -> list[Path]:
        results = []
        term_lower = term.lower()
        for item in folder.rglob("*"):
            if item.is_file() and item.suffix.lower() in IMAGE_EXTS and term_lower in item.name.lower():
                results.append(item)
        return sorted(results)[:100]

    def do_search(term: str):
        if not term.strip():
            load_folder(Path(folder_path.value))
            search_results_mode[0] = False
            return
        search_results_mode[0] = True
        folder_contents.controls.clear()
        folder_contents.controls.append(ft.TextButton("← Back", on_click=lambda e: load_folder(Path(folder_path.value))))
        results = search_recursive(ROOT_DIR, term.strip())
        for img in results:
            folder_contents.controls.append(
                ft.ListTile(
                    leading=ft.Icon(Icons.IMAGE),
                    title=ft.Text(img.name, size=12),
                    subtitle=ft.Text(str(img.parent.relative_to(ROOT_DIR)), size=10, color=ft.Colors.GREY_400),
                    on_click=lambda e, p=img: show_preview(p),
                )
            )
        folder_contents.update()

    def load_folder(folder: Path):
        folder_path.value = str(folder)
        folder_path.update()
        search_results_mode[0] = False
        folder_contents.controls.clear()
        thumbnails.controls.clear()

        current_images[0] = get_images(folder)

        for d in get_subdirs(folder):
            folder_contents.controls.append(
                ft.ListTile(
                    leading=ft.Icon(Icons.FOLDER),
                    title=ft.Text(d.name),
                    on_click=lambda e, p=d: load_folder(p),
                )
            )

        for img in current_images[0]:
            try:
                thumbnails.controls.append(
                    ft.Container(
                        content=ft.Image(src=str(img), fit=ft.BoxFit.COVER, border_radius=5),
                        on_click=lambda e, p=img: show_preview(p),
                        ink=True,
                    )
                )
            except Exception:
                pass

        folder_contents.update()
        thumbnails.update()

        if current_images[0]:
            show_preview(current_images[0][0])

    def show_preview(img_path: Path):
        preview.src = str(img_path)
        idx = current_images[0].index(img_path) if img_path in current_images[0] else 0
        current_index[0] = idx
        status_text.value = f"{idx + 1} / {len(current_images[0])}"
        current_file_label.value = str(img_path)
        preview.update()
        status_text.update()
        current_file_label.update()

    def next_image(e):
        if current_images[0] and current_index[0] < len(current_images[0]) - 1:
            current_index[0] += 1
            show_preview(current_images[0][current_index[0]])

    def prev_image(e):
        if current_images[0] and current_index[0] > 0:
            current_index[0] -= 1
            show_preview(current_images[0][current_index[0]])

    def go_up(e):
        parent = ROOT_DIR if str(ROOT_DIR) == str(folder_path.value) else Path(folder_path.value).parent
        if parent.is_dir():
            load_folder(parent)

    nav_bar = ft.Row(
        [
            ft.IconButton(icon=Icons.KEYBOARD_ARROW_UP, on_click=go_up),
            ft.IconButton(icon=Icons.ARROW_BACK, on_click=prev_image),
            status_text,
            ft.IconButton(icon=Icons.ARROW_FORWARD, on_click=next_image),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
    )

    page.add(
        folder_path,
        ft.Row(
            [
                ft.Container(
                    ft.Column([search_field, folder_contents], spacing=5),
                    width=250,
                    border=ft.Border.all(1, ft.Colors.GREY_800),
                    border_radius=5,
                    padding=5,
                ),
                ft.Container(ft.Column([current_file_label, preview], spacing=5), expand=True),
            ],
            expand=True,
        ),
        ft.Container(content=thumbnails, height=180, border=ft.Border.all(1, ft.Colors.GREY_800), border_radius=5),
        nav_bar,
    )

    load_folder(ROOT_DIR)


ft.run(main)
