import json

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from chat.models import Chat, ChatMessage
from api.models import User


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
        view_event_max_id = data.get("view_max_id_event", -1)

        if message:
            # Сохранить сообщение в БД
            chat_message = await self.save_message(self.user, self.room_group_name, message)
            time, mes_id = chat_message.created_at, chat_message.id

            # Отправить сообщение всем участникам чата
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_message",
                    "message_id": mes_id,
                    "public_id": str(self.user.public_id),
                    "message": message,
                    "time": time.isoformat(timespec="milliseconds").split('+')[0] + "Z",
                    "is_viewed": chat_message.is_viewed
                }
            )

        if not view_event_max_id == -1:
            flag = await self.viewed_message(room_name=self.room_group_name, view_event_id=view_event_max_id)
            if flag:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "update_view",
                        "message_id": view_event_max_id,
                        "public_id": str(self.user.public_id)
                    }
                )

    async def chat_message(self, event):
        """ Отправляет сообщение клиенту """
        await self.send(text_data=json.dumps({
            "type": event["type"],
            "message_id": event["message_id"],
            "public_id": str(event["public_id"]),
            "message": event["message"],
            "time": event["time"],
            "is_viewed": event["is_viewed"]
        }))

    async def update_view(self, event):
        await self.send(text_data=json.dumps({
            "type": event["type"],
            "message_id": event["message_id"],
            "public_id": str(event["public_id"])
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
            return chat_message

    @database_sync_to_async
    def fetch_messages(self, room_name):
        """ Получает последние 20 сообщений чата """
        chat = Chat.objects.get(ws_key=room_name)
        if chat:
            messages = ChatMessage.objects.filter(chat=chat).order_by("-created_at")
            return [
                {"public_id": str(msg.sender.public_id), "message_id": msg.id, "message": msg.content,
                 "time": msg.created_at.isoformat(timespec="milliseconds").split('+')[0] + "Z",
                 "is_viewed": msg.is_viewed}
                for msg in reversed(messages)
            ]
        return []

    @database_sync_to_async
    def viewed_message(self, room_name, view_event_id):
        chat = Chat.objects.get(ws_key=room_name)
        if chat:
            user = User.objects.get(public_id=str(self.user.public_id))
            if user:
                ChatMessage.objects.filter(chat=chat, id__lte=view_event_id, is_viewed=False).exclude(
                    sender=user.id).update(
                    is_viewed=True)
                return True
        return False
