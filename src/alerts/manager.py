"""Alert manager for coordinating alert rules, channels, and delivery."""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Type
from collections import defaultdict

from src.core.config import settings
from src.core.logging import get_logger
# from src.data.models import ResearchProject  # Import when needed

from .models import (
    Alert, AlertRule, AlertChannel, AlertSeverity, AlertStatus,
    AlertDeliveryResult, AlertBatch, AlertMetrics, AlertTemplate
)
from .channels import (
    BaseAlertChannel, EmailChannel, WebhookChannel, SlackChannel,
    DiscordChannel, SMSChannel
)
from .rules import (
    BaseAlertRule, PriceAlertRule, VolumeAlertRule, NewsAlertRule,
    ResearchCompletionRule, WorkflowErrorRule, SystemHealthRule, CustomRule
)


logger = get_logger(__name__)


class AlertManager:
    """Central manager for the alert system."""
    
    def __init__(self):
        self.logger = get_logger(f"{__name__}.manager")
        
        # Storage (in production, use database)
        self.alerts: Dict[str, Alert] = {}
        self.rules: Dict[str, AlertRule] = {}
        self.templates: Dict[str, AlertTemplate] = {}
        
        # Channel configurations
        self.channel_configs: Dict[AlertChannel, Dict[str, Any]] = {}
        
        # Rule instances
        self.rule_instances: Dict[str, BaseAlertRule] = {}
        
        # Channel instances
        self.channel_instances: Dict[AlertChannel, BaseAlertChannel] = {}
        
        # Rate limiting tracking
        self.rule_trigger_history: Dict[str, List[datetime]] = defaultdict(list)
        
        # Processing queue
        self.alert_queue: asyncio.Queue = asyncio.Queue()
        self.batch_queue: asyncio.Queue = asyncio.Queue()
        
        # Background tasks
        self.processing_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.stats = {
            "alerts_created": 0,
            "alerts_sent": 0,
            "alerts_failed": 0,
            "rules_triggered": 0
        }
        
        # Initialize default configurations
        self._initialize_default_configs()
        
        self.logger.info("Alert manager initialized")
    
    def _initialize_default_configs(self):
        """Initialize default channel configurations."""
        
        # Email configuration from settings
        if hasattr(settings, 'email') and settings.email:
            self.channel_configs[AlertChannel.EMAIL] = {
                "smtp_host": getattr(settings.email, 'smtp_host', 'smtp.gmail.com'),
                "smtp_port": getattr(settings.email, 'smtp_port', 587),
                "username": getattr(settings.email, 'username', ''),
                "password": getattr(settings.email, 'password', ''),
                "from_email": getattr(settings.email, 'from_email', ''),
                "use_tls": getattr(settings.email, 'use_tls', True)
            }
        
        # Webhook configuration
        self.channel_configs[AlertChannel.WEBHOOK] = {
            "timeout": 10,
            "headers": {"Content-Type": "application/json"},
            "retry_attempts": 3,
            "verify_ssl": True
        }
        
        # Slack configuration
        if hasattr(settings, 'slack') and settings.slack:
            self.channel_configs[AlertChannel.SLACK] = {
                "webhook_url": getattr(settings.slack, 'webhook_url', ''),
                "username": getattr(settings.slack, 'username', 'ResearchLab'),
                "icon_emoji": getattr(settings.slack, 'icon_emoji', ':chart_with_upwards_trend:')
            }
    
    async def start(self):
        """Start the alert manager and background tasks."""
        if self.processing_task is None:
            self.processing_task = asyncio.create_task(self._process_alerts())
            self.cleanup_task = asyncio.create_task(self._cleanup_old_alerts())
            
            self.logger.info("Alert manager started")
    
    async def stop(self):
        """Stop the alert manager and background tasks."""
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
        
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Alert manager stopped")
    
    # Rule Management
    
    def add_rule(self, rule: AlertRule) -> str:
        """Add an alert rule."""
        self.rules[rule.rule_id] = rule
        
        # Create rule instance based on type
        rule_instance = self._create_rule_instance(rule)
        if rule_instance:
            self.rule_instances[rule.rule_id] = rule_instance
        
        self.logger.info(f"Added alert rule: {rule.name}", rule_id=rule.rule_id)
        return rule.rule_id
    
    def _create_rule_instance(self, rule: AlertRule) -> Optional[BaseAlertRule]:
        """Create rule instance based on rule configuration."""
        
        # Determine rule type from conditions or name
        rule_type = rule.conditions.get("rule_type", "custom")
        rule_name_lower = rule.name.lower()
        
        # Map rule types to classes
        rule_classes = {
            "price": PriceAlertRule,
            "volume": VolumeAlertRule,
            "news": NewsAlertRule,
            "research_completion": ResearchCompletionRule,
            "workflow_error": WorkflowErrorRule,
            "system_health": SystemHealthRule,
            "custom": CustomRule
        }
        
        # Infer type from rule name if not specified
        if rule_type == "custom":
            for keyword, rule_class in rule_classes.items():
                if keyword in rule_name_lower:
                    rule_type = keyword
                    break
        
        rule_class = rule_classes.get(rule_type, CustomRule)
        
        try:
            return rule_class(rule)
        except Exception as e:
            self.logger.error(f"Failed to create rule instance: {e}", rule_id=rule.rule_id)
            return None
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove an alert rule."""
        if rule_id in self.rules:
            del self.rules[rule_id]
            
            if rule_id in self.rule_instances:
                del self.rule_instances[rule_id]
            
            if rule_id in self.rule_trigger_history:
                del self.rule_trigger_history[rule_id]
            
            self.logger.info(f"Removed alert rule", rule_id=rule_id)
            return True
        
        return False
    
    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        """Get alert rule by ID."""
        return self.rules.get(rule_id)
    
    def list_rules(self, enabled_only: bool = False) -> List[AlertRule]:
        """List all alert rules."""
        rules = list(self.rules.values())
        
        if enabled_only:
            rules = [rule for rule in rules if rule.enabled]
        
        return rules
    
    # Channel Management
    
    def configure_channel(self, channel: AlertChannel, config: Dict[str, Any]):
        """Configure alert channel."""
        self.channel_configs[channel] = config
        
        # Remove existing instance to force recreation
        if channel in self.channel_instances:
            del self.channel_instances[channel]
        
        self.logger.info(f"Configured alert channel: {channel.value}")
    
    def _get_channel_instance(self, channel: AlertChannel) -> Optional[BaseAlertChannel]:
        """Get or create channel instance."""
        if channel not in self.channel_instances:
            config = self.channel_configs.get(channel, {})
            
            channel_classes = {
                AlertChannel.EMAIL: EmailChannel,
                AlertChannel.WEBHOOK: WebhookChannel,
                AlertChannel.SLACK: SlackChannel,
                AlertChannel.DISCORD: DiscordChannel,
                AlertChannel.SMS: SMSChannel
            }
            
            channel_class = channel_classes.get(channel)
            if not channel_class:
                self.logger.error(f"Unknown channel type: {channel}")
                return None
            
            try:
                self.channel_instances[channel] = channel_class(config)
            except Exception as e:
                self.logger.error(f"Failed to create channel instance: {e}", channel=channel.value)
                return None
        
        return self.channel_instances.get(channel)
    
    # Alert Creation and Processing
    
    async def evaluate_rules(self, data: Dict[str, Any]) -> List[Alert]:
        """Evaluate all active rules against data."""
        triggered_alerts = []
        
        for rule_id, rule_instance in self.rule_instances.items():
            try:
                rule_config = self.rules[rule_id]
                
                # Check if rule can trigger based on rate limits and time constraints
                if not self._can_rule_trigger(rule_config):
                    continue
                
                # Evaluate rule
                alert = rule_instance.evaluate(data)
                
                if alert:
                    # Update rule statistics
                    rule_config.update_trigger_stats()
                    self.stats["rules_triggered"] += 1
                    
                    # Track rule trigger for rate limiting
                    self.rule_trigger_history[rule_id].append(datetime.now())
                    
                    # Add to processing queue
                    triggered_alerts.append(alert)
                    await self.alert_queue.put(alert)
                    
                    self.logger.info(
                        f"Rule triggered alert",
                        rule_id=rule_id,
                        alert_id=alert.alert_id,
                        severity=alert.severity.value
                    )
            
            except Exception as e:
                self.logger.error(f"Error evaluating rule: {e}", rule_id=rule_id)
        
        return triggered_alerts
    
    def _can_rule_trigger(self, rule: AlertRule) -> bool:
        """Check if rule can trigger based on rate limits and constraints."""
        
        if not rule.can_trigger():
            return False
        
        # Check hourly rate limit
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        
        recent_triggers = [
            t for t in self.rule_trigger_history[rule.rule_id]
            if t > hour_ago
        ]
        
        if len(recent_triggers) >= rule.max_alerts_per_hour:
            return False
        
        # Check daily rate limit
        day_ago = now - timedelta(days=1)
        daily_triggers = [
            t for t in self.rule_trigger_history[rule.rule_id]
            if t > day_ago
        ]
        
        if len(daily_triggers) >= rule.max_alerts_per_day:
            return False
        
        return True
    
    async def create_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        channels: List[AlertChannel],
        recipients: List[str],
        **kwargs
    ) -> Alert:
        """Create and queue an alert for delivery."""
        
        alert = Alert(
            title=title,
            message=message,
            severity=severity,
            channels=channels,
            recipients=recipients,
            **kwargs
        )
        
        # Store alert
        self.alerts[alert.alert_id] = alert
        
        # Queue for processing
        await self.alert_queue.put(alert)
        
        self.stats["alerts_created"] += 1
        
        self.logger.info(
            f"Created alert",
            alert_id=alert.alert_id,
            title=title,
            severity=severity.value
        )
        
        return alert
    
    async def _process_alerts(self):
        """Background task to process alerts from queue."""
        while True:
            try:
                alert = await self.alert_queue.get()
                
                if alert.is_expired():
                    self.logger.warning(f"Alert expired before processing", alert_id=alert.alert_id)
                    continue
                
                await self._deliver_alert(alert)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error processing alert: {e}")
    
    async def _deliver_alert(self, alert: Alert):
        """Deliver alert through all configured channels."""
        
        delivery_results = []
        
        for channel in alert.channels:
            channel_instance = self._get_channel_instance(channel)
            
            if not channel_instance:
                self.logger.error(f"Channel not configured: {channel.value}", alert_id=alert.alert_id)
                continue
            
            # Send to all recipients for this channel
            for recipient in alert.recipients:
                try:
                    result = await channel_instance.send_alert(alert, recipient)
                    delivery_results.append(result)
                    
                    if result.success:
                        self.logger.info(
                            f"Alert delivered successfully",
                            alert_id=alert.alert_id,
                            channel=channel.value,
                            recipient=recipient
                        )
                    else:
                        self.logger.error(
                            f"Alert delivery failed",
                            alert_id=alert.alert_id,
                            channel=channel.value,
                            recipient=recipient,
                            error=result.error_message
                        )
                
                except Exception as e:
                    self.logger.error(
                        f"Exception during alert delivery: {e}",
                        alert_id=alert.alert_id,
                        channel=channel.value,
                        recipient=recipient
                    )
        
        # Update alert status based on delivery results
        successful_deliveries = [r for r in delivery_results if r.success]
        failed_deliveries = [r for r in delivery_results if not r.success]
        
        if successful_deliveries and not failed_deliveries:
            alert.status = AlertStatus.SENT
            alert.delivered_at = datetime.now()
            self.stats["alerts_sent"] += 1
        elif failed_deliveries and not successful_deliveries:
            alert.status = AlertStatus.FAILED
            self.stats["alerts_failed"] += 1
        else:
            # Partial success
            alert.status = AlertStatus.SENT  # Consider partial success as sent
            alert.delivered_at = datetime.now()
            self.stats["alerts_sent"] += 1
        
        # Store delivery results in alert data
        alert.data["delivery_results"] = [r.dict() for r in delivery_results]
    
    # Template Management
    
    def add_template(self, template: AlertTemplate) -> str:
        """Add alert template."""
        self.templates[template.template_id] = template
        
        self.logger.info(f"Added alert template: {template.name}", template_id=template.template_id)
        return template.template_id
    
    def get_template(self, template_id: str) -> Optional[AlertTemplate]:
        """Get alert template by ID."""
        return self.templates.get(template_id)
    
    async def create_alert_from_template(
        self,
        template_id: str,
        variables: Dict[str, Any],
        channels: List[AlertChannel],
        recipients: List[str],
        **kwargs
    ) -> Optional[Alert]:
        """Create alert from template."""
        
        template = self.get_template(template_id)
        if not template:
            self.logger.error(f"Template not found: {template_id}")
            return None
        
        try:
            rendered = template.render(variables)
            
            alert = await self.create_alert(
                title=rendered["title"],
                message=rendered["message"],
                severity=kwargs.get("severity", template.default_severity),
                channels=channels or template.default_channels,
                recipients=recipients,
                category=kwargs.get("category", template.default_category),
                **{k: v for k, v in kwargs.items() if k not in ["severity", "category"]}
            )
            
            alert.data["template_id"] = template_id
            alert.data["template_variables"] = variables
            
            return alert
        
        except Exception as e:
            self.logger.error(f"Failed to create alert from template: {e}", template_id=template_id)
            return None
    
    # Alert Management
    
    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get alert by ID."""
        return self.alerts.get(alert_id)
    
    def list_alerts(
        self,
        status: Optional[AlertStatus] = None,
        severity: Optional[AlertSeverity] = None,
        limit: int = 100
    ) -> List[Alert]:
        """List alerts with optional filtering."""
        
        alerts = list(self.alerts.values())
        
        # Apply filters
        if status:
            alerts = [a for a in alerts if a.status == status]
        
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        
        # Sort by creation time (newest first)
        alerts.sort(key=lambda x: x.created_at, reverse=True)
        
        return alerts[:limit]
    
    def acknowledge_alert(self, alert_id: str, user_id: Optional[str] = None) -> bool:
        """Acknowledge an alert."""
        alert = self.get_alert(alert_id)
        if alert:
            alert.acknowledge(user_id)
            self.logger.info(f"Alert acknowledged", alert_id=alert_id, user_id=user_id)
            return True
        return False
    
    def resolve_alert(
        self,
        alert_id: str,
        user_id: Optional[str] = None,
        resolution: Optional[str] = None
    ) -> bool:
        """Resolve an alert."""
        alert = self.get_alert(alert_id)
        if alert:
            alert.resolve(user_id, resolution)
            self.logger.info(f"Alert resolved", alert_id=alert_id, user_id=user_id)
            return True
        return False
    
    # Cleanup and Maintenance
    
    async def _cleanup_old_alerts(self):
        """Background task to cleanup old alerts."""
        while True:
            try:
                # Clean up every hour
                await asyncio.sleep(3600)
                
                now = datetime.now()
                cutoff = now - timedelta(days=7)  # Keep alerts for 7 days
                
                old_alerts = [
                    alert_id for alert_id, alert in self.alerts.items()
                    if alert.created_at < cutoff
                ]
                
                for alert_id in old_alerts:
                    del self.alerts[alert_id]
                
                if old_alerts:
                    self.logger.info(f"Cleaned up {len(old_alerts)} old alerts")
                
                # Clean up rule trigger history
                history_cutoff = now - timedelta(days=1)
                for rule_id in list(self.rule_trigger_history.keys()):
                    self.rule_trigger_history[rule_id] = [
                        t for t in self.rule_trigger_history[rule_id]
                        if t > history_cutoff
                    ]
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error during cleanup: {e}")
    
    # Metrics and Statistics
    
    def get_metrics(self, hours: int = 24) -> AlertMetrics:
        """Get alert system metrics for specified time period."""
        
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        # Filter alerts in time period
        period_alerts = [
            alert for alert in self.alerts.values()
            if start_time <= alert.created_at <= end_time
        ]
        
        metrics = AlertMetrics(
            period_start=start_time,
            period_end=end_time
        )
        
        metrics.total_alerts = len(period_alerts)
        
        # Count by severity
        for alert in period_alerts:
            severity = alert.severity.value
            metrics.alerts_by_severity[severity] = metrics.alerts_by_severity.get(severity, 0) + 1
        
        # Count by channel
        for alert in period_alerts:
            for channel in alert.channels:
                channel_name = channel.value
                metrics.alerts_by_channel[channel_name] = metrics.alerts_by_channel.get(channel_name, 0) + 1
        
        # Count by category
        for alert in period_alerts:
            category = alert.category
            metrics.alerts_by_category[category] = metrics.alerts_by_category.get(category, 0) + 1
        
        # Delivery metrics
        delivered_alerts = [a for a in period_alerts if a.status == AlertStatus.SENT]
        failed_alerts = [a for a in period_alerts if a.status == AlertStatus.FAILED]
        
        metrics.successful_deliveries = len(delivered_alerts)
        metrics.failed_deliveries = len(failed_alerts)
        
        # Response metrics
        metrics.acknowledged_alerts = len([a for a in period_alerts if a.acknowledged_at])
        metrics.resolved_alerts = len([a for a in period_alerts if a.resolved_at])
        metrics.expired_alerts = len([a for a in period_alerts if a.is_expired()])
        
        # Rule metrics
        metrics.active_rules = len([r for r in self.rules.values() if r.enabled])
        
        # Count rules that triggered in period
        triggered_rules = set()
        for alert in period_alerts:
            if alert.rule_id:
                triggered_rules.add(alert.rule_id)
        metrics.triggered_rules = len(triggered_rules)
        
        return metrics
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current alert system statistics."""
        return {
            **self.stats,
            "total_rules": len(self.rules),
            "active_rules": len([r for r in self.rules.values() if r.enabled]),
            "total_alerts": len(self.alerts),
            "pending_alerts": len([a for a in self.alerts.values() if a.status == AlertStatus.PENDING]),
            "configured_channels": list(self.channel_configs.keys())
        }
    
    # Integration Methods
    
    async def notify_research_completion(self, project_data: Dict[str, Any]):
        """Notify about research project completion."""
        data = {
            "project_id": project_data.get("project_id"),
            "workflow_id": project_data.get("workflow_id"),
            "status": project_data.get("status"),
            "confidence": project_data.get("confidence"),
            "companies": project_data.get("companies", [])
        }
        
        await self.evaluate_rules(data)
    
    async def notify_price_change(self, symbol: str, current_price: float, previous_price: float):
        """Notify about price changes."""
        data = {
            "symbol": symbol,
            "current_price": current_price,
            "previous_price": previous_price
        }
        
        await self.evaluate_rules(data)
    
    async def notify_news_event(self, symbol: str, news_items: List[Dict], sentiment_score: float):
        """Notify about news events."""
        data = {
            "symbol": symbol,
            "news_items": news_items,
            "sentiment_score": sentiment_score
        }
        
        await self.evaluate_rules(data)
    
    async def notify_workflow_error(
        self,
        workflow_id: str,
        error_type: str,
        error_message: str,
        stage: Optional[str] = None,
        agent: Optional[str] = None,
        severity: str = "medium"
    ):
        """Notify about workflow errors."""
        data = {
            "workflow_id": workflow_id,
            "error_type": error_type,
            "error_message": error_message,
            "stage": stage,
            "agent": agent,
            "severity": severity
        }
        
        await self.evaluate_rules(data)
    
    async def notify_system_health(self, metric_name: str, metric_value: float, threshold: float):
        """Notify about system health metrics."""
        data = {
            "metric_name": metric_name,
            "metric_value": metric_value,
            "threshold": threshold
        }
        
        await self.evaluate_rules(data)