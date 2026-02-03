"""HITL checkpoint system for workflow intervention points."""

import asyncio
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import DatabaseManager
from src.agents.base import AgentRole

logger = structlog.get_logger()


class CheckpointStatus(Enum):
    """Checkpoint status values."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class CheckpointType(Enum):
    """Types of HITL checkpoints."""
    RESEARCH_PLAN_REVIEW = "research_plan_review"
    AGENT_RESULT_VALIDATION = "agent_result_validation"
    RISK_ASSESSMENT_REVIEW = "risk_assessment_review"
    FINAL_RECOMMENDATION_APPROVAL = "final_recommendation_approval"
    DATA_QUALITY_CHECK = "data_quality_check"
    SCOPE_MODIFICATION = "scope_modification"


@dataclass
class CheckpointContext:
    """Context information for a checkpoint."""
    workflow_id: str
    project_id: str
    agent_role: Optional[AgentRole] = None
    stage: Optional[str] = None
    confidence_score: Optional[float] = None
    data_summary: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CheckpointDecision:
    """Decision made at a checkpoint."""
    checkpoint_id: str
    status: CheckpointStatus
    reviewer: str
    decision_time: datetime
    comments: Optional[str] = None
    modifications: Dict[str, Any] = field(default_factory=dict)
    confidence_adjustment: Optional[float] = None


class HITLCheckpoint:
    """
    Human-in-the-loop checkpoint for workflow intervention.
    
    Allows humans to review, approve, reject, or modify research workflow
    execution at critical decision points.
    """
    
    def __init__(self, 
                 checkpoint_id: str,
                 checkpoint_type: CheckpointType,
                 context: CheckpointContext,
                 timeout_minutes: int = 60):
        
        self.checkpoint_id = checkpoint_id
        self.checkpoint_type = checkpoint_type
        self.context = context
        self.timeout_minutes = timeout_minutes
        
        # Status tracking
        self.status = CheckpointStatus.PENDING
        self.created_at = datetime.now()
        self.expires_at = self.created_at + timedelta(minutes=timeout_minutes)
        self.decision: Optional[CheckpointDecision] = None
        
        # Synchronization
        self._decision_event = asyncio.Event()
        self._timeout_task: Optional[asyncio.Task] = None
        
        self.logger = logger.bind(checkpoint_id=checkpoint_id, type=checkpoint_type.value)
        
        # Start timeout countdown
        self._start_timeout()
    
    def _start_timeout(self):
        """Start timeout countdown task."""
        
        async def timeout_handler():
            try:
                await asyncio.sleep(self.timeout_minutes * 60)
                if self.status == CheckpointStatus.PENDING:
                    self.status = CheckpointStatus.EXPIRED
                    self._decision_event.set()
                    self.logger.warning("checkpoint_expired")
            except asyncio.CancelledError:
                pass
        
        self._timeout_task = asyncio.create_task(timeout_handler())
    
    async def wait_for_decision(self) -> CheckpointDecision:
        """
        Wait for human decision on checkpoint.
        
        Returns the decision when made or raises TimeoutError if expired.
        """
        
        self.logger.info("awaiting_human_decision", expires_at=self.expires_at.isoformat())
        
        # Wait for decision or timeout
        await self._decision_event.wait()
        
        # Cancel timeout task
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
        
        if self.status == CheckpointStatus.EXPIRED:
            raise TimeoutError(f"Checkpoint {self.checkpoint_id} expired without decision")
        
        if not self.decision:
            raise ValueError("Decision event set but no decision recorded")
        
        self.logger.info("human_decision_received", 
                        status=self.decision.status.value,
                        reviewer=self.decision.reviewer)
        
        return self.decision
    
    def make_decision(self, 
                     status: CheckpointStatus,
                     reviewer: str,
                     comments: Optional[str] = None,
                     modifications: Optional[Dict[str, Any]] = None,
                     confidence_adjustment: Optional[float] = None) -> bool:
        """
        Record human decision for checkpoint.
        
        Returns True if decision was recorded, False if checkpoint already decided.
        """
        
        if self.status != CheckpointStatus.PENDING:
            self.logger.warning("checkpoint_already_decided", current_status=self.status.value)
            return False
        
        # Validate decision
        if status not in [CheckpointStatus.APPROVED, CheckpointStatus.REJECTED, CheckpointStatus.CANCELLED]:
            raise ValueError(f"Invalid decision status: {status}")
        
        # Record decision
        self.decision = CheckpointDecision(
            checkpoint_id=self.checkpoint_id,
            status=status,
            reviewer=reviewer,
            decision_time=datetime.now(),
            comments=comments,
            modifications=modifications or {},
            confidence_adjustment=confidence_adjustment
        )
        
        self.status = status
        self._decision_event.set()
        
        self.logger.info("checkpoint_decision_recorded",
                        status=status.value,
                        reviewer=reviewer,
                        has_comments=bool(comments),
                        has_modifications=bool(modifications))
        
        return True
    
    def get_summary(self) -> Dict[str, Any]:
        """Get checkpoint summary for display/API."""
        
        return {
            "checkpoint_id": self.checkpoint_id,
            "type": self.checkpoint_type.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "timeout_minutes": self.timeout_minutes,
            "context": {
                "workflow_id": self.context.workflow_id,
                "project_id": self.context.project_id,
                "agent_role": self.context.agent_role.value if self.context.agent_role else None,
                "stage": self.context.stage,
                "confidence_score": self.context.confidence_score,
                "data_summary": self.context.data_summary
            },
            "decision": {
                "status": self.decision.status.value,
                "reviewer": self.decision.reviewer,
                "decision_time": self.decision.decision_time.isoformat(),
                "comments": self.decision.comments,
                "has_modifications": bool(self.decision.modifications),
                "confidence_adjustment": self.decision.confidence_adjustment
            } if self.decision else None,
            "time_remaining": max(0, int((self.expires_at - datetime.now()).total_seconds())) if self.status == CheckpointStatus.PENDING else None
        }


class HITLCheckpointManager:
    """Manager for HITL checkpoints across workflows."""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.logger = logger.bind(component="hitl_checkpoint_manager")
        
        # Active checkpoints
        self.active_checkpoints: Dict[str, HITLCheckpoint] = {}
        
        # Configuration
        self.default_timeouts = {
            CheckpointType.RESEARCH_PLAN_REVIEW: 120,  # 2 hours
            CheckpointType.AGENT_RESULT_VALIDATION: 60,  # 1 hour
            CheckpointType.RISK_ASSESSMENT_REVIEW: 90,  # 1.5 hours
            CheckpointType.FINAL_RECOMMENDATION_APPROVAL: 180,  # 3 hours
            CheckpointType.DATA_QUALITY_CHECK: 30,  # 30 minutes
            CheckpointType.SCOPE_MODIFICATION: 120  # 2 hours
        }
        
        # Checkpoint rules
        self.checkpoint_rules = self._initialize_rules()
    
    def _initialize_rules(self) -> Dict[str, Dict[str, Any]]:
        """Initialize checkpoint triggering rules."""
        
        return {
            "low_confidence": {
                "condition": lambda context: context.confidence_score and context.confidence_score < 0.4,
                "checkpoint_type": CheckpointType.AGENT_RESULT_VALIDATION,
                "priority": "high",
                "description": "Low confidence result requires human validation"
            },
            "risk_assessment_high": {
                "condition": lambda context: (
                    context.agent_role == AgentRole.RISK_ANALYST and
                    context.data_summary.get("max_risk_score", 0) > 0.8
                ),
                "checkpoint_type": CheckpointType.RISK_ASSESSMENT_REVIEW,
                "priority": "critical",
                "description": "High risk assessment requires review"
            },
            "scope_expansion": {
                "condition": lambda context: (
                    context.data_summary.get("additional_companies_suggested", 0) > 0
                ),
                "checkpoint_type": CheckpointType.SCOPE_MODIFICATION,
                "priority": "medium",
                "description": "Scope expansion suggestion requires approval"
            },
            "data_quality_issues": {
                "condition": lambda context: (
                    context.data_summary.get("data_quality_warnings", 0) > 2
                ),
                "checkpoint_type": CheckpointType.DATA_QUALITY_CHECK,
                "priority": "high",
                "description": "Data quality issues detected"
            }
        }
    
    async def create_checkpoint(self,
                              checkpoint_type: CheckpointType,
                              context: CheckpointContext,
                              timeout_minutes: Optional[int] = None,
                              force: bool = False) -> HITLCheckpoint:
        """
        Create a new HITL checkpoint.
        
        Args:
            checkpoint_type: Type of checkpoint
            context: Context information
            timeout_minutes: Override default timeout
            force: Create even if rules don't trigger
        """
        
        # Check if checkpoint should be created
        if not force and not self._should_create_checkpoint(checkpoint_type, context):
            raise ValueError(f"Checkpoint creation not triggered for {checkpoint_type.value}")
        
        checkpoint_id = f"cp_{uuid.uuid4()}"
        timeout = timeout_minutes or self.default_timeouts.get(checkpoint_type, 60)
        
        checkpoint = HITLCheckpoint(
            checkpoint_id=checkpoint_id,
            checkpoint_type=checkpoint_type,
            context=context,
            timeout_minutes=timeout
        )
        
        self.active_checkpoints[checkpoint_id] = checkpoint
        
        self.logger.info("checkpoint_created",
                        checkpoint_id=checkpoint_id,
                        type=checkpoint_type.value,
                        timeout_minutes=timeout,
                        workflow_id=context.workflow_id)
        
        return checkpoint
    
    def _should_create_checkpoint(self, 
                                checkpoint_type: CheckpointType,
                                context: CheckpointContext) -> bool:
        """Determine if checkpoint should be created based on rules."""
        
        for rule_name, rule in self.checkpoint_rules.items():
            if rule["checkpoint_type"] == checkpoint_type:
                try:
                    if rule["condition"](context):
                        self.logger.info("checkpoint_rule_triggered",
                                       rule=rule_name,
                                       type=checkpoint_type.value)
                        return True
                except Exception as e:
                    self.logger.warning("checkpoint_rule_evaluation_failed",
                                      rule=rule_name, error=str(e))
        
        return False
    
    async def evaluate_checkpoint_needs(self, context: CheckpointContext) -> List[CheckpointType]:
        """Evaluate what checkpoints are needed for given context."""
        
        needed_checkpoints = []
        
        for rule_name, rule in self.checkpoint_rules.items():
            try:
                if rule["condition"](context):
                    checkpoint_type = rule["checkpoint_type"]
                    if checkpoint_type not in needed_checkpoints:
                        needed_checkpoints.append(checkpoint_type)
                        
                        self.logger.info("checkpoint_needed",
                                       rule=rule_name,
                                       type=checkpoint_type.value,
                                       priority=rule["priority"])
            except Exception as e:
                self.logger.warning("checkpoint_evaluation_failed",
                                  rule=rule_name, error=str(e))
        
        return needed_checkpoints
    
    def get_checkpoint(self, checkpoint_id: str) -> Optional[HITLCheckpoint]:
        """Get checkpoint by ID."""
        return self.active_checkpoints.get(checkpoint_id)
    
    def get_pending_checkpoints(self,
                               workflow_id: Optional[str] = None,
                               project_id: Optional[str] = None) -> List[HITLCheckpoint]:
        """Get pending checkpoints with optional filtering."""
        
        checkpoints = []
        
        for checkpoint in self.active_checkpoints.values():
            if checkpoint.status != CheckpointStatus.PENDING:
                continue
            
            if workflow_id and checkpoint.context.workflow_id != workflow_id:
                continue
            
            if project_id and checkpoint.context.project_id != project_id:
                continue
            
            checkpoints.append(checkpoint)
        
        # Sort by priority and creation time
        return sorted(checkpoints, key=lambda cp: (
            self._get_checkpoint_priority(cp.checkpoint_type),
            cp.created_at
        ))
    
    def _get_checkpoint_priority(self, checkpoint_type: CheckpointType) -> int:
        """Get numeric priority for sorting (lower = higher priority)."""
        
        priority_map = {
            CheckpointType.FINAL_RECOMMENDATION_APPROVAL: 1,
            CheckpointType.RISK_ASSESSMENT_REVIEW: 2,
            CheckpointType.RESEARCH_PLAN_REVIEW: 3,
            CheckpointType.DATA_QUALITY_CHECK: 4,
            CheckpointType.AGENT_RESULT_VALIDATION: 5,
            CheckpointType.SCOPE_MODIFICATION: 6
        }
        
        return priority_map.get(checkpoint_type, 10)
    
    async def cleanup_expired_checkpoints(self) -> int:
        """Remove expired checkpoints and return count."""
        
        expired_ids = []
        current_time = datetime.now()
        
        for checkpoint_id, checkpoint in self.active_checkpoints.items():
            if (checkpoint.status == CheckpointStatus.EXPIRED or
                (checkpoint.status == CheckpointStatus.PENDING and 
                 current_time > checkpoint.expires_at)):
                expired_ids.append(checkpoint_id)
        
        for checkpoint_id in expired_ids:
            del self.active_checkpoints[checkpoint_id]
        
        if expired_ids:
            self.logger.info("expired_checkpoints_cleaned",
                           count=len(expired_ids))
        
        return len(expired_ids)
    
    def get_checkpoint_statistics(self) -> Dict[str, Any]:
        """Get checkpoint system statistics."""
        
        stats = {
            "total_checkpoints": len(self.active_checkpoints),
            "by_status": {},
            "by_type": {},
            "average_response_time": None,
            "pending_by_priority": {}
        }
        
        # Count by status
        for checkpoint in self.active_checkpoints.values():
            status = checkpoint.status.value
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
            
            # Count by type
            checkpoint_type = checkpoint.checkpoint_type.value
            stats["by_type"][checkpoint_type] = stats["by_type"].get(checkpoint_type, 0) + 1
        
        # Calculate response times for completed checkpoints
        response_times = []
        for checkpoint in self.active_checkpoints.values():
            if checkpoint.decision:
                response_time = (checkpoint.decision.decision_time - checkpoint.created_at).total_seconds()
                response_times.append(response_time)
        
        if response_times:
            stats["average_response_time"] = sum(response_times) / len(response_times)
        
        # Pending by priority
        pending_checkpoints = [cp for cp in self.active_checkpoints.values() 
                             if cp.status == CheckpointStatus.PENDING]
        
        for checkpoint in pending_checkpoints:
            priority = self._get_checkpoint_priority(checkpoint.checkpoint_type)
            priority_name = f"priority_{priority}"
            stats["pending_by_priority"][priority_name] = stats["pending_by_priority"].get(priority_name, 0) + 1
        
        return stats
    
    def add_checkpoint_rule(self,
                          rule_name: str,
                          condition: Callable[[CheckpointContext], bool],
                          checkpoint_type: CheckpointType,
                          priority: str = "medium",
                          description: str = "") -> None:
        """Add custom checkpoint rule."""
        
        self.checkpoint_rules[rule_name] = {
            "condition": condition,
            "checkpoint_type": checkpoint_type,
            "priority": priority,
            "description": description
        }
        
        self.logger.info("checkpoint_rule_added",
                        rule=rule_name,
                        type=checkpoint_type.value,
                        priority=priority)