from dataclasses import dataclass
from typing import Final

import flet as ft


@dataclass
class Message:
    user_name: str
    text: str
    message_type: str


_AVATAR_COLORS: Final[list[str]] = [
    ft.Colors.AMBER,
    ft.Colors.BLUE,
    ft.Colors.BROWN,
    ft.Colors.CYAN,
    ft.Colors.GREEN,
    ft.Colors.INDIGO,
    ft.Colors.LIME,
    ft.Colors.ORANGE,
    ft.Colors.PINK,
    ft.Colors.PURPLE,
    ft.Colors.RED,
    ft.Colors.TEAL,
    ft.Colors.YELLOW,
]


@ft.control
class ChatMessage(ft.Row):
    def __init__(self, message: Message) -> None:
        super().__init__()
        self.message = message
        self.vertical_alignment = ft.CrossAxisAlignment.START
        self.controls = [
            ft.CircleAvatar(
                content=ft.Text(self.get_initials(message.user_name)),
                color=ft.Colors.WHITE,
                bgcolor=self.get_avatar_color(message.user_name),
            ),
            ft.Column(
                tight=True,
                spacing=5,
                controls=[
                    ft.Text(message.user_name, weight=ft.FontWeight.BOLD),
                    ft.Text(message.text, selectable=True),
                ],
            ),
        ]

    @staticmethod
    def get_initials(user_name: str) -> str:
        if not user_name:
            return "?"
        return "".join(word[0] for word in user_name.split()[:2]).upper()

    @staticmethod
    def get_avatar_color(user_name: str) -> str:
        return _AVATAR_COLORS[abs(hash(user_name)) % len(_AVATAR_COLORS)]


def main(page: ft.Page) -> None:
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.title = "Flet Chat"

    def join_chat_click(e: ft.ControlEvent) -> None:
        if not join_user_name.value:
            join_user_name.error_text = "Name cannot be blank!"
            join_user_name.update()
        else:
            page.session.store.set("user_name", join_user_name.value)
            welcome_dlg.open = False
            new_message.prefix = ft.Text(f"{join_user_name.value}: ")
            page.pubsub.send_all(
                Message(
                    user_name=join_user_name.value,
                    text=f"{join_user_name.value} has joined the chat.",
                    message_type="login_message",
                )
            )

    async def send_message_click(e: ft.ControlEvent) -> None:
        if new_message.value:
            page.pubsub.send_all(
                Message(
                    page.session.store.get("user_name"),
                    new_message.value,
                    message_type="chat_message",
                )
            )
            new_message.value = ""
            await new_message.focus_async()

    async def on_message(message: Message) -> None:
        if message.message_type == "chat_message":
            chat.controls.append(ChatMessage(message))
        elif message.message_type == "login_message":
            chat.controls.append(
                ft.Text(message.text, italic=True, color=ft.Colors.BLACK_45, size=12)
            )
        await page.update_async()

    page.pubsub.subscribe(on_message)

    join_user_name = ft.TextField(
        label="Enter your name to join the chat",
        autofocus=True,
        on_submit=join_chat_click,
    )
    welcome_dlg = ft.AlertDialog(
        open=True,
        modal=True,
        title=ft.Text("Welcome!"),
        content=ft.Column([join_user_name], width=300, height=70, tight=True),
        actions=[ft.Button(content="Join chat", on_click=join_chat_click)],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.overlay.append(welcome_dlg)

    chat = ft.ListView(
        expand=True,
        spacing=10,
        auto_scroll=True,
    )

    new_message = ft.TextField(
        hint_text="Write a message...",
        autofocus=True,
        shift_enter=True,
        min_lines=1,
        max_lines=5,
        filled=True,
        expand=True,
        on_submit=send_message_click,
    )

    page.add(
        ft.Container(
            content=chat,
            border=ft.Border.all(1, ft.Colors.OUTLINE),
            border_radius=5,
            padding=10,
            expand=True,
        ),
        ft.Row(
            controls=[
                new_message,
                ft.IconButton(
                    icon=ft.Icons.SEND_ROUNDED,
                    tooltip="Send message",
                    on_click=send_message_click,
                ),
            ]
        ),
    )


ft.run(main)
