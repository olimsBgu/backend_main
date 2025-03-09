import json

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from chat.models import Chat, ChatMessage


class ChatConsumer(AsyncWebsocketConsumer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.room_group_name = None

    async def connect(self):
        self.user = self.scope.get("user")

        # Если нет пользователя или он не аутентифицирован — нахуй
        if not self.user or not getattr(self.user, "id", None):
            await self.close()
            return

        room_name = self.scope["url_route"]["kwargs"]["room_name"]
        parts = room_name.split("_")

        if len(parts) != 3 or parts[0] != "chat":
            await self.close()
            return

        try:
            user_id_1, user_id_2 = parts[1], parts[2]
        except ValueError:
            await self.close()
            return

        if str(self.user.public_id) not in (str(user_id_1), str(user_id_2)):
            await self.close()
            return

        if not await self.is_chat_exists(user_id_1, user_id_2):
            await self.close()
            return

        self.room_group_name = room_name

        # Если проверка пройдена — подключаем пользователя
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Подгружаем последние сообщения
        messages = await self.fetch_messages(room_name)
        await self.send(text_data=json.dumps({
            "type": "chat_history",
            "messages": messages
        }))

    async def disconnect(self, close_code):
        if self.room_group_name:
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        """ Обрабатывает входящие сообщения от клиента """
        data = json.loads(text_data)
        message = data.get("message", "").strip()

        if message:
            # Сохранить сообщение в БД
            time = await self.save_message(self.user, self.room_group_name, message)

            # Отправить сообщение всем участникам чата
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_message",
                    "public_id": str(self.user.public_id),
                    "message": message,
                    "time": time.strftime("%d/%m/%Y, %H:%M:%S")
                }
            )

    async def chat_message(self, event):
        """ Отправляет сообщение клиенту """
        await self.send(text_data=json.dumps({
            "type": "chat_message",
            "public_id": str(event["public_id"]),
            "message": event["message"],
            "time": event["time"]
        }))

    @database_sync_to_async
    def is_chat_exists(self, user_id_1, user_id_2):
        """ Проверяет, существует ли чат между пользователями """
        return Chat.objects.filter(
            users__public_id=user_id_1
        ).filter(
            users__public_id=user_id_2
        ).exists()

    @database_sync_to_async
    def save_message(self, user, room_name, content):
        """ Сохраняет сообщение в БД """
        chat = Chat.objects.get(ws_key=room_name)
        if chat:
            chat_message = ChatMessage.objects.create(chat=chat, sender=user, content=content)
            return chat_message.created_at

    @database_sync_to_async
    def fetch_messages(self, room_name):
        """ Получает последние 20 сообщений чата """
        chat = Chat.objects.get(ws_key=room_name)
        if chat:
            messages = ChatMessage.objects.filter(chat=chat).order_by("-created_at")
            return [
                {"public_id": str(msg.sender.public_id), "message": msg.content, "time": msg.created_at.strftime("%d/%m/%Y, %H:%M:%S")}
                for msg in reversed(messages)
            ]
        return []
