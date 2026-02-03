"""Annotation system for HITL feedback and improvements."""

from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import DatabaseManager
from src.agents.base import AgentRole

logger = structlog.get_logger()


class AnnotationType(Enum):
    """Types of annotations."""
    CORRECTION = "correction"
    SUGGESTION = "suggestion"
    VALIDATION = "validation"
    QUALITY_FLAG = "quality_flag"
    CONFIDENCE_ADJUSTMENT = "confidence_adjustment"
    METHODOLOGY_NOTE = "methodology_note"
    DATA_SOURCE_NOTE = "data_source_note"
    FOLLOW_UP = "follow_up"


class AnnotationSeverity(Enum):
    """Severity levels for annotations."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnnotationStatus(Enum):
    """Status of annotation resolution."""
    OPEN = "open"
    IN_REVIEW = "in_review"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


@dataclass
class Annotation:
    """Individual annotation on research content."""
    annotation_id: str
    type: AnnotationType
    severity: AnnotationSeverity
    status: AnnotationStatus
    
    # Content reference
    target_type: str  # "workflow", "agent_result", "data_point", "recommendation"
    target_id: str
    target_path: Optional[str] = None  # JSON path for specific content
    
    # Annotation content
    title: str = ""
    description: str = ""
    suggested_correction: Optional[str] = None
    supporting_data: Dict[str, Any] = field(default_factory=dict)
    
    # Attribution
    annotator: str = ""
    annotator_type: str = "human"  # "human", "system", "agent"
    created_at: datetime = field(default_factory=datetime.now)
    
    # Resolution tracking
    assigned_to: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    
    # Impact tracking
    confidence_impact: Optional[float] = None
    quality_impact: Optional[str] = None
    
    # Tags and metadata
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnnotationSummary:
    """Summary of annotations for an entity."""
    target_type: str
    target_id: str
    total_annotations: int
    by_type: Dict[str, int] = field(default_factory=dict)
    by_severity: Dict[str, int] = field(default_factory=dict)
    by_status: Dict[str, int] = field(default_factory=dict)
    avg_confidence_impact: Optional[float] = None
    critical_issues: int = 0
    open_issues: int = 0


class AnnotationSystem:
    """
    System for managing human annotations on research content.
    
    Enables humans to provide feedback, corrections, and improvements
    to AI-generated research analysis and recommendations.
    """
    
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.logger = logger.bind(component="annotation_system")
        
        # In-memory storage (would use database in production)
        self.annotations: Dict[str, Annotation] = {}
        
        # Indexing for efficient queries
        self.by_target: Dict[str, List[str]] = {}  # target_id -> annotation_ids
        self.by_annotator: Dict[str, List[str]] = {}  # annotator -> annotation_ids
        self.by_type: Dict[AnnotationType, List[str]] = {}
        
        # Quality metrics tracking
        self.quality_metrics: Dict[str, Any] = {}
        
        # Annotation templates
        self.templates = self._initialize_templates()
        
    def _initialize_templates(self) -> Dict[str, Dict[str, Any]]:
        """Initialize annotation templates for common scenarios."""
        
        return {
            "low_confidence_data": {
                "type": AnnotationType.QUALITY_FLAG,
                "severity": AnnotationSeverity.MEDIUM,
                "title": "Low Confidence Data Source",
                "description_template": "Data from {source} has reliability concerns: {details}",
                "tags": ["data-quality", "reliability"]
            },
            "methodology_suggestion": {
                "type": AnnotationType.SUGGESTION,
                "severity": AnnotationSeverity.LOW,
                "title": "Methodology Improvement Suggestion",
                "description_template": "Consider alternative approach: {suggestion}",
                "tags": ["methodology", "improvement"]
            },
            "calculation_error": {
                "type": AnnotationType.CORRECTION,
                "severity": AnnotationSeverity.HIGH,
                "title": "Calculation Error Detected",
                "description_template": "Error in {calculation}: Expected {expected}, Got {actual}",
                "tags": ["calculation", "error", "correction"]
            },
            "missing_context": {
                "type": AnnotationType.VALIDATION,
                "severity": AnnotationSeverity.MEDIUM,
                "title": "Missing Context",
                "description_template": "Analysis lacks important context: {missing_context}",
                "tags": ["context", "validation", "completeness"]
            },
            "confidence_override": {
                "type": AnnotationType.CONFIDENCE_ADJUSTMENT,
                "severity": AnnotationSeverity.MEDIUM,
                "title": "Confidence Score Override",
                "description_template": "Confidence should be {new_confidence} because {reasoning}",
                "tags": ["confidence", "override"]
            }
        }
    
    async def create_annotation(self,
                              target_type: str,
                              target_id: str,
                              annotation_type: AnnotationType,
                              title: str,
                              description: str,
                              annotator: str,
                              severity: AnnotationSeverity = AnnotationSeverity.MEDIUM,
                              target_path: Optional[str] = None,
                              suggested_correction: Optional[str] = None,
                              confidence_impact: Optional[float] = None,
                              tags: Optional[List[str]] = None) -> Annotation:
        """
        Create a new annotation.
        
        Args:
            target_type: Type of content being annotated
            target_id: ID of the target content
            annotation_type: Type of annotation
            title: Brief title for annotation
            description: Detailed description
            annotator: Person/system making annotation
            severity: Severity level
            target_path: Specific path within content (optional)
            suggested_correction: Suggested fix (optional)
            confidence_impact: Impact on confidence score (optional)
            tags: Additional tags (optional)
        """
        
        annotation_id = f"ann_{uuid.uuid4()}"
        
        annotation = Annotation(
            annotation_id=annotation_id,
            type=annotation_type,
            severity=severity,
            status=AnnotationStatus.OPEN,
            target_type=target_type,
            target_id=target_id,
            target_path=target_path,
            title=title,
            description=description,
            suggested_correction=suggested_correction,
            annotator=annotator,
            confidence_impact=confidence_impact,
            tags=tags or []
        )
        
        # Store annotation
        self.annotations[annotation_id] = annotation
        
        # Update indices
        self._update_indices(annotation)
        
        self.logger.info("annotation_created",
                        annotation_id=annotation_id,
                        type=annotation_type.value,
                        severity=severity.value,
                        target_type=target_type,
                        target_id=target_id,
                        annotator=annotator)
        
        return annotation
    
    def _update_indices(self, annotation: Annotation) -> None:
        """Update indices for efficient querying."""
        
        # By target
        if annotation.target_id not in self.by_target:
            self.by_target[annotation.target_id] = []
        self.by_target[annotation.target_id].append(annotation.annotation_id)
        
        # By annotator
        if annotation.annotator not in self.by_annotator:
            self.by_annotator[annotation.annotator] = []
        self.by_annotator[annotation.annotator].append(annotation.annotation_id)
        
        # By type
        if annotation.type not in self.by_type:
            self.by_type[annotation.type] = []
        self.by_type[annotation.type].append(annotation.annotation_id)
    
    async def create_from_template(self,
                                 template_name: str,
                                 target_type: str,
                                 target_id: str,
                                 annotator: str,
                                 template_vars: Dict[str, Any],
                                 **kwargs) -> Annotation:
        """Create annotation from predefined template."""
        
        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found")
        
        template = self.templates[template_name]
        
        # Format description with variables
        description = template["description_template"].format(**template_vars)
        
        return await self.create_annotation(
            target_type=target_type,
            target_id=target_id,
            annotation_type=AnnotationType(template["type"]),
            title=template["title"],
            description=description,
            annotator=annotator,
            severity=AnnotationSeverity(template["severity"]),
            tags=template.get("tags", []),
            **kwargs
        )
    
    def get_annotations(self,
                       target_type: Optional[str] = None,
                       target_id: Optional[str] = None,
                       annotation_type: Optional[AnnotationType] = None,
                       annotator: Optional[str] = None,
                       status: Optional[AnnotationStatus] = None,
                       severity: Optional[AnnotationSeverity] = None,
                       limit: Optional[int] = None) -> List[Annotation]:
        """Get annotations with optional filtering."""
        
        annotations = list(self.annotations.values())
        
        # Apply filters
        if target_type:
            annotations = [a for a in annotations if a.target_type == target_type]
        
        if target_id:
            annotations = [a for a in annotations if a.target_id == target_id]
        
        if annotation_type:
            annotations = [a for a in annotations if a.type == annotation_type]
        
        if annotator:
            annotations = [a for a in annotations if a.annotator == annotator]
        
        if status:
            annotations = [a for a in annotations if a.status == status]
        
        if severity:
            annotations = [a for a in annotations if a.severity == severity]
        
        # Sort by creation time (newest first)
        annotations.sort(key=lambda a: a.created_at, reverse=True)
        
        # Apply limit
        if limit:
            annotations = annotations[:limit]
        
        return annotations
    
    def get_annotation(self, annotation_id: str) -> Optional[Annotation]:
        """Get specific annotation by ID."""
        return self.annotations.get(annotation_id)
    
    async def update_annotation(self,
                              annotation_id: str,
                              status: Optional[AnnotationStatus] = None,
                              assigned_to: Optional[str] = None,
                              resolution_notes: Optional[str] = None,
                              **updates) -> bool:
        """Update annotation fields."""
        
        annotation = self.annotations.get(annotation_id)
        if not annotation:
            self.logger.error("annotation_not_found", annotation_id=annotation_id)
            return False
        
        # Update fields
        if status is not None:
            annotation.status = status
            if status == AnnotationStatus.RESOLVED:
                annotation.resolved_at = datetime.now()
        
        if assigned_to is not None:
            annotation.assigned_to = assigned_to
        
        if resolution_notes is not None:
            annotation.resolution_notes = resolution_notes
        
        # Update other fields
        for field, value in updates.items():
            if hasattr(annotation, field):
                setattr(annotation, field, value)
        
        self.logger.info("annotation_updated",
                        annotation_id=annotation_id,
                        status=annotation.status.value if status else None)
        
        return True
    
    def get_annotation_summary(self, target_id: str, target_type: Optional[str] = None) -> AnnotationSummary:
        """Get summary of annotations for a target."""
        
        annotations = self.get_annotations(target_id=target_id, target_type=target_type)
        
        summary = AnnotationSummary(
            target_type=target_type or "unknown",
            target_id=target_id,
            total_annotations=len(annotations)
        )
        
        # Count by categories
        for annotation in annotations:
            # By type
            type_name = annotation.type.value
            summary.by_type[type_name] = summary.by_type.get(type_name, 0) + 1
            
            # By severity
            severity_name = annotation.severity.value
            summary.by_severity[severity_name] = summary.by_severity.get(severity_name, 0) + 1
            
            # By status
            status_name = annotation.status.value
            summary.by_status[status_name] = summary.by_status.get(status_name, 0) + 1
            
            # Count critical and open issues
            if annotation.severity == AnnotationSeverity.CRITICAL:
                summary.critical_issues += 1
            
            if annotation.status == AnnotationStatus.OPEN:
                summary.open_issues += 1
        
        # Calculate average confidence impact
        confidence_impacts = [a.confidence_impact for a in annotations if a.confidence_impact is not None]
        if confidence_impacts:
            summary.avg_confidence_impact = sum(confidence_impacts) / len(confidence_impacts)
        
        return summary
    
    def get_system_statistics(self) -> Dict[str, Any]:
        """Get system-wide annotation statistics."""
        
        stats = {
            "total_annotations": len(self.annotations),
            "by_type": {},
            "by_severity": {},
            "by_status": {},
            "by_annotator": {},
            "resolution_rate": 0.0,
            "avg_resolution_time": None,
            "critical_open": 0,
            "quality_trends": {}
        }
        
        resolution_times = []
        total_resolved = 0
        
        for annotation in self.annotations.values():
            # Count by type
            type_name = annotation.type.value
            stats["by_type"][type_name] = stats["by_type"].get(type_name, 0) + 1
            
            # Count by severity
            severity_name = annotation.severity.value
            stats["by_severity"][severity_name] = stats["by_severity"].get(severity_name, 0) + 1
            
            # Count by status
            status_name = annotation.status.value
            stats["by_status"][status_name] = stats["by_status"].get(status_name, 0) + 1
            
            # Count by annotator
            stats["by_annotator"][annotation.annotator] = stats["by_annotator"].get(annotation.annotator, 0) + 1
            
            # Resolution tracking
            if annotation.status == AnnotationStatus.RESOLVED:
                total_resolved += 1
                if annotation.resolved_at:
                    resolution_time = (annotation.resolved_at - annotation.created_at).total_seconds()
                    resolution_times.append(resolution_time)
            
            # Critical open issues
            if (annotation.severity == AnnotationSeverity.CRITICAL and 
                annotation.status == AnnotationStatus.OPEN):
                stats["critical_open"] += 1
        
        # Calculate resolution rate
        if len(self.annotations) > 0:
            stats["resolution_rate"] = total_resolved / len(self.annotations)
        
        # Calculate average resolution time
        if resolution_times:
            stats["avg_resolution_time"] = sum(resolution_times) / len(resolution_times)
        
        return stats
    
    async def bulk_create_annotations(self, annotations_data: List[Dict[str, Any]]) -> List[Annotation]:
        """Create multiple annotations in bulk."""
        
        created_annotations = []
        
        for annotation_data in annotations_data:
            try:
                annotation = await self.create_annotation(**annotation_data)
                created_annotations.append(annotation)
            except Exception as e:
                self.logger.error("bulk_annotation_creation_failed",
                                error=str(e), data=annotation_data)
        
        self.logger.info("bulk_annotations_created", 
                        total=len(annotations_data),
                        successful=len(created_annotations))
        
        return created_annotations
    
    def search_annotations(self, query: str, fields: List[str] = None) -> List[Annotation]:
        """Search annotations by text query."""
        
        if fields is None:
            fields = ["title", "description", "tags"]
        
        query_lower = query.lower()
        matching_annotations = []
        
        for annotation in self.annotations.values():
            match_found = False
            
            for field in fields:
                if field == "title" and query_lower in annotation.title.lower():
                    match_found = True
                elif field == "description" and query_lower in annotation.description.lower():
                    match_found = True
                elif field == "tags" and any(query_lower in tag.lower() for tag in annotation.tags):
                    match_found = True
            
            if match_found:
                matching_annotations.append(annotation)
        
        return matching_annotations
    
    def add_template(self, name: str, template_config: Dict[str, Any]) -> None:
        """Add custom annotation template."""
        
        required_fields = ["type", "severity", "title", "description_template"]
        
        for field in required_fields:
            if field not in template_config:
                raise ValueError(f"Template missing required field: {field}")
        
        self.templates[name] = template_config
        
        self.logger.info("annotation_template_added", name=name)
    
    async def export_annotations(self,
                               target_id: Optional[str] = None,
                               format: str = "json") -> Dict[str, Any]:
        """Export annotations for backup or analysis."""
        
        annotations_to_export = self.get_annotations(target_id=target_id) if target_id else list(self.annotations.values())
        
        export_data = {
            "export_timestamp": datetime.now().isoformat(),
            "total_annotations": len(annotations_to_export),
            "target_id": target_id,
            "annotations": []
        }
        
        for annotation in annotations_to_export:
            annotation_dict = {
                "annotation_id": annotation.annotation_id,
                "type": annotation.type.value,
                "severity": annotation.severity.value,
                "status": annotation.status.value,
                "target_type": annotation.target_type,
                "target_id": annotation.target_id,
                "target_path": annotation.target_path,
                "title": annotation.title,
                "description": annotation.description,
                "suggested_correction": annotation.suggested_correction,
                "annotator": annotation.annotator,
                "created_at": annotation.created_at.isoformat(),
                "resolved_at": annotation.resolved_at.isoformat() if annotation.resolved_at else None,
                "tags": annotation.tags,
                "confidence_impact": annotation.confidence_impact
            }
            export_data["annotations"].append(annotation_dict)
        
        return export_data
    
    async def analyze_annotation_patterns(self) -> Dict[str, Any]:
        """Analyze patterns in annotations for insights."""
        
        analysis = {
            "most_common_issues": {},
            "annotator_patterns": {},
            "target_patterns": {},
            "temporal_patterns": {},
            "quality_indicators": {}
        }
        
        # Most common issue types
        type_counts = {}
        for annotation in self.annotations.values():
            type_name = annotation.type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        
        analysis["most_common_issues"] = dict(sorted(type_counts.items(), 
                                                   key=lambda x: x[1], reverse=True))
        
        # Annotator patterns
        for annotator, annotation_ids in self.by_annotator.items():
            annotations = [self.annotations[aid] for aid in annotation_ids]
            
            analysis["annotator_patterns"][annotator] = {
                "total_annotations": len(annotations),
                "most_common_type": max(set(a.type.value for a in annotations), 
                                      key=lambda t: sum(1 for a in annotations if a.type.value == t)),
                "avg_severity": sum(["info", "low", "medium", "high", "critical"].index(a.severity.value) 
                                  for a in annotations) / len(annotations) if annotations else 0
            }
        
        # Quality trends (simplified)
        recent_annotations = [a for a in self.annotations.values() 
                            if (datetime.now() - a.created_at).days <= 7]
        
        analysis["quality_indicators"] = {
            "recent_annotation_rate": len(recent_annotations),
            "critical_issues_rate": len([a for a in recent_annotations 
                                       if a.severity == AnnotationSeverity.CRITICAL]),
            "avg_confidence_impact": sum(a.confidence_impact for a in recent_annotations 
                                       if a.confidence_impact) / len([a for a in recent_annotations 
                                                                     if a.confidence_impact]) if recent_annotations else 0
        }
        
        return analysis