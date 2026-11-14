import logging
from datetime import datetime
from typing import Dict, Any, Optional
from app.db.mongo import get_db

logger = logging.getLogger("nettrace.agents")

class BaseAgent:
    def __init__(self, agent_name: str, role: str):
        self.agent_name = agent_name
        self.role = role
        self.db = get_db()

    def log_event(self, event_type: str, details: Dict[str, Any], level: str = "INFO"):
        doc = {
            "agent": self.agent_name,
            "role": self.role,
            "event_type": event_type,
            "level": level,
            "details": details,
            "timestamp": datetime.utcnow()
        }
        self.db.audit_logs.insert_one(doc)
        logger.info(f"[{self.agent_name}] {event_type}: {details.get('summary', details)}")
