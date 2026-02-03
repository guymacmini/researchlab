"""Approval workflow system for HITL checkpoints."""

import asyncio
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import DatabaseManager
from .checkpoint import HITLCheckpoint, CheckpointStatus, CheckpointType

logger = structlog.get_logger()


class ApprovalStatus(Enum):
    """Approval request status."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    EXPIRED = "expired"


class ApprovalLevel(Enum):
    """Approval authority levels."""
    ANALYST = "analyst"
    SENIOR_ANALYST = "senior_analyst"
    TEAM_LEAD = "team_lead"
    DIRECTOR = "director"
    VP = "vp"


class ApprovalDecision(Enum):
    """Approval decision types."""
    APPROVE = "approve"
    REJECT = "reject"
    ESCALATE = "escalate"
    REQUEST_CHANGES = "request_changes"


@dataclass
class ApprovalRequest:
    """Request for approval in HITL workflow."""
    request_id: str
    checkpoint_id: str
    title: str
    description: str
    required_level: ApprovalLevel
    urgency: str  # low, medium, high, critical
    
    # Content for approval
    content: Dict[str, Any]
    attachments: List[str] = field(default_factory=list)
    
    # Status tracking
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    
    # Approval chain
    assigned_reviewers: List[str] = field(default_factory=list)
    completed_reviews: List['ApprovalReview'] = field(default_factory=list)
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalReview:
    """Individual review within approval process."""
    review_id: str
    request_id: str
    reviewer: str
    reviewer_level: ApprovalLevel
    decision: ApprovalDecision
    comments: str
    reviewed_at: datetime
    
    # Specific feedback
    confidence_adjustment: Optional[float] = None
    required_changes: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


class ApprovalWorkflow:
    """
    Manages approval workflows for HITL checkpoints.
    
    Handles routing approval requests to appropriate reviewers,
    managing approval chains, and escalation procedures.
    """
    
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.logger = logger.bind(component="approval_workflow")
        
        # Active approval requests
        self.active_requests: Dict[str, ApprovalRequest] = {}
        
        # Reviewer configuration
        self.reviewers: Dict[str, Dict[str, Any]] = {}
        
        # Approval rules
        self.approval_rules = self._initialize_approval_rules()
        
        # Notification callbacks
        self.notification_callbacks: List = []
        
        # Load reviewer configuration
        self._load_reviewer_config()
    
    def _initialize_approval_rules(self) -> Dict[CheckpointType, Dict[str, Any]]:
        """Initialize approval rules for different checkpoint types."""
        
        return {
            CheckpointType.RESEARCH_PLAN_REVIEW: {
                "required_level": ApprovalLevel.SENIOR_ANALYST,
                "timeout_hours": 4,
                "escalation_chain": [ApprovalLevel.TEAM_LEAD, ApprovalLevel.DIRECTOR],
                "parallel_reviews": False,
                "minimum_approvals": 1
            },
            CheckpointType.AGENT_RESULT_VALIDATION: {
                "required_level": ApprovalLevel.ANALYST,
                "timeout_hours": 2,
                "escalation_chain": [ApprovalLevel.SENIOR_ANALYST],
                "parallel_reviews": False,
                "minimum_approvals": 1
            },
            CheckpointType.RISK_ASSESSMENT_REVIEW: {
                "required_level": ApprovalLevel.TEAM_LEAD,
                "timeout_hours": 6,
                "escalation_chain": [ApprovalLevel.DIRECTOR, ApprovalLevel.VP],
                "parallel_reviews": True,
                "minimum_approvals": 2
            },
            CheckpointType.FINAL_RECOMMENDATION_APPROVAL: {
                "required_level": ApprovalLevel.DIRECTOR,
                "timeout_hours": 8,
                "escalation_chain": [ApprovalLevel.VP],
                "parallel_reviews": True,
                "minimum_approvals": 2
            },
            CheckpointType.DATA_QUALITY_CHECK: {
                "required_level": ApprovalLevel.ANALYST,
                "timeout_hours": 1,
                "escalation_chain": [ApprovalLevel.SENIOR_ANALYST],
                "parallel_reviews": False,
                "minimum_approvals": 1
            },
            CheckpointType.SCOPE_MODIFICATION: {
                "required_level": ApprovalLevel.SENIOR_ANALYST,
                "timeout_hours": 3,
                "escalation_chain": [ApprovalLevel.TEAM_LEAD],
                "parallel_reviews": False,
                "minimum_approvals": 1
            }
        }
    
    def _load_reviewer_config(self):
        """Load reviewer configuration (mock implementation)."""
        
        # In production, this would load from database or config file
        self.reviewers = {
            "analyst_1": {
                "name": "Junior Analyst",
                "level": ApprovalLevel.ANALYST,
                "specialties": ["fundamental_analysis", "data_quality"],
                "max_concurrent": 5,
                "active": True,
                "email": "analyst1@company.com"
            },
            "analyst_2": {
                "name": "Senior Analyst",
                "level": ApprovalLevel.SENIOR_ANALYST,
                "specialties": ["quantitative_analysis", "risk_assessment"],
                "max_concurrent": 3,
                "active": True,
                "email": "senior1@company.com"
            },
            "team_lead_1": {
                "name": "Team Lead",
                "level": ApprovalLevel.TEAM_LEAD,
                "specialties": ["strategy", "portfolio_management"],
                "max_concurrent": 2,
                "active": True,
                "email": "teamlead1@company.com"
            },
            "director_1": {
                "name": "Research Director",
                "level": ApprovalLevel.DIRECTOR,
                "specialties": ["strategy", "final_approval"],
                "max_concurrent": 1,
                "active": True,
                "email": "director1@company.com"
            }
        }
    
    async def create_approval_request(self,
                                    checkpoint: HITLCheckpoint,
                                    title: str,
                                    description: str,
                                    content: Dict[str, Any],
                                    urgency: str = "medium") -> ApprovalRequest:
        """
        Create approval request for HITL checkpoint.
        
        Args:
            checkpoint: Associated checkpoint
            title: Brief title for approval
            description: Detailed description
            content: Content to be reviewed
            urgency: Urgency level (low, medium, high, critical)
        """
        
        request_id = f"apr_{uuid.uuid4()}"
        
        # Determine approval requirements
        rules = self.approval_rules.get(checkpoint.checkpoint_type)
        if not rules:
            raise ValueError(f"No approval rules for checkpoint type {checkpoint.checkpoint_type}")
        
        required_level = rules["required_level"]
        timeout_hours = rules["timeout_hours"]
        
        # Adjust timeout based on urgency
        urgency_multipliers = {
            "critical": 0.5,
            "high": 0.75,
            "medium": 1.0,
            "low": 1.5
        }
        timeout_hours *= urgency_multipliers.get(urgency, 1.0)
        
        # Create approval request
        request = ApprovalRequest(
            request_id=request_id,
            checkpoint_id=checkpoint.checkpoint_id,
            title=title,
            description=description,
            required_level=required_level,
            urgency=urgency,
            content=content,
            expires_at=datetime.now() + timedelta(hours=timeout_hours)
        )
        
        # Assign reviewers
        request.assigned_reviewers = self._assign_reviewers(checkpoint.checkpoint_type, required_level)
        
        self.active_requests[request_id] = request
        
        # Notify reviewers
        await self._notify_reviewers(request)
        
        self.logger.info("approval_request_created",
                        request_id=request_id,
                        checkpoint_id=checkpoint.checkpoint_id,
                        type=checkpoint.checkpoint_type.value,
                        urgency=urgency,
                        reviewers=len(request.assigned_reviewers))
        
        return request
    
    def _assign_reviewers(self, checkpoint_type: CheckpointType, required_level: ApprovalLevel) -> List[str]:
        """Assign reviewers based on checkpoint type and required level."""
        
        rules = self.approval_rules[checkpoint_type]
        parallel_reviews = rules["parallel_reviews"]
        minimum_approvals = rules.get("minimum_approvals", 1)
        
        # Find available reviewers at required level or higher
        eligible_reviewers = []
        
        level_hierarchy = [
            ApprovalLevel.ANALYST,
            ApprovalLevel.SENIOR_ANALYST,
            ApprovalLevel.TEAM_LEAD,
            ApprovalLevel.DIRECTOR,
            ApprovalLevel.VP
        ]
        
        required_level_index = level_hierarchy.index(required_level)
        
        for reviewer_id, reviewer_info in self.reviewers.items():
            if not reviewer_info["active"]:
                continue
            
            reviewer_level = reviewer_info["level"]
            if level_hierarchy.index(reviewer_level) >= required_level_index:
                # Check current workload
                current_load = self._get_reviewer_current_load(reviewer_id)
                if current_load < reviewer_info["max_concurrent"]:
                    eligible_reviewers.append(reviewer_id)
        
        # Select reviewers based on rules
        if parallel_reviews:
            # Assign multiple reviewers for parallel review
            return eligible_reviewers[:minimum_approvals * 2]  # Assign extra for coverage
        else:
            # Assign single reviewer (prefer least loaded)
            if eligible_reviewers:
                return [min(eligible_reviewers, key=self._get_reviewer_current_load)]
            else:
                return []
    
    def _get_reviewer_current_load(self, reviewer_id: str) -> int:
        """Get current number of pending requests for reviewer."""
        
        count = 0
        for request in self.active_requests.values():
            if (reviewer_id in request.assigned_reviewers and 
                request.status == ApprovalStatus.PENDING):
                count += 1
        
        return count
    
    async def submit_review(self,
                          request_id: str,
                          reviewer: str,
                          decision: ApprovalDecision,
                          comments: str,
                          confidence_adjustment: Optional[float] = None,
                          required_changes: Optional[List[str]] = None) -> bool:
        """
        Submit review for approval request.
        
        Args:
            request_id: ID of approval request
            reviewer: Reviewer identifier
            decision: Approval decision
            comments: Review comments
            confidence_adjustment: Confidence score adjustment
            required_changes: List of required changes
        
        Returns:
            True if review successfully submitted
        """
        
        request = self.active_requests.get(request_id)
        if not request:
            self.logger.error("approval_request_not_found", request_id=request_id)
            return False
        
        if reviewer not in request.assigned_reviewers:
            self.logger.error("reviewer_not_assigned", request_id=request_id, reviewer=reviewer)
            return False
        
        if request.status != ApprovalStatus.PENDING:
            self.logger.warning("request_already_decided", request_id=request_id, status=request.status.value)
            return False
        
        # Get reviewer info
        reviewer_info = self.reviewers.get(reviewer)
        if not reviewer_info:
            self.logger.error("reviewer_not_found", reviewer=reviewer)
            return False
        
        # Create review record
        review = ApprovalReview(
            review_id=f"rev_{uuid.uuid4()}",
            request_id=request_id,
            reviewer=reviewer,
            reviewer_level=reviewer_info["level"],
            decision=decision,
            comments=comments,
            reviewed_at=datetime.now(),
            confidence_adjustment=confidence_adjustment,
            required_changes=required_changes or [],
            recommendations=[]
        )
        
        request.completed_reviews.append(review)
        
        # Determine if request is complete
        await self._evaluate_request_completion(request)
        
        self.logger.info("review_submitted",
                        request_id=request_id,
                        reviewer=reviewer,
                        decision=decision.value)
        
        return True
    
    async def _evaluate_request_completion(self, request: ApprovalRequest) -> None:
        """Evaluate if approval request is complete and update status."""
        
        checkpoint_type = None
        # Find checkpoint type (would be stored in request in real implementation)
        for cp in self.active_requests.values():
            if cp.checkpoint_id == request.checkpoint_id:
                # Get checkpoint to find type (simplified)
                break
        
        if not checkpoint_type:
            return
        
        rules = self.approval_rules.get(checkpoint_type, {})
        parallel_reviews = rules.get("parallel_reviews", False)
        minimum_approvals = rules.get("minimum_approvals", 1)
        
        # Count approvals and rejections
        approvals = sum(1 for review in request.completed_reviews 
                       if review.decision == ApprovalDecision.APPROVE)
        rejections = sum(1 for review in request.completed_reviews 
                        if review.decision == ApprovalDecision.REJECT)
        escalations = sum(1 for review in request.completed_reviews 
                         if review.decision == ApprovalDecision.ESCALATE)
        
        # Determine final status
        if parallel_reviews:
            # Parallel reviews - need minimum approvals
            if approvals >= minimum_approvals:
                request.status = ApprovalStatus.APPROVED
            elif rejections > 0:
                request.status = ApprovalStatus.REJECTED
            elif escalations > 0:
                await self._escalate_request(request)
        else:
            # Sequential reviews - first decision wins
            if request.completed_reviews:
                last_review = request.completed_reviews[-1]
                if last_review.decision == ApprovalDecision.APPROVE:
                    request.status = ApprovalStatus.APPROVED
                elif last_review.decision == ApprovalDecision.REJECT:
                    request.status = ApprovalStatus.REJECTED
                elif last_review.decision == ApprovalDecision.ESCALATE:
                    await self._escalate_request(request)
        
        # Notify completion if decided
        if request.status in [ApprovalStatus.APPROVED, ApprovalStatus.REJECTED]:
            await self._notify_completion(request)
    
    async def _escalate_request(self, request: ApprovalRequest) -> None:
        """Escalate approval request to higher authority."""
        
        # Find checkpoint type and escalation chain
        checkpoint_type = None  # Would be determined from checkpoint
        rules = self.approval_rules.get(checkpoint_type, {})
        escalation_chain = rules.get("escalation_chain", [])
        
        if escalation_chain:
            # Assign to next level in escalation chain
            next_level = escalation_chain[0]
            new_reviewers = self._assign_reviewers_by_level(next_level)
            
            if new_reviewers:
                request.assigned_reviewers = new_reviewers
                request.status = ApprovalStatus.ESCALATED
                
                # Reset completed reviews for new reviewers
                request.completed_reviews = []
                
                await self._notify_reviewers(request)
                
                self.logger.info("request_escalated",
                               request_id=request.request_id,
                               new_level=next_level.value,
                               new_reviewers=len(new_reviewers))
            else:
                # No reviewers available at escalation level
                request.status = ApprovalStatus.REJECTED
                self.logger.warning("escalation_failed_no_reviewers",
                                  request_id=request.request_id,
                                  target_level=next_level.value)
    
    def _assign_reviewers_by_level(self, level: ApprovalLevel) -> List[str]:
        """Assign reviewers at specific level."""
        
        eligible_reviewers = []
        
        for reviewer_id, reviewer_info in self.reviewers.items():
            if (reviewer_info["active"] and 
                reviewer_info["level"] == level):
                
                current_load = self._get_reviewer_current_load(reviewer_id)
                if current_load < reviewer_info["max_concurrent"]:
                    eligible_reviewers.append(reviewer_id)
        
        return eligible_reviewers[:2]  # Limit to 2 reviewers
    
    async def _notify_reviewers(self, request: ApprovalRequest) -> None:
        """Notify assigned reviewers of new approval request."""
        
        for callback in self.notification_callbacks:
            try:
                await callback("reviewer_notification", {
                    "request_id": request.request_id,
                    "title": request.title,
                    "urgency": request.urgency,
                    "assigned_reviewers": request.assigned_reviewers,
                    "expires_at": request.expires_at.isoformat() if request.expires_at else None
                })
            except Exception as e:
                self.logger.warning("notification_callback_failed", error=str(e))
    
    async def _notify_completion(self, request: ApprovalRequest) -> None:
        """Notify completion of approval request."""
        
        for callback in self.notification_callbacks:
            try:
                await callback("approval_completion", {
                    "request_id": request.request_id,
                    "status": request.status.value,
                    "checkpoint_id": request.checkpoint_id,
                    "completed_reviews": len(request.completed_reviews)
                })
            except Exception as e:
                self.logger.warning("notification_callback_failed", error=str(e))
    
    def get_pending_requests(self, reviewer: Optional[str] = None) -> List[ApprovalRequest]:
        """Get pending approval requests, optionally filtered by reviewer."""
        
        requests = []
        
        for request in self.active_requests.values():
            if request.status != ApprovalStatus.PENDING:
                continue
            
            if reviewer and reviewer not in request.assigned_reviewers:
                continue
            
            requests.append(request)
        
        # Sort by urgency and creation time
        urgency_priority = {"critical": 1, "high": 2, "medium": 3, "low": 4}
        
        return sorted(requests, key=lambda r: (
            urgency_priority.get(r.urgency, 5),
            r.created_at
        ))
    
    def get_approval_statistics(self) -> Dict[str, Any]:
        """Get approval workflow statistics."""
        
        stats = {
            "total_requests": len(self.active_requests),
            "by_status": {},
            "by_urgency": {},
            "reviewer_workload": {},
            "average_approval_time": None,
            "escalation_rate": 0.0
        }
        
        # Count by status
        escalated_count = 0
        total_completed = 0
        approval_times = []
        
        for request in self.active_requests.values():
            status = request.status.value
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
            
            urgency = request.urgency
            stats["by_urgency"][urgency] = stats["by_urgency"].get(urgency, 0) + 1
            
            if request.status == ApprovalStatus.ESCALATED:
                escalated_count += 1
            
            if request.status in [ApprovalStatus.APPROVED, ApprovalStatus.REJECTED]:
                total_completed += 1
                if request.completed_reviews:
                    completion_time = request.completed_reviews[-1].reviewed_at
                    approval_time = (completion_time - request.created_at).total_seconds()
                    approval_times.append(approval_time)
        
        # Calculate escalation rate
        if total_completed + escalated_count > 0:
            stats["escalation_rate"] = escalated_count / (total_completed + escalated_count)
        
        # Calculate average approval time
        if approval_times:
            stats["average_approval_time"] = sum(approval_times) / len(approval_times)
        
        # Reviewer workload
        for reviewer_id, reviewer_info in self.reviewers.items():
            current_load = self._get_reviewer_current_load(reviewer_id)
            max_load = reviewer_info["max_concurrent"]
            stats["reviewer_workload"][reviewer_id] = {
                "current": current_load,
                "maximum": max_load,
                "utilization": current_load / max_load if max_load > 0 else 0
            }
        
        return stats
    
    def add_notification_callback(self, callback) -> None:
        """Add notification callback for approval events."""
        self.notification_callbacks.append(callback)
    
    async def cleanup_expired_requests(self) -> int:
        """Clean up expired approval requests."""
        
        expired_ids = []
        current_time = datetime.now()
        
        for request_id, request in self.active_requests.items():
            if (request.expires_at and 
                current_time > request.expires_at and 
                request.status == ApprovalStatus.PENDING):
                
                request.status = ApprovalStatus.EXPIRED
                expired_ids.append(request_id)
        
        for request_id in expired_ids:
            del self.active_requests[request_id]
        
        if expired_ids:
            self.logger.info("expired_requests_cleaned", count=len(expired_ids))
        
        return len(expired_ids)