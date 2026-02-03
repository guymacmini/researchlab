"""Tests for HITL (Human-in-the-loop) system."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from src.hitl.checkpoint import (
    HITLCheckpoint, HITLCheckpointManager, CheckpointStatus, 
    CheckpointType, CheckpointContext, CheckpointDecision
)
from src.hitl.approval import (
    ApprovalWorkflow, ApprovalRequest, ApprovalReview,
    ApprovalStatus, ApprovalLevel, ApprovalDecision
)
from src.hitl.annotation import (
    AnnotationSystem, Annotation, AnnotationType,
    AnnotationSeverity, AnnotationStatus, AnnotationSummary
)
from src.agents.base import AgentRole


class TestHITLCheckpoint:
    """Test cases for HITL Checkpoint system."""

    @pytest.fixture
    def sample_context(self):
        """Sample checkpoint context."""
        return CheckpointContext(
            workflow_id="wf_test_123",
            project_id="proj_test_123",
            agent_role=AgentRole.RISK_ANALYST,
            stage="risk_analysis",
            confidence_score=0.35,  # Low confidence
            data_summary={
                "max_risk_score": 0.85,
                "data_quality_warnings": 3
            }
        )

    def test_checkpoint_creation(self, sample_context):
        """Test checkpoint creation and initialization."""
        
        checkpoint = HITLCheckpoint(
            checkpoint_id="cp_test_123",
            checkpoint_type=CheckpointType.RISK_ASSESSMENT_REVIEW,
            context=sample_context,
            timeout_minutes=60
        )
        
        assert checkpoint.checkpoint_id == "cp_test_123"
        assert checkpoint.checkpoint_type == CheckpointType.RISK_ASSESSMENT_REVIEW
        assert checkpoint.status == CheckpointStatus.PENDING
        assert checkpoint.context == sample_context
        assert checkpoint.timeout_minutes == 60
        assert checkpoint.decision is None

    def test_make_decision_success(self, sample_context):
        """Test successful decision making."""
        
        checkpoint = HITLCheckpoint(
            checkpoint_id="cp_test_123",
            checkpoint_type=CheckpointType.RISK_ASSESSMENT_REVIEW,
            context=sample_context
        )
        
        result = checkpoint.make_decision(
            status=CheckpointStatus.APPROVED,
            reviewer="analyst_1",
            comments="Risk assessment looks reasonable",
            confidence_adjustment=0.1
        )
        
        assert result is True
        assert checkpoint.status == CheckpointStatus.APPROVED
        assert checkpoint.decision is not None
        assert checkpoint.decision.reviewer == "analyst_1"
        assert checkpoint.decision.confidence_adjustment == 0.1

    def test_make_decision_already_decided(self, sample_context):
        """Test decision making when checkpoint already decided."""
        
        checkpoint = HITLCheckpoint(
            checkpoint_id="cp_test_123",
            checkpoint_type=CheckpointType.RISK_ASSESSMENT_REVIEW,
            context=sample_context
        )
        
        # Make first decision
        checkpoint.make_decision(CheckpointStatus.APPROVED, "analyst_1")
        
        # Try to make second decision
        result = checkpoint.make_decision(CheckpointStatus.REJECTED, "analyst_2")
        
        assert result is False
        assert checkpoint.status == CheckpointStatus.APPROVED  # Unchanged
        assert checkpoint.decision.reviewer == "analyst_1"  # Original decision

    @pytest.mark.asyncio
    async def test_wait_for_decision(self, sample_context):
        """Test waiting for decision."""
        
        checkpoint = HITLCheckpoint(
            checkpoint_id="cp_test_123",
            checkpoint_type=CheckpointType.RISK_ASSESSMENT_REVIEW,
            context=sample_context,
            timeout_minutes=1  # Short timeout for testing
        )
        
        async def make_decision_later():
            await asyncio.sleep(0.1)
            checkpoint.make_decision(CheckpointStatus.APPROVED, "analyst_1")
        
        # Start decision task
        asyncio.create_task(make_decision_later())
        
        # Wait for decision
        decision = await checkpoint.wait_for_decision()
        
        assert decision.status == CheckpointStatus.APPROVED
        assert decision.reviewer == "analyst_1"

    @pytest.mark.asyncio
    async def test_checkpoint_timeout(self, sample_context):
        """Test checkpoint timeout behavior."""
        
        checkpoint = HITLCheckpoint(
            checkpoint_id="cp_test_123",
            checkpoint_type=CheckpointType.RISK_ASSESSMENT_REVIEW,
            context=sample_context,
            timeout_minutes=0.01  # Very short timeout (0.6 seconds)
        )
        
        with pytest.raises(TimeoutError):
            await checkpoint.wait_for_decision()
        
        assert checkpoint.status == CheckpointStatus.EXPIRED

    def test_get_summary(self, sample_context):
        """Test checkpoint summary generation."""
        
        checkpoint = HITLCheckpoint(
            checkpoint_id="cp_test_123",
            checkpoint_type=CheckpointType.RISK_ASSESSMENT_REVIEW,
            context=sample_context
        )
        
        checkpoint.make_decision(CheckpointStatus.APPROVED, "analyst_1", "Looks good")
        
        summary = checkpoint.get_summary()
        
        assert summary["checkpoint_id"] == "cp_test_123"
        assert summary["type"] == "risk_assessment_review"
        assert summary["status"] == "approved"
        assert summary["decision"]["reviewer"] == "analyst_1"
        assert "time_remaining" in summary


class TestHITLCheckpointManager:
    """Test cases for HITL Checkpoint Manager."""

    @pytest.fixture
    def manager(self):
        """Create checkpoint manager."""
        with patch('src.hitl.checkpoint.DatabaseManager'):
            return HITLCheckpointManager()

    @pytest.fixture
    def sample_context(self):
        """Sample checkpoint context."""
        return CheckpointContext(
            workflow_id="wf_test_123",
            project_id="proj_test_123",
            agent_role=AgentRole.RISK_ANALYST,
            confidence_score=0.35
        )

    def test_manager_initialization(self, manager):
        """Test manager initialization."""
        
        assert len(manager.active_checkpoints) == 0
        assert len(manager.default_timeouts) > 0
        assert len(manager.checkpoint_rules) > 0

    @pytest.mark.asyncio
    async def test_create_checkpoint(self, manager, sample_context):
        """Test checkpoint creation through manager."""
        
        checkpoint = await manager.create_checkpoint(
            CheckpointType.RISK_ASSESSMENT_REVIEW,
            sample_context,
            timeout_minutes=120,
            force=True
        )
        
        assert checkpoint.checkpoint_type == CheckpointType.RISK_ASSESSMENT_REVIEW
        assert checkpoint.timeout_minutes == 120
        assert checkpoint.checkpoint_id in manager.active_checkpoints

    @pytest.mark.asyncio
    async def test_evaluate_checkpoint_needs(self, manager):
        """Test checkpoint needs evaluation."""
        
        # Context that should trigger low confidence rule
        low_confidence_context = CheckpointContext(
            workflow_id="wf_test",
            project_id="proj_test",
            confidence_score=0.3  # Below threshold
        )
        
        needed = await manager.evaluate_checkpoint_needs(low_confidence_context)
        
        assert len(needed) > 0
        assert CheckpointType.AGENT_RESULT_VALIDATION in needed

    def test_get_pending_checkpoints(self, manager, sample_context):
        """Test getting pending checkpoints with filtering."""
        
        # Create test checkpoints
        asyncio.run(manager.create_checkpoint(
            CheckpointType.RISK_ASSESSMENT_REVIEW, 
            sample_context, 
            force=True
        ))
        
        pending = manager.get_pending_checkpoints(workflow_id="wf_test_123")
        
        assert len(pending) == 1
        assert pending[0].status == CheckpointStatus.PENDING

    @pytest.mark.asyncio
    async def test_cleanup_expired_checkpoints(self, manager, sample_context):
        """Test cleanup of expired checkpoints."""
        
        # Create checkpoint with past expiration
        checkpoint = await manager.create_checkpoint(
            CheckpointType.DATA_QUALITY_CHECK,
            sample_context,
            timeout_minutes=-10,  # Already expired
            force=True
        )
        
        cleaned_count = await manager.cleanup_expired_checkpoints()
        
        assert cleaned_count == 1
        assert checkpoint.checkpoint_id not in manager.active_checkpoints

    def test_checkpoint_statistics(self, manager, sample_context):
        """Test checkpoint statistics generation."""
        
        # Add some test checkpoints
        asyncio.run(manager.create_checkpoint(
            CheckpointType.RISK_ASSESSMENT_REVIEW,
            sample_context,
            force=True
        ))
        
        stats = manager.get_checkpoint_statistics()
        
        assert "total_checkpoints" in stats
        assert "by_status" in stats
        assert "by_type" in stats
        assert stats["total_checkpoints"] == 1


class TestApprovalWorkflow:
    """Test cases for Approval Workflow system."""

    @pytest.fixture
    def workflow(self):
        """Create approval workflow."""
        with patch('src.hitl.approval.DatabaseManager'):
            return ApprovalWorkflow()

    @pytest.fixture
    def sample_checkpoint(self):
        """Sample checkpoint for approval."""
        context = CheckpointContext(
            workflow_id="wf_test_123",
            project_id="proj_test_123"
        )
        return HITLCheckpoint(
            checkpoint_id="cp_test_123",
            checkpoint_type=CheckpointType.RESEARCH_PLAN_REVIEW,
            context=context
        )

    def test_workflow_initialization(self, workflow):
        """Test workflow initialization."""
        
        assert len(workflow.active_requests) == 0
        assert len(workflow.reviewers) > 0
        assert len(workflow.approval_rules) > 0

    @pytest.mark.asyncio
    async def test_create_approval_request(self, workflow, sample_checkpoint):
        """Test approval request creation."""
        
        request = await workflow.create_approval_request(
            checkpoint=sample_checkpoint,
            title="Test Approval Request",
            description="Testing approval workflow",
            content={"test": "data"},
            urgency="high"
        )
        
        assert request.checkpoint_id == sample_checkpoint.checkpoint_id
        assert request.title == "Test Approval Request"
        assert request.urgency == "high"
        assert request.status == ApprovalStatus.PENDING
        assert len(request.assigned_reviewers) > 0

    @pytest.mark.asyncio
    async def test_submit_review(self, workflow, sample_checkpoint):
        """Test review submission."""
        
        # Create approval request
        request = await workflow.create_approval_request(
            checkpoint=sample_checkpoint,
            title="Test Request",
            description="Test description",
            content={"test": "data"}
        )
        
        if request.assigned_reviewers:
            reviewer = request.assigned_reviewers[0]
            
            result = await workflow.submit_review(
                request_id=request.request_id,
                reviewer=reviewer,
                decision=ApprovalDecision.APPROVE,
                comments="Looks good to me"
            )
            
            assert result is True
            assert len(request.completed_reviews) == 1
            assert request.completed_reviews[0].decision == ApprovalDecision.APPROVE

    def test_get_pending_requests(self, workflow, sample_checkpoint):
        """Test getting pending requests."""
        
        # Create test request
        asyncio.run(workflow.create_approval_request(
            checkpoint=sample_checkpoint,
            title="Test Request",
            description="Test description",
            content={"test": "data"}
        ))
        
        pending = workflow.get_pending_requests()
        
        assert len(pending) == 1
        assert pending[0].status == ApprovalStatus.PENDING

    def test_approval_statistics(self, workflow):
        """Test approval statistics."""
        
        stats = workflow.get_approval_statistics()
        
        assert "total_requests" in stats
        assert "by_status" in stats
        assert "reviewer_workload" in stats
        assert "escalation_rate" in stats


class TestAnnotationSystem:
    """Test cases for Annotation System."""

    @pytest.fixture
    def annotation_system(self):
        """Create annotation system."""
        with patch('src.hitl.annotation.DatabaseManager'):
            return AnnotationSystem()

    def test_system_initialization(self, annotation_system):
        """Test annotation system initialization."""
        
        assert len(annotation_system.annotations) == 0
        assert len(annotation_system.templates) > 0
        assert "low_confidence_data" in annotation_system.templates

    @pytest.mark.asyncio
    async def test_create_annotation(self, annotation_system):
        """Test annotation creation."""
        
        annotation = await annotation_system.create_annotation(
            target_type="agent_result",
            target_id="result_123",
            annotation_type=AnnotationType.CORRECTION,
            title="Calculation Error",
            description="The ROI calculation appears incorrect",
            annotator="analyst_1",
            severity=AnnotationSeverity.HIGH,
            suggested_correction="Should be 15.2% not 12.5%"
        )
        
        assert annotation.target_type == "agent_result"
        assert annotation.target_id == "result_123"
        assert annotation.type == AnnotationType.CORRECTION
        assert annotation.severity == AnnotationSeverity.HIGH
        assert annotation.status == AnnotationStatus.OPEN
        assert annotation.annotator == "analyst_1"

    @pytest.mark.asyncio
    async def test_create_from_template(self, annotation_system):
        """Test creating annotation from template."""
        
        annotation = await annotation_system.create_from_template(
            template_name="calculation_error",
            target_type="agent_result",
            target_id="result_123",
            annotator="analyst_1",
            template_vars={
                "calculation": "ROI",
                "expected": "15.2%",
                "actual": "12.5%"
            }
        )
        
        assert annotation.type == AnnotationType.CORRECTION
        assert annotation.severity == AnnotationSeverity.HIGH
        assert "ROI" in annotation.description
        assert "15.2%" in annotation.description

    @pytest.mark.asyncio
    async def test_update_annotation(self, annotation_system):
        """Test annotation updates."""
        
        # Create annotation
        annotation = await annotation_system.create_annotation(
            target_type="agent_result",
            target_id="result_123",
            annotation_type=AnnotationType.VALIDATION,
            title="Test Annotation",
            description="Test description",
            annotator="analyst_1"
        )
        
        # Update annotation
        result = await annotation_system.update_annotation(
            annotation.annotation_id,
            status=AnnotationStatus.RESOLVED,
            resolution_notes="Issue has been fixed"
        )
        
        assert result is True
        assert annotation.status == AnnotationStatus.RESOLVED
        assert annotation.resolution_notes == "Issue has been fixed"
        assert annotation.resolved_at is not None

    def test_get_annotations_with_filtering(self, annotation_system):
        """Test getting annotations with filters."""
        
        # Create test annotations
        asyncio.run(annotation_system.create_annotation(
            target_type="workflow",
            target_id="wf_123",
            annotation_type=AnnotationType.CORRECTION,
            title="Test 1",
            description="Test description 1",
            annotator="analyst_1",
            severity=AnnotationSeverity.HIGH
        ))
        
        asyncio.run(annotation_system.create_annotation(
            target_type="agent_result",
            target_id="result_456",
            annotation_type=AnnotationType.SUGGESTION,
            title="Test 2",
            description="Test description 2",
            annotator="analyst_2",
            severity=AnnotationSeverity.LOW
        ))
        
        # Test filtering by type
        corrections = annotation_system.get_annotations(
            annotation_type=AnnotationType.CORRECTION
        )
        assert len(corrections) == 1
        assert corrections[0].type == AnnotationType.CORRECTION
        
        # Test filtering by severity
        high_severity = annotation_system.get_annotations(
            severity=AnnotationSeverity.HIGH
        )
        assert len(high_severity) == 1
        assert high_severity[0].severity == AnnotationSeverity.HIGH
        
        # Test filtering by target_type
        workflow_annotations = annotation_system.get_annotations(
            target_type="workflow"
        )
        assert len(workflow_annotations) == 1
        assert workflow_annotations[0].target_type == "workflow"

    def test_get_annotation_summary(self, annotation_system):
        """Test annotation summary generation."""
        
        target_id = "test_target_123"
        
        # Create multiple annotations for same target
        asyncio.run(annotation_system.create_annotation(
            target_type="workflow",
            target_id=target_id,
            annotation_type=AnnotationType.CORRECTION,
            title="Error 1",
            description="Description 1",
            annotator="analyst_1",
            severity=AnnotationSeverity.CRITICAL
        ))
        
        asyncio.run(annotation_system.create_annotation(
            target_type="workflow",
            target_id=target_id,
            annotation_type=AnnotationType.SUGGESTION,
            title="Suggestion 1",
            description="Description 2",
            annotator="analyst_2",
            severity=AnnotationSeverity.MEDIUM
        ))
        
        summary = annotation_system.get_annotation_summary(target_id, "workflow")
        
        assert summary.target_id == target_id
        assert summary.total_annotations == 2
        assert summary.critical_issues == 1
        assert summary.open_issues == 2
        assert "correction" in summary.by_type
        assert "suggestion" in summary.by_type

    def test_search_annotations(self, annotation_system):
        """Test annotation search functionality."""
        
        # Create annotations with searchable content
        asyncio.run(annotation_system.create_annotation(
            target_type="workflow",
            target_id="wf_123",
            annotation_type=AnnotationType.CORRECTION,
            title="Calculation Error in ROI",
            description="The return on investment calculation is incorrect",
            annotator="analyst_1",
            tags=["calculation", "roi", "error"]
        ))
        
        asyncio.run(annotation_system.create_annotation(
            target_type="agent_result",
            target_id="result_456",
            annotation_type=AnnotationType.SUGGESTION,
            title="Data Quality Issue",
            description="Consider using more recent data sources",
            annotator="analyst_2",
            tags=["data", "quality", "sources"]
        ))
        
        # Search by title
        roi_results = annotation_system.search_annotations("ROI")
        assert len(roi_results) == 1
        assert "ROI" in roi_results[0].title
        
        # Search by description
        data_results = annotation_system.search_annotations("data")
        assert len(data_results) == 1
        assert "data" in data_results[0].description
        
        # Search by tags
        quality_results = annotation_system.search_annotations("quality")
        assert len(quality_results) == 1
        assert "quality" in quality_results[0].tags

    def test_system_statistics(self, annotation_system):
        """Test system statistics generation."""
        
        # Create test annotations
        asyncio.run(annotation_system.create_annotation(
            target_type="workflow",
            target_id="wf_123",
            annotation_type=AnnotationType.CORRECTION,
            title="Test 1",
            description="Test description 1",
            annotator="analyst_1",
            severity=AnnotationSeverity.HIGH
        ))
        
        asyncio.run(annotation_system.update_annotation(
            list(annotation_system.annotations.keys())[0],
            status=AnnotationStatus.RESOLVED
        ))
        
        stats = annotation_system.get_system_statistics()
        
        assert stats["total_annotations"] == 1
        assert "by_type" in stats
        assert "by_severity" in stats
        assert "by_status" in stats
        assert "resolution_rate" in stats
        assert stats["resolution_rate"] == 1.0  # 100% resolved

    @pytest.mark.asyncio
    async def test_bulk_create_annotations(self, annotation_system):
        """Test bulk annotation creation."""
        
        annotations_data = [
            {
                "target_type": "workflow",
                "target_id": "wf_123",
                "annotation_type": AnnotationType.CORRECTION,
                "title": "Error 1",
                "description": "Description 1",
                "annotator": "analyst_1"
            },
            {
                "target_type": "agent_result",
                "target_id": "result_456",
                "annotation_type": AnnotationType.SUGGESTION,
                "title": "Suggestion 1",
                "description": "Description 2",
                "annotator": "analyst_2"
            }
        ]
        
        created = await annotation_system.bulk_create_annotations(annotations_data)
        
        assert len(created) == 2
        assert len(annotation_system.annotations) == 2

    @pytest.mark.asyncio
    async def test_export_annotations(self, annotation_system):
        """Test annotation export."""
        
        # Create test annotation
        await annotation_system.create_annotation(
            target_type="workflow",
            target_id="wf_123",
            annotation_type=AnnotationType.CORRECTION,
            title="Test Annotation",
            description="Test description",
            annotator="analyst_1"
        )
        
        export_data = await annotation_system.export_annotations()
        
        assert "export_timestamp" in export_data
        assert "total_annotations" in export_data
        assert "annotations" in export_data
        assert len(export_data["annotations"]) == 1

    @pytest.mark.asyncio
    async def test_analyze_annotation_patterns(self, annotation_system):
        """Test annotation pattern analysis."""
        
        # Create diverse annotations for pattern analysis
        await annotation_system.create_annotation(
            target_type="workflow",
            target_id="wf_123",
            annotation_type=AnnotationType.CORRECTION,
            title="Error 1",
            description="Description 1",
            annotator="analyst_1",
            severity=AnnotationSeverity.HIGH
        )
        
        await annotation_system.create_annotation(
            target_type="agent_result",
            target_id="result_456",
            annotation_type=AnnotationType.CORRECTION,
            title="Error 2",
            description="Description 2",
            annotator="analyst_1",
            severity=AnnotationSeverity.MEDIUM
        )
        
        patterns = await annotation_system.analyze_annotation_patterns()
        
        assert "most_common_issues" in patterns
        assert "annotator_patterns" in patterns
        assert "quality_indicators" in patterns
        assert patterns["most_common_issues"]["correction"] == 2
        assert "analyst_1" in patterns["annotator_patterns"]


class TestHITLIntegration:
    """Integration tests for HITL components."""

    @pytest.mark.asyncio
    async def test_checkpoint_to_approval_workflow(self):
        """Test integration between checkpoints and approval workflow."""
        
        with patch('src.hitl.checkpoint.DatabaseManager'):
            with patch('src.hitl.approval.DatabaseManager'):
                
                # Create checkpoint manager and approval workflow
                checkpoint_manager = HITLCheckpointManager()
                approval_workflow = ApprovalWorkflow()
                
                # Create context that triggers checkpoint
                context = CheckpointContext(
                    workflow_id="wf_integration_test",
                    project_id="proj_integration_test",
                    confidence_score=0.2  # Very low confidence
                )
                
                # Create checkpoint
                checkpoint = await checkpoint_manager.create_checkpoint(
                    CheckpointType.AGENT_RESULT_VALIDATION,
                    context,
                    force=True
                )
                
                # Create approval request for checkpoint
                approval_request = await approval_workflow.create_approval_request(
                    checkpoint=checkpoint,
                    title="Low Confidence Result Review",
                    description="Agent result has very low confidence score",
                    content={"confidence": 0.2, "result": "test_data"}
                )
                
                assert approval_request.checkpoint_id == checkpoint.checkpoint_id
                assert approval_request.status == ApprovalStatus.PENDING

    def test_hitl_system_coordination(self):
        """Test coordination between all HITL components."""
        
        with patch('src.hitl.checkpoint.DatabaseManager'):
            with patch('src.hitl.approval.DatabaseManager'):
                with patch('src.hitl.annotation.DatabaseManager'):
                    
                    # Initialize all systems
                    checkpoint_manager = HITLCheckpointManager()
                    approval_workflow = ApprovalWorkflow()
                    annotation_system = AnnotationSystem()
                    
                    # Simulate workflow scenario
                    context = CheckpointContext(
                        workflow_id="wf_coord_test",
                        project_id="proj_coord_test",
                        agent_role=AgentRole.RISK_ANALYST,
                        confidence_score=0.3,
                        data_summary={"quality_warnings": 5}
                    )
                    
                    # Should trigger multiple checkpoint types
                    needed_checkpoints = asyncio.run(
                        checkpoint_manager.evaluate_checkpoint_needs(context)
                    )
                    
                    assert len(needed_checkpoints) > 0
                    
                    # Create annotation for the same target
                    annotation = asyncio.run(annotation_system.create_annotation(
                        target_type="workflow",
                        target_id="wf_coord_test",
                        annotation_type=AnnotationType.QUALITY_FLAG,
                        title="Multiple Data Quality Issues",
                        description="Several quality warnings detected",
                        annotator="system"
                    ))
                    
                    # Verify systems are tracking related content
                    assert annotation.target_id == context.workflow_id
                    assert len(checkpoint_manager.checkpoint_rules) > 0
                    assert len(approval_workflow.approval_rules) > 0