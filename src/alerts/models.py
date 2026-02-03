"""Alert system models and data structures."""

from enum import Enum
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union
from uuid import uuid4

from pydantic import BaseModel, Field

from src.core.logging import get_logger


logger = get_logger(__name__)


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertStatus(str, Enum):
    """Alert status."""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertChannel(str, Enum):
    """Alert delivery channels."""
    EMAIL = "email"
    WEBHOOK = "webhook"
    SLACK = "slack"
    SMS = "sms"
    DISCORD = "discord"
    TEAMS = "teams"


class Alert(BaseModel):
    """Core alert model."""
    
    # Identifiers
    alert_id: str = Field(default_factory=lambda: f"alert_{uuid4().hex[:8]}")
    rule_id: Optional[str] = Field(default=None, description="Rule that triggered this alert")
    
    # Content
    title: str = Field(..., description="Alert title")
    message: str = Field(..., description="Alert message body")
    severity: AlertSeverity = Field(..., description="Alert severity level")
    
    # Context
    source: str = Field(..., description="Source system/component")
    category: str = Field(..., description="Alert category (price, news, system, etc.)")
    
    # Related data
    symbol: Optional[str] = Field(default=None, description="Related stock symbol")
    project_id: Optional[str] = Field(default=None, description="Related research project")
    workflow_id: Optional[str] = Field(default=None, description="Related workflow")
    
    # Metadata
    data: Dict[str, Any] = Field(default_factory=dict, description="Additional alert data")
    tags: List[str] = Field(default_factory=list, description="Alert tags")
    
    # Delivery
    channels: List[AlertChannel] = Field(..., description="Delivery channels")
    recipients: List[str] = Field(default_factory=list, description="Recipient addresses/IDs")
    
    # Timing
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = Field(default=None, description="Alert expiration")
    
    # Status tracking
    status: AlertStatus = Field(default=AlertStatus.PENDING)
    delivery_attempts: int = Field(default=0)
    last_attempt: Optional[datetime] = Field(default=None)
    delivered_at: Optional[datetime] = Field(default=None)
    acknowledged_at: Optional[datetime] = Field(default=None)
    resolved_at: Optional[datetime] = Field(default=None)
    
    # Error handling
    error_message: Optional[str] = Field(default=None)
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=3)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
    
    def is_expired(self) -> bool:
        """Check if alert has expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    def can_retry(self) -> bool:
        """Check if alert can be retried."""
        return (
            self.retry_count < self.max_retries and
            self.status in [AlertStatus.PENDING, AlertStatus.FAILED] and
            not self.is_expired()
        )
    
    def add_delivery_attempt(self, success: bool, error: Optional[str] = None):
        """Record a delivery attempt."""
        self.delivery_attempts += 1
        self.last_attempt = datetime.now()
        
        if success:
            self.status = AlertStatus.SENT
            self.delivered_at = datetime.now()
            self.error_message = None
        else:
            self.retry_count += 1
            self.status = AlertStatus.FAILED
            self.error_message = error
    
    def acknowledge(self, user_id: Optional[str] = None):
        """Mark alert as acknowledged."""
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_at = datetime.now()
        if user_id:
            self.data["acknowledged_by"] = user_id
    
    def resolve(self, user_id: Optional[str] = None, resolution: Optional[str] = None):
        """Mark alert as resolved."""
        self.status = AlertStatus.RESOLVED
        self.resolved_at = datetime.now()
        if user_id:
            self.data["resolved_by"] = user_id
        if resolution:
            self.data["resolution"] = resolution


class AlertRule(BaseModel):
    """Base alert rule configuration."""
    
    # Identifiers
    rule_id: str = Field(default_factory=lambda: f"rule_{uuid4().hex[:8]}")
    name: str = Field(..., description="Rule name")
    description: Optional[str] = Field(default=None)
    
    # Configuration
    enabled: bool = Field(default=True)
    severity: AlertSeverity = Field(default=AlertSeverity.MEDIUM)
    channels: List[AlertChannel] = Field(..., description="Delivery channels")
    recipients: List[str] = Field(..., description="Recipient addresses")
    
    # Conditions
    conditions: Dict[str, Any] = Field(default_factory=dict, description="Rule conditions")
    
    # Rate limiting
    cooldown_minutes: int = Field(default=60, description="Cooldown between alerts")
    max_alerts_per_hour: int = Field(default=10)
    max_alerts_per_day: int = Field(default=50)
    
    # Timing
    active_hours: Optional[List[int]] = Field(default=None, description="Active hours (0-23)")
    active_days: Optional[List[int]] = Field(default=None, description="Active days (0-6, Mon=0)")
    timezone: str = Field(default="UTC")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    created_by: Optional[str] = Field(default=None)
    
    # Statistics
    alert_count: int = Field(default=0)
    last_triggered: Optional[datetime] = Field(default=None)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
    
    def is_active(self) -> bool:
        """Check if rule is currently active based on time constraints."""
        if not self.enabled:
            return False
        
        now = datetime.now()
        
        # Check active hours
        if self.active_hours is not None:
            if now.hour not in self.active_hours:
                return False
        
        # Check active days
        if self.active_days is not None:
            if now.weekday() not in self.active_days:
                return False
        
        return True
    
    def can_trigger(self) -> bool:
        """Check if rule can trigger based on rate limits."""
        if not self.is_active():
            return False
        
        now = datetime.now()
        
        # Check cooldown
        if self.last_triggered:
            cooldown_expires = self.last_triggered + timedelta(minutes=self.cooldown_minutes)
            if now < cooldown_expires:
                return False
        
        # Additional rate limiting would be checked by AlertManager
        return True
    
    def update_trigger_stats(self):
        """Update rule statistics when triggered."""
        self.alert_count += 1
        self.last_triggered = datetime.now()
        self.updated_at = datetime.now()


class AlertTemplate(BaseModel):
    """Template for generating alerts."""
    
    template_id: str = Field(default_factory=lambda: f"template_{uuid4().hex[:8]}")
    name: str = Field(..., description="Template name")
    description: Optional[str] = Field(default=None)
    
    # Template content
    title_template: str = Field(..., description="Title template with placeholders")
    message_template: str = Field(..., description="Message template with placeholders")
    
    # Default settings
    default_severity: AlertSeverity = Field(default=AlertSeverity.MEDIUM)
    default_channels: List[AlertChannel] = Field(default_factory=list)
    default_category: str = Field(default="general")
    
    # Template variables
    required_variables: List[str] = Field(default_factory=list)
    optional_variables: List[str] = Field(default_factory=list)
    
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: Optional[str] = Field(default=None)
    
    def render(self, variables: Dict[str, Any]) -> Dict[str, str]:
        """Render template with provided variables."""
        try:
            # Check required variables
            missing = [var for var in self.required_variables if var not in variables]
            if missing:
                raise ValueError(f"Missing required variables: {missing}")
            
            # Render templates
            title = self.title_template.format(**variables)
            message = self.message_template.format(**variables)
            
            return {"title": title, "message": message}
        
        except KeyError as e:
            raise ValueError(f"Template variable not provided: {e}")
        except Exception as e:
            raise ValueError(f"Template rendering error: {e}")


class AlertDeliveryResult(BaseModel):
    """Result of alert delivery attempt."""
    
    alert_id: str
    channel: AlertChannel
    recipient: str
    success: bool
    delivered_at: datetime
    
    # Response details
    response_code: Optional[int] = Field(default=None)
    response_message: Optional[str] = Field(default=None)
    response_data: Dict[str, Any] = Field(default_factory=dict)
    
    # Error details
    error_type: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    
    # Timing
    delivery_duration_ms: Optional[float] = Field(default=None)
    
    def __str__(self):
        status = "✅" if self.success else "❌"
        return f"{status} {self.channel.value} to {self.recipient}: {self.response_message or self.error_message}"


class AlertBatch(BaseModel):
    """Batch of alerts for processing."""
    
    batch_id: str = Field(default_factory=lambda: f"batch_{uuid4().hex[:8]}")
    alerts: List[Alert] = Field(default_factory=list)
    
    # Processing status
    status: str = Field(default="pending")  # pending, processing, completed, failed
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    
    # Results
    successful_deliveries: int = Field(default=0)
    failed_deliveries: int = Field(default=0)
    delivery_results: List[AlertDeliveryResult] = Field(default_factory=list)
    
    def add_alert(self, alert: Alert):
        """Add alert to batch."""
        self.alerts.append(alert)
    
    def start_processing(self):
        """Mark batch as started."""
        self.status = "processing"
        self.started_at = datetime.now()
    
    def complete_processing(self):
        """Mark batch as completed."""
        self.status = "completed"
        self.completed_at = datetime.now()
        
        # Calculate statistics
        self.successful_deliveries = len([r for r in self.delivery_results if r.success])
        self.failed_deliveries = len([r for r in self.delivery_results if not r.success])
    
    def add_delivery_result(self, result: AlertDeliveryResult):
        """Add delivery result to batch."""
        self.delivery_results.append(result)


class AlertMetrics(BaseModel):
    """Alert system metrics."""
    
    # Time range
    period_start: datetime
    period_end: datetime
    
    # Alert counts
    total_alerts: int = Field(default=0)
    alerts_by_severity: Dict[str, int] = Field(default_factory=dict)
    alerts_by_channel: Dict[str, int] = Field(default_factory=dict)
    alerts_by_category: Dict[str, int] = Field(default_factory=dict)
    
    # Delivery metrics
    successful_deliveries: int = Field(default=0)
    failed_deliveries: int = Field(default=0)
    average_delivery_time_ms: float = Field(default=0.0)
    
    # Rule metrics
    active_rules: int = Field(default=0)
    triggered_rules: int = Field(default=0)
    
    # Response metrics
    acknowledged_alerts: int = Field(default=0)
    resolved_alerts: int = Field(default=0)
    expired_alerts: int = Field(default=0)
    
    def calculate_success_rate(self) -> float:
        """Calculate delivery success rate."""
        total = self.successful_deliveries + self.failed_deliveries
        if total == 0:
            return 0.0
        return (self.successful_deliveries / total) * 100
    
    def calculate_acknowledgment_rate(self) -> float:
        """Calculate alert acknowledgment rate."""
        if self.total_alerts == 0:
            return 0.0
        return (self.acknowledged_alerts / self.total_alerts) * 100