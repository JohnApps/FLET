# flet_run.py
# https://python.plainenglish.io/i-thought-python-couldnt-do-modern-uis-then-i-found-this-library-48d6b471b932
#
import flet as ft


def main(page: ft.Page):
	page.title = "Hello, UI"
	page.add(ft.Text("This is a real UI. Built with Python."))


ft.app(target=main)