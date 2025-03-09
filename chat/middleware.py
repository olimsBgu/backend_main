import logging
from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from ninja_jwt.tokens import AccessToken
from api.models import User

logger = logging.getLogger("django")


@database_sync_to_async
def get_user_from_token(token):
    """ Достаём юзера по JWT-токену """
    try:
        access_token = AccessToken(token)
        user = User.objects.get(id=access_token["user_id"])
        return user
    except Exception:
        return None


class JWTAuthMiddleware:

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query_params = parse_qs(scope["query_string"].decode())
        token = query_params.get("token", [None])[0]

        user = await get_user_from_token(token)

        if not user:  # Если токена нет или он невалидный, сразу выкидываем
            await send({
                "type": "websocket.close",
                "code": 4001  # Код закрытия (Unauthorized)
            })
            return

        scope["user"] = user

        return await self.inner(scope, receive, send)
