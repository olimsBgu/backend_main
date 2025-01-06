from ninja import NinjaAPI
from .views import router

api = NinjaAPI(urls_namespace="api")
api.add_router("/", router, tags=["Auth"])
