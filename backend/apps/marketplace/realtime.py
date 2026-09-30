"""
Real-time notification and event broadcasting helpers for TFTW.
Pushes events to WebSocket clients via Django Channels.
"""

import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def broadcast_marketplace_event(event_type: str, data: dict):
    """
    Broadcasts a marketplace event to all connected clients
    (Customer marketplace, Restaurant panels, Admin dashboard).

    Event types:
      - listing_created: A new surplus item has been listed
      - listing_updated: Price, status, or details updated
      - listing_deleted: Listing deactivated / removed
      - booking_created: Customer placed a booking (inventory decreased)
      - booking_status_changed: Status updated (CONFIRMED, READY, COMPLETED, CANCELLED)
    """
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                "tftw_marketplace",
                {
                    "type": "marketplace_broadcast",
                    "payload": {
                        "event": event_type,
                        "data": data,
                    },
                },
            )
    except Exception as exc:
        logger.warning(f"Failed to broadcast real-time event '{event_type}': {exc}")
