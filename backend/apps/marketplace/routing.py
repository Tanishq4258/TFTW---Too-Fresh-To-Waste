"""
WebSocket routing for Too Fresh To Waste.
"""

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r"^ws/marketplace/?$", consumers.MarketplaceConsumer.as_asgi()),
]
