from django.urls import re_path
from .consumers import ChatConsumer

websocket_urlpatterns = [
    # Here "room_name" corresponds to self.scope['url_route']['kwargs']['room_name'] in ChatConsumer
    re_path(r'ws/chat/(?P<room_name>[^/]+)$', ChatConsumer.as_asgi()),
]