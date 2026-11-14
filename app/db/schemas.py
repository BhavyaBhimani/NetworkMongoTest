from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

class BranchEnv(str, Enum):
    ENG = "eng"
    QA = "qa"
    DEV = "dev"
    PAT = "pat"  # Pre-Acceptance Testing / Staging
    PROD = "prod"

class PRStatus(str, Enum):
    OPEN = "OPEN"
    VALIDATING = "VALIDATING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    MERGED = "MERGED"
    DEPLOYING = "DEPLOYING"
    DEPLOYED = "DEPLOYED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class PolicyRule(BaseModel):
    rule_id: str
    name: str
    target_env: str = "dev"
    direction: str = "ingress"  # ingress / egress
    protocol: str = "TCP"       # TCP, UDP, ICMP, ALL
    port_range: str = "443"     # e.g., "443", "80-443", "22", "*"
    source_cidr: str = "10.0.0.0/16"
    destination_cidr: str = "10.1.0.0/16"
    action: str = "ALLOW"       # ALLOW / DENY
    risk_level: str = "LOW"
    description: str = ""
    status: str = "active"      # active, deprecated, rolled_back
    version: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)

class CreatePRRequest(BaseModel):
    title: str
    author: str
    target_branch: str = "dev"
    source_branch: str = "feature/network-update"
    policy_changes: List[Dict[str, Any]]
    description: Optional[str] = ""

class ValidationResult(BaseModel):
    approved: bool
    risk_level: str
    requires_human_approval: bool
    reasons: List[str]
    context_notes: List[str]
    matched_historical_incidents: List[Dict[str, Any]] = []

class DeploymentResult(BaseModel):
    success: bool
    env: str
    deployed_revision: int
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class TestResult(BaseModel):
    passed: bool
    total_checks: int
    passed_checks: int
    failed_checks: int
    latency_avg_ms: float
    packet_loss_pct: float
    details: List[Dict[str, Any]]

class AttestationRecord(BaseModel):
    attestation_id: str
    schema_version: str = "https://in-toto.io/Statement/v1"
    predicate_type: str = "https://slsa.dev/provenance/v1"
    subject_digest: str
    pr_id: str
    pr_author: str
    target_env: str
    commit_hash: str
    test_run_id: str
    test_status: str
    signature: str
    previous_attestation_hash: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class MemoryEpisode(BaseModel):
    memory_id: str
    memory_type: str  # incident, failed_pr, manual_drift, deployment_success
    environment: str
    summary: str
    tags: List[str] = []
    affected_ports: List[str] = []
    affected_cidrs: List[str] = []
    embedding: List[float] = []
    outcome: str
    resolution: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class DriftIncident(BaseModel):
    incident_id: str
    env: str
    drift_type: str
    detected_rule: Dict[str, Any]
    detected_by: str = "AuditAgent"
    reconciled: bool = False
    details: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
