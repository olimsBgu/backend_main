import os
import django

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rimonim.settings.base")

# 1. Call django.setup() before any code that might load models
django.setup()

# 2. Now you can safely import your routing, which imports consumers, which imports models
from chat.routing import websocket_urlpatterns

from django.core.asgi import get_asgi_application
from chat.middleware import JWTAuthMiddleware

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket":
        JWTAuthMiddleware(
            URLRouter(
                websocket_urlpatterns
            )
        ),
})
