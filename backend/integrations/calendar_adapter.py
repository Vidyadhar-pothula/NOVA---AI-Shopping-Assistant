from typing import Dict, Any, Optional, List
import datetime
from backend.tools.registry import registry

class CalendarAdapter:
    def __init__(self):
        # In-memory settings state (can be configured via settings API)
        self.is_connected = False
        self.events = [
            {
                "id": "event_1",
                "title": "ICC World Cup Final Match",
                "date": "2026-11-15",
                "time": "14:00",
                "category": "sports",
                "source": "Google Calendar"
            }
        ]

    def set_connection_status(self, connected: bool):
        self.is_connected = connected

    def handle_calendar_action(
        self,
        action: str,
        title: Optional[str] = None,
        date: Optional[str] = None,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        action_clean = (action or "list").lower().strip()

        # Check authorization (Rule 20 & 35)
        if not self.is_connected:
            return {
                "status": "permission_required",
                "is_connected": False,
                "message": "Google Calendar access isn't connected yet. Please grant permission in Settings to view or create calendar events."
            }

        if action_clean in ["list", "view", "get"]:
            return {
                "status": "success",
                "is_connected": True,
                "events": self.events,
                "message": f"Found {len(self.events)} upcoming event(s) in your connected Google Calendar."
            }

        elif action_clean in ["create", "add", "schedule"]:
            if not title:
                return {"status": "error", "message": "Event title is required."}

            event_id = f"evt_{len(self.events) + 1}"
            event_date = date or (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
            new_event = {
                "id": event_id,
                "title": title,
                "date": event_date,
                "description": description or "Added via NOVA Commerce Agent",
                "source": "Google Calendar"
            }
            self.events.append(new_event)
            return {
                "status": "success",
                "is_connected": True,
                "event": new_event,
                "message": f"Successfully created event '{title}' on {event_date} in your Google Calendar."
            }

        return {"status": "error", "message": f"Unknown calendar action '{action}'."}

calendar_adapter = CalendarAdapter()

def calendar_action(
    action: str,
    title: Optional[str] = None,
    date: Optional[str] = None,
    description: Optional[str] = None
) -> Dict[str, Any]:
    """Execute permissioned Google Calendar actions (list events, add event)."""
    return calendar_adapter.handle_calendar_action(action=action, title=title, date=date, description=description)

calendar_action_schema = {
    "type": "function",
    "function": {
        "name": "calendar_action",
        "description": "View or schedule events in the user's Google Calendar (e.g. 'Add World Cup final to my calendar'). Requires user authorization.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action type: 'list', 'create'."
                },
                "title": {
                    "type": "string",
                    "description": "Title of the calendar event to create."
                },
                "date": {
                    "type": "string",
                    "description": "Date of event in YYYY-MM-DD format."
                },
                "description": {
                    "type": "string",
                    "description": "Optional event details or notes."
                }
            },
            "required": ["action"]
        }
    }
}

registry.register(calendar_action_schema, calendar_action)
