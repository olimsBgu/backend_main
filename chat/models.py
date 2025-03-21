from django.db import models
from api.models import User


# Create your models here.
class Chat(models.Model):
    """
    Model for a two-user chat.
    ws_key uniquely identifies the WebSocket group name for these users.
    """
    ws_key = models.CharField(max_length=255, unique=True)
    users = models.ManyToManyField(User, related_name='chats')

    def __str__(self):
        return f"Chat: {self.ws_key}"


class ChatMessage(models.Model):
    """
    Stores messages between users in a Chat.
    """
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_viewed = models.BooleanField(default=False)

    def __str__(self):
        return f"Message from {self.sender.email} in {self.chat.ws_key}"
