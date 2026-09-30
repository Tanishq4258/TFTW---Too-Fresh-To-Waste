"""
WebSocket consumers for real-time event distribution.

Handles:
  - MarketplaceConsumer: Broadcasts listing additions/updates, stock changes,
    booking events, and status transitions across Customer, Restaurant, and Admin panels.
"""

import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class MarketplaceConsumer(AsyncJsonWebsocketConsumer):
    """
    Subscribes connected clients (Customer marketplace, Restaurant dashboard,
    Admin dashboard) to real-time events.
    """

    GROUP_NAME = "tftw_marketplace"

    async def connect(self):
        # Join broadcast group
        await self.channel_layer.group_add(
            self.GROUP_NAME,
            self.channel_name,
        )
        await self.accept()

        # Send welcome ack
        await self.send_json({
            "type": "connection_established",
            "message": "Connected to TFTW Real-Time Marketplace",
        })

    async def disconnect(self, close_code):
        # Leave broadcast group
        await self.channel_layer.group_discard(
            self.GROUP_NAME,
            self.channel_name,
        )

    async def receive_json(self, content):
        """
        Handle ping / heartbeat messages from clients.
        """
        msg_type = content.get("type", "")
        if msg_type == "ping":
            await self.send_json({"type": "pong"})

    async def marketplace_broadcast(self, event):
        """
        Handler for messages pushed into the 'tftw_marketplace' group.
        Sends payload down to the connected WebSocket client.
        """
        await self.send_json(event["payload"])
