import logging
from typing import Optional
from pymongo import MongoClient
import mongomock
from app.config import settings

logger = logging.getLogger("nettrace.mongo")

# MongoDB Atlas Collection-Level JSON Schema Validation
SCHEMAS = {
    "policies": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["rule_id", "target_env", "direction", "protocol", "port_range", "action", "status"],
            "properties": {
                "rule_id": {"bsonType": "string", "description": "Unique rule identifier"},
                "target_env": {"enum": ["eng", "qa", "dev", "pat", "prod"], "description": "Environment must be one of eng, qa, dev, pat, prod"},
                "direction": {"enum": ["ingress", "egress"]},
                "protocol": {"enum": ["TCP", "UDP", "ICMP", "ALL"]},
                "port_range": {"bsonType": "string"},
                "action": {"enum": ["ALLOW", "DENY"]},
                "status": {"enum": ["active", "deprecated", "rolled_back", "superseded"]}
            }
        }
    },
    "attestations": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["attestation_id", "schema_version", "predicate_type", "subject", "predicate", "signature", "attestation_hash"],
            "properties": {
                "attestation_id": {"bsonType": "string"},
                "schema_version": {"bsonType": "string"},
                "predicate_type": {"bsonType": "string"},
                "subject": {"bsonType": "object"},
                "predicate": {"bsonType": "object"},
                "signature": {"bsonType": "string"},
                "attestation_hash": {"bsonType": "string"}
            }
        }
    },
    "audit_logs": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["event_type", "timestamp"],
            "properties": {
                "event_type": {"bsonType": "string"},
                "agent": {"bsonType": "string"}
            }
        }
    }
}

class MongoManager:
    _instance: Optional["MongoManager"] = None

    def __init__(self):
        self.client = None
        self.db = None
        self.is_atlas = False
        self._initialize_connection()

    def _initialize_connection(self):
        uri = settings.MONGODB_URI.strip() if settings.MONGODB_URI else ""
        if uri:
            try:
                logger.info("Attempting connection to MongoDB Atlas...")
                self.client = MongoClient(uri, serverSelectionTimeoutMS=4000)
                # Verify connection with ping
                self.client.admin.command('ping')
                self.db = self.client[settings.MONGODB_DB_NAME]
                self.is_atlas = True
                logger.info(f"Connected successfully to MongoDB Atlas! DB: {settings.MONGODB_DB_NAME}")
                self._apply_schema_validation()
            except Exception as e:
                logger.warning(f"Could not connect to MongoDB Atlas ({e}). Falling back to Embedded In-Memory Engine.")
                self.client = mongomock.MongoClient()
                self.db = self.client[settings.MONGODB_DB_NAME]
                self.is_atlas = False
        else:
            logger.info("No MONGODB_URI specified. Using High-Performance Embedded In-Memory MongoDB Engine.")
            self.client = mongomock.MongoClient()
            self.db = self.client[settings.MONGODB_DB_NAME]
            self.is_atlas = False

    def _apply_schema_validation(self):
        """Applies collection-level JSON Schema Validation on MongoDB Atlas"""
        if not self.is_atlas:
            return
        try:
            existing = self.db.list_collection_names()
            for coll_name, validator in SCHEMAS.items():
                if coll_name not in existing:
                    self.db.create_collection(coll_name, validator=validator)
                    logger.info(f"Created collection '{coll_name}' with MongoDB JSON Schema Validation.")
                else:
                    self.db.command('collMod', coll_name, validator=validator)
                    logger.info(f"Updated collection '{coll_name}' with MongoDB JSON Schema Validation.")
        except Exception as e:
            logger.warning(f"Schema validation configuration notice: {e}")

    @classmethod
    def get_instance(cls) -> "MongoManager":
        if cls._instance is None:
            cls._instance = MongoManager()
        return cls._instance

    @property
    def policies(self):
        return self.db["policies"]

    @property
    def pull_requests(self):
        return self.db["pull_requests"]

    @property
    def deployments(self):
        return self.db["deployments"]

    @property
    def attestations(self):
        return self.db["attestations"]

    @property
    def agent_memory(self):
        return self.db["agent_memory"]

    @property
    def network_telemetry(self):
        return self.db["network_telemetry"]

    @property
    def drifts(self):
        return self.db["drifts"]

    @property
    def audit_logs(self):
        return self.db["audit_logs"]

def get_db():
    return MongoManager.get_instance()
