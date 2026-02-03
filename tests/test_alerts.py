"""Tests for alert system."""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from src.alerts import (
    AlertManager, Alert, AlertRule, AlertChannel, AlertSeverity, 
    AlertStatus, AlertTemplate, EmailChannel, WebhookChannel
)
from src.alerts.rules import PriceAlertRule, NewsAlertRule, ResearchCompletionRule
from src.alerts.models import AlertDeliveryResult


class TestAlertModels:
    """Test alert data models."""
    
    def test_alert_creation(self):
        """Test alert creation."""
        alert = Alert(
            title="Test Alert",
            message="This is a test alert",
            severity=AlertSeverity.MEDIUM,
            source="test",
            category="test",
            channels=[AlertChannel.EMAIL],
            recipients=["test@example.com"]
        )
        
        assert alert.title == "Test Alert"
        assert alert.severity == AlertSeverity.MEDIUM
        assert alert.status == AlertStatus.PENDING
        assert len(alert.channels) == 1
        assert alert.channels[0] == AlertChannel.EMAIL
    
    def test_alert_expiration(self):
        """Test alert expiration logic."""
        # Create alert that expires in 1 hour
        expires_at = datetime.now() + timedelta(hours=1)
        alert = Alert(
            title="Test",
            message="Test",
            severity=AlertSeverity.LOW,
            source="test",
            category="test",
            channels=[AlertChannel.EMAIL],
            recipients=["test@example.com"],
            expires_at=expires_at
        )
        
        assert not alert.is_expired()
        
        # Create already expired alert
        expired_alert = Alert(
            title="Test",
            message="Test", 
            severity=AlertSeverity.LOW,
            source="test",
            category="test",
            channels=[AlertChannel.EMAIL],
            recipients=["test@example.com"],
            expires_at=datetime.now() - timedelta(hours=1)
        )
        
        assert expired_alert.is_expired()
    
    def test_alert_delivery_attempt(self):
        """Test alert delivery attempt tracking."""
        alert = Alert(
            title="Test",
            message="Test",
            severity=AlertSeverity.LOW,
            source="test",
            category="test",
            channels=[AlertChannel.EMAIL],
            recipients=["test@example.com"]
        )
        
        # Successful delivery
        alert.add_delivery_attempt(True)
        assert alert.status == AlertStatus.SENT
        assert alert.delivered_at is not None
        assert alert.delivery_attempts == 1
        
        # Failed delivery
        failed_alert = Alert(
            title="Test",
            message="Test",
            severity=AlertSeverity.LOW,
            source="test",
            category="test",
            channels=[AlertChannel.EMAIL],
            recipients=["test@example.com"]
        )
        
        failed_alert.add_delivery_attempt(False, "SMTP error")
        assert failed_alert.status == AlertStatus.FAILED
        assert failed_alert.error_message == "SMTP error"
        assert failed_alert.retry_count == 1
    
    def test_alert_acknowledge_resolve(self):
        """Test alert acknowledgment and resolution."""
        alert = Alert(
            title="Test",
            message="Test",
            severity=AlertSeverity.HIGH,
            source="test",
            category="test",
            channels=[AlertChannel.EMAIL],
            recipients=["test@example.com"]
        )
        
        # Acknowledge
        alert.acknowledge("user123")
        assert alert.status == AlertStatus.ACKNOWLEDGED
        assert alert.acknowledged_at is not None
        assert alert.data["acknowledged_by"] == "user123"
        
        # Resolve
        alert.resolve("user123", "Issue fixed")
        assert alert.status == AlertStatus.RESOLVED
        assert alert.resolved_at is not None
        assert alert.data["resolved_by"] == "user123"
        assert alert.data["resolution"] == "Issue fixed"
    
    def test_alert_rule_creation(self):
        """Test alert rule creation."""
        rule = AlertRule(
            name="Test Rule",
            description="Test alert rule",
            severity=AlertSeverity.HIGH,
            channels=[AlertChannel.EMAIL, AlertChannel.SLACK],
            recipients=["admin@example.com", "#alerts"],
            conditions={"min_change_percent": 5.0},
            cooldown_minutes=30
        )
        
        assert rule.name == "Test Rule"
        assert rule.severity == AlertSeverity.HIGH
        assert len(rule.channels) == 2
        assert rule.conditions["min_change_percent"] == 5.0
        assert rule.cooldown_minutes == 30
        assert rule.enabled is True
    
    def test_alert_rule_timing(self):
        """Test alert rule timing constraints."""
        # Rule active only during business hours (9-17)
        rule = AlertRule(
            name="Business Hours Rule",
            severity=AlertSeverity.MEDIUM,
            channels=[AlertChannel.EMAIL],
            recipients=["test@example.com"],
            active_hours=list(range(9, 18)),  # 9 AM to 5 PM
            active_days=[0, 1, 2, 3, 4]  # Monday to Friday
        )
        
        # Mock current time to business hours
        with patch('src.alerts.models.datetime') as mock_dt:
            # Tuesday 2 PM
            mock_dt.now.return_value = datetime(2024, 2, 6, 14, 0, 0)  # Tuesday
            assert rule.is_active()
        
        # Mock to weekend
        with patch('src.alerts.models.datetime') as mock_dt:
            # Saturday 2 PM
            mock_dt.now.return_value = datetime(2024, 2, 10, 14, 0, 0)  # Saturday
            assert not rule.is_active()


class TestAlertTemplate:
    """Test alert templates."""
    
    def test_template_creation(self):
        """Test template creation."""
        template = AlertTemplate(
            name="Price Alert Template",
            title_template="{symbol} price {direction}",
            message_template="{symbol} price {direction} by {change_percent:.1f}%",
            required_variables=["symbol", "direction", "change_percent"]
        )
        
        assert template.name == "Price Alert Template"
        assert len(template.required_variables) == 3
    
    def test_template_rendering(self):
        """Test template rendering."""
        template = AlertTemplate(
            name="Test Template",
            title_template="Alert for {symbol}",
            message_template="{symbol} changed by {change:.2f}%",
            required_variables=["symbol", "change"]
        )
        
        variables = {
            "symbol": "AAPL",
            "change": 5.67
        }
        
        rendered = template.render(variables)
        assert rendered["title"] == "Alert for AAPL"
        assert rendered["message"] == "AAPL changed by 5.67%"
    
    def test_template_missing_variables(self):
        """Test template with missing required variables."""
        template = AlertTemplate(
            name="Test Template", 
            title_template="Alert for {symbol}",
            message_template="{symbol} changed by {change:.2f}%",
            required_variables=["symbol", "change"]
        )
        
        # Missing required variable
        with pytest.raises(ValueError):
            template.render({"symbol": "AAPL"})  # Missing 'change'


class TestAlertRules:
    """Test alert rule implementations."""
    
    def test_price_alert_rule(self):
        """Test price alert rule."""
        rule_config = AlertRule(
            name="Price Alert",
            severity=AlertSeverity.MEDIUM,
            channels=[AlertChannel.EMAIL],
            recipients=["test@example.com"],
            conditions={
                "min_change_percent": 2.0,
                "direction": "up"
            }
        )
        
        price_rule = PriceAlertRule(rule_config)
        
        # Test triggering condition (5% increase)
        data = {
            "symbol": "AAPL",
            "current_price": 105.0,
            "previous_price": 100.0
        }
        
        alert = price_rule.evaluate(data)
        assert alert is not None
        assert alert.symbol == "AAPL"
        assert "increased" in alert.title
        assert alert.severity == AlertSeverity.MEDIUM
        
        # Test non-triggering condition (1% increase, below threshold)
        data_small = {
            "symbol": "AAPL", 
            "current_price": 101.0,
            "previous_price": 100.0
        }
        
        alert_small = price_rule.evaluate(data_small)
        assert alert_small is None
        
        # Test wrong direction (decrease when expecting increase)
        data_down = {
            "symbol": "AAPL",
            "current_price": 95.0, 
            "previous_price": 100.0
        }
        
        alert_down = price_rule.evaluate(data_down)
        assert alert_down is None
    
    def test_news_alert_rule(self):
        """Test news alert rule."""
        rule_config = AlertRule(
            name="News Alert",
            severity=AlertSeverity.HIGH,
            channels=[AlertChannel.SLACK],
            recipients=["#news-alerts"],
            conditions={
                "min_articles": 3,
                "sentiment_direction": "negative",
                "keywords": ["earnings", "lawsuit"]
            }
        )
        
        news_rule = NewsAlertRule(rule_config)
        
        # Test triggering condition
        news_items = [
            {"title": "Company faces lawsuit over earnings", "source": "Reuters"},
            {"title": "Earnings miss expectations", "source": "Bloomberg"}, 
            {"title": "Legal troubles continue", "source": "WSJ"},
            {"title": "Stock drops on lawsuit news", "source": "CNBC"}
        ]
        
        data = {
            "symbol": "XYZ",
            "news_items": news_items,
            "sentiment_score": -0.6
        }
        
        alert = news_rule.evaluate(data)
        assert alert is not None
        assert alert.symbol == "XYZ"
        assert "negative" in alert.title
        assert len(alert.data["articles"]) <= 5
    
    def test_research_completion_rule(self):
        """Test research completion rule."""
        rule_config = AlertRule(
            name="Research Complete",
            severity=AlertSeverity.MEDIUM,
            channels=[AlertChannel.EMAIL],
            recipients=["researcher@example.com"],
            conditions={
                "alert_on_status": ["completed", "failed"],
                "min_confidence": 0.7
            }
        )
        
        completion_rule = ResearchCompletionRule(rule_config)
        
        # Test successful completion with high confidence
        data = {
            "project_id": "proj_123",
            "workflow_id": "wf_456",
            "status": "completed",
            "confidence": 0.85,
            "companies": [{"symbol": "AAPL", "name": "Apple Inc."}]
        }
        
        alert = completion_rule.evaluate(data)
        assert alert is not None
        assert "completed" in alert.title
        assert alert.data["confidence"] == 0.85
        
        # Test low confidence completion (should not trigger)
        data_low_conf = {
            "project_id": "proj_123",
            "status": "completed", 
            "confidence": 0.5,
            "companies": [{"symbol": "AAPL"}]
        }
        
        alert_low = completion_rule.evaluate(data_low_conf)
        assert alert_low is None
        
        # Test failure (should trigger regardless of confidence)
        data_failed = {
            "project_id": "proj_123",
            "status": "failed",
            "confidence": 0.3,
            "companies": [{"symbol": "AAPL"}]
        }
        
        alert_failed = completion_rule.evaluate(data_failed)
        assert alert_failed is not None
        assert "failed" in alert_failed.title


class TestAlertChannels:
    """Test alert delivery channels."""
    
    @pytest.mark.asyncio
    async def test_email_channel_formatting(self):
        """Test email channel message formatting."""
        config = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "username": "test@example.com",
            "password": "password",
            "from_email": "alerts@example.com"
        }
        
        channel = EmailChannel(config)
        
        alert = Alert(
            title="Test Alert",
            message="This is a test alert message",
            severity=AlertSeverity.HIGH,
            source="test_system",
            category="test",
            symbol="AAPL",
            channels=[AlertChannel.EMAIL],
            recipients=["user@example.com"],
            tags=["urgent", "price"]
        )
        
        formatted = channel.format_message(alert)
        assert formatted["title"] == "Test Alert"
        assert formatted["message"] == "This is a test alert message"
        
        # Test HTML email creation
        html_body = channel._create_html_email(alert, formatted)
        assert "Test Alert" in html_body
        assert "HIGH" in html_body or "high" in html_body
        assert "AAPL" in html_body
        
        # Test text email creation
        text_body = channel._create_text_email(alert, formatted)
        assert "Test Alert" in text_body
        assert "High" in text_body or "HIGH" in text_body
        assert "AAPL" in text_body
    
    @pytest.mark.asyncio 
    async def test_webhook_channel(self):
        """Test webhook channel."""
        config = {
            "timeout": 5,
            "headers": {"Authorization": "Bearer token123"}
        }
        
        channel = WebhookChannel(config)
        
        alert = Alert(
            title="Webhook Test",
            message="Test webhook delivery",
            severity=AlertSeverity.CRITICAL,
            source="webhook_test",
            category="test",
            channels=[AlertChannel.WEBHOOK],
            recipients=["https://example.com/webhook"]
        )
        
        # Test payload creation
        payload = channel._create_webhook_payload(alert)
        assert payload["title"] == "Webhook Test"
        assert payload["severity"] == "critical"
        assert payload["source"] == "webhook_test"
        assert "created_at" in payload
    
    def test_slack_channel_formatting(self):
        """Test Slack channel message formatting."""
        config = {
            "webhook_url": "https://hooks.slack.com/test",
            "username": "AlertBot",
            "icon_emoji": ":warning:"
        }
        
        channel = SlackChannel(config)
        
        alert = Alert(
            title="Slack Alert Test",
            message="Testing Slack integration",
            severity=AlertSeverity.MEDIUM,
            source="slack_test",
            category="integration",
            symbol="GOOGL",
            channels=[AlertChannel.SLACK],
            recipients=["#alerts"],
            tags=["test", "integration"]
        )
        
        payload = channel._create_slack_payload(alert, "#alerts")
        
        assert payload["channel"] == "#alerts"
        assert payload["username"] == "AlertBot"
        assert len(payload["attachments"]) == 1
        
        attachment = payload["attachments"][0]
        assert attachment["title"] == "Slack Alert Test"
        assert attachment["text"] == "Testing Slack integration"
        assert len(attachment["fields"]) >= 4  # Severity, Source, Category, Time


class TestAlertManager:
    """Test alert manager."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = AlertManager()
    
    def test_manager_initialization(self):
        """Test manager initialization."""
        assert self.manager is not None
        assert len(self.manager.rules) == 0
        assert len(self.manager.alerts) == 0
        assert isinstance(self.manager.stats, dict)
    
    def test_add_remove_rule(self):
        """Test adding and removing rules."""
        rule = AlertRule(
            name="Test Rule",
            severity=AlertSeverity.MEDIUM,
            channels=[AlertChannel.EMAIL],
            recipients=["test@example.com"]
        )
        
        # Add rule
        rule_id = self.manager.add_rule(rule)
        assert rule_id == rule.rule_id
        assert len(self.manager.rules) == 1
        assert rule_id in self.manager.rule_instances
        
        # Get rule
        retrieved = self.manager.get_rule(rule_id)
        assert retrieved.name == "Test Rule"
        
        # List rules
        all_rules = self.manager.list_rules()
        assert len(all_rules) == 1
        
        # Remove rule
        removed = self.manager.remove_rule(rule_id)
        assert removed is True
        assert len(self.manager.rules) == 0
        assert rule_id not in self.manager.rule_instances
    
    @pytest.mark.asyncio
    async def test_create_alert(self):
        """Test alert creation."""
        alert = await self.manager.create_alert(
            title="Test Alert",
            message="This is a test",
            severity=AlertSeverity.HIGH,
            channels=[AlertChannel.EMAIL],
            recipients=["test@example.com"],
            symbol="AAPL",
            category="test"
        )
        
        assert alert.title == "Test Alert"
        assert alert.severity == AlertSeverity.HIGH
        assert alert.symbol == "AAPL"
        assert alert.alert_id in self.manager.alerts
        assert self.manager.stats["alerts_created"] == 1
    
    @pytest.mark.asyncio
    async def test_evaluate_rules(self):
        """Test rule evaluation."""
        # Add a price alert rule
        rule = AlertRule(
            name="Price Alert",
            severity=AlertSeverity.MEDIUM,
            channels=[AlertChannel.EMAIL],
            recipients=["test@example.com"],
            conditions={"min_change_percent": 5.0}
        )
        
        self.manager.add_rule(rule)
        
        # Evaluate with triggering data
        data = {
            "symbol": "AAPL",
            "current_price": 110.0,
            "previous_price": 100.0
        }
        
        triggered_alerts = await self.manager.evaluate_rules(data)
        
        # Should trigger one alert
        assert len(triggered_alerts) == 1
        assert triggered_alerts[0].symbol == "AAPL"
        assert self.manager.stats["rules_triggered"] == 1
    
    def test_channel_configuration(self):
        """Test channel configuration."""
        email_config = {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "username": "test@gmail.com",
            "password": "app_password"
        }
        
        self.manager.configure_channel(AlertChannel.EMAIL, email_config)
        
        assert AlertChannel.EMAIL in self.manager.channel_configs
        assert self.manager.channel_configs[AlertChannel.EMAIL]["smtp_host"] == "smtp.gmail.com"
    
    def test_template_management(self):
        """Test alert template management."""
        template = AlertTemplate(
            name="Price Change Template",
            title_template="{symbol} Price Alert",
            message_template="{symbol} changed by {change:.1f}%",
            required_variables=["symbol", "change"]
        )
        
        template_id = self.manager.add_template(template)
        assert template_id in self.manager.templates
        
        retrieved = self.manager.get_template(template_id)
        assert retrieved.name == "Price Change Template"
    
    @pytest.mark.asyncio
    async def test_create_alert_from_template(self):
        """Test creating alert from template."""
        template = AlertTemplate(
            name="Test Template",
            title_template="Alert for {symbol}",
            message_template="{symbol} alert: {message}",
            required_variables=["symbol", "message"],
            default_severity=AlertSeverity.LOW
        )
        
        template_id = self.manager.add_template(template)
        
        variables = {
            "symbol": "AAPL",
            "message": "Price increased"
        }
        
        alert = await self.manager.create_alert_from_template(
            template_id=template_id,
            variables=variables,
            channels=[AlertChannel.EMAIL],
            recipients=["test@example.com"]
        )
        
        assert alert is not None
        assert alert.title == "Alert for AAPL"
        assert alert.message == "AAPL alert: Price increased"
        assert alert.data["template_id"] == template_id
    
    def test_alert_management_operations(self):
        """Test alert management operations."""
        # Create some test alerts
        alert1 = Alert(
            title="Alert 1",
            message="Test",
            severity=AlertSeverity.HIGH,
            source="test",
            category="test",
            channels=[AlertChannel.EMAIL],
            recipients=["test@example.com"]
        )
        
        alert2 = Alert(
            title="Alert 2", 
            message="Test",
            severity=AlertSeverity.LOW,
            source="test",
            category="test",
            channels=[AlertChannel.EMAIL],
            recipients=["test@example.com"],
            status=AlertStatus.SENT
        )
        
        self.manager.alerts[alert1.alert_id] = alert1
        self.manager.alerts[alert2.alert_id] = alert2
        
        # Test get alert
        retrieved = self.manager.get_alert(alert1.alert_id)
        assert retrieved.title == "Alert 1"
        
        # Test list alerts
        all_alerts = self.manager.list_alerts()
        assert len(all_alerts) == 2
        
        # Test filter by status
        pending_alerts = self.manager.list_alerts(status=AlertStatus.PENDING)
        assert len(pending_alerts) == 1
        
        # Test filter by severity
        high_alerts = self.manager.list_alerts(severity=AlertSeverity.HIGH)
        assert len(high_alerts) == 1
        
        # Test acknowledge
        success = self.manager.acknowledge_alert(alert1.alert_id, "user123")
        assert success is True
        assert alert1.status == AlertStatus.ACKNOWLEDGED
        
        # Test resolve
        success = self.manager.resolve_alert(alert1.alert_id, "user123", "Fixed issue")
        assert success is True
        assert alert1.status == AlertStatus.RESOLVED
    
    def test_get_metrics(self):
        """Test metrics collection."""
        # Create test alerts
        now = datetime.now()
        
        alert1 = Alert(
            title="Alert 1",
            message="Test",
            severity=AlertSeverity.HIGH,
            source="test",
            category="price",
            channels=[AlertChannel.EMAIL],
            recipients=["test@example.com"],
            created_at=now,
            status=AlertStatus.SENT
        )
        alert1.acknowledged_at = now
        
        alert2 = Alert(
            title="Alert 2",
            message="Test", 
            severity=AlertSeverity.MEDIUM,
            source="test",
            category="news",
            channels=[AlertChannel.SLACK],
            recipients=["#alerts"],
            created_at=now - timedelta(minutes=30),
            status=AlertStatus.FAILED
        )
        
        self.manager.alerts[alert1.alert_id] = alert1
        self.manager.alerts[alert2.alert_id] = alert2
        
        # Get metrics
        metrics = self.manager.get_metrics(hours=1)
        
        assert metrics.total_alerts == 2
        assert metrics.alerts_by_severity["high"] == 1
        assert metrics.alerts_by_severity["medium"] == 1
        assert metrics.alerts_by_category["price"] == 1
        assert metrics.alerts_by_category["news"] == 1
        assert metrics.successful_deliveries == 1
        assert metrics.failed_deliveries == 1
        assert metrics.acknowledged_alerts == 1
    
    def test_get_stats(self):
        """Test statistics collection.""" 
        self.manager.stats["alerts_created"] = 10
        self.manager.stats["alerts_sent"] = 8
        self.manager.stats["alerts_failed"] = 2
        
        stats = self.manager.get_stats()
        
        assert stats["alerts_created"] == 10
        assert stats["alerts_sent"] == 8
        assert stats["alerts_failed"] == 2
        assert "total_rules" in stats
        assert "configured_channels" in stats


class TestAlertIntegration:
    """Integration tests for alert system."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = AlertManager()
    
    @pytest.mark.asyncio
    async def test_price_alert_integration(self):
        """Test price alert end-to-end."""
        # Configure email channel
        email_config = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "username": "test@example.com",
            "password": "password"
        }
        self.manager.configure_channel(AlertChannel.EMAIL, email_config)
        
        # Add price alert rule
        rule = AlertRule(
            name="AAPL Price Alert",
            severity=AlertSeverity.HIGH,
            channels=[AlertChannel.EMAIL],
            recipients=["trader@example.com"],
            conditions={
                "min_change_percent": 3.0,
                "direction": "up"
            }
        )
        self.manager.add_rule(rule)
        
        # Simulate price change notification
        await self.manager.notify_price_change("AAPL", 103.5, 100.0)
        
        # Check that alert was created
        assert len(self.manager.alerts) >= 1
        
        # Find the price alert
        price_alerts = [a for a in self.manager.alerts.values() if a.symbol == "AAPL"]
        assert len(price_alerts) >= 1
        
        price_alert = price_alerts[0]
        assert "increased" in price_alert.title.lower()
        assert price_alert.severity == AlertSeverity.HIGH
    
    @pytest.mark.asyncio
    async def test_research_completion_integration(self):
        """Test research completion alert end-to-end."""
        # Add research completion rule
        rule = AlertRule(
            name="Research Complete",
            severity=AlertSeverity.MEDIUM,
            channels=[AlertChannel.EMAIL],
            recipients=["analyst@example.com"],
            conditions={
                "alert_on_status": ["completed"],
                "min_confidence": 0.75
            }
        )
        self.manager.add_rule(rule)
        
        # Simulate research completion
        project_data = {
            "project_id": "proj_123",
            "workflow_id": "wf_456", 
            "status": "completed",
            "confidence": 0.85,
            "companies": [{"symbol": "AAPL", "name": "Apple Inc."}]
        }
        
        await self.manager.notify_research_completion(project_data)
        
        # Check alert was created
        completion_alerts = [a for a in self.manager.alerts.values() 
                           if "completed" in a.title.lower()]
        assert len(completion_alerts) >= 1
        
        alert = completion_alerts[0]
        assert alert.data["confidence"] == 0.85
        assert alert.data["project_id"] == "proj_123"
    
    @pytest.mark.asyncio
    async def test_multiple_channels_integration(self):
        """Test alert delivery to multiple channels."""
        # Configure multiple channels
        self.manager.configure_channel(AlertChannel.EMAIL, {
            "smtp_host": "smtp.example.com"
        })
        self.manager.configure_channel(AlertChannel.WEBHOOK, {
            "timeout": 10
        })
        
        # Create alert for multiple channels
        alert = await self.manager.create_alert(
            title="Multi-Channel Alert",
            message="This alert goes to multiple channels",
            severity=AlertSeverity.HIGH,
            channels=[AlertChannel.EMAIL, AlertChannel.WEBHOOK],
            recipients=["admin@example.com", "https://example.com/webhook"],
            category="system"
        )
        
        assert len(alert.channels) == 2
        assert AlertChannel.EMAIL in alert.channels
        assert AlertChannel.WEBHOOK in alert.channels
    
    def test_rule_rate_limiting(self):
        """Test rule rate limiting."""
        rule = AlertRule(
            name="Rate Limited Rule",
            severity=AlertSeverity.MEDIUM,
            channels=[AlertChannel.EMAIL],
            recipients=["test@example.com"],
            cooldown_minutes=60,
            max_alerts_per_hour=2
        )
        
        self.manager.add_rule(rule)
        
        # Simulate multiple triggers
        now = datetime.now()
        
        # First trigger should work
        assert self.manager._can_rule_trigger(rule) is True
        
        # Add trigger history
        self.manager.rule_trigger_history[rule.rule_id] = [now, now - timedelta(minutes=30)]
        
        # Should hit rate limit
        assert self.manager._can_rule_trigger(rule) is False
        
        # After cooldown, should work again
        rule.last_triggered = now - timedelta(minutes=61)
        self.manager.rule_trigger_history[rule.rule_id] = [now - timedelta(minutes=61)]
        
        assert self.manager._can_rule_trigger(rule) is True


class TestAlertDeliveryResult:
    """Test alert delivery result model."""
    
    def test_delivery_result_creation(self):
        """Test delivery result creation."""
        result = AlertDeliveryResult(
            alert_id="alert_123",
            channel=AlertChannel.EMAIL,
            recipient="test@example.com",
            success=True,
            delivered_at=datetime.now(),
            response_code=250,
            response_message="Message sent successfully",
            delivery_duration_ms=150.5
        )
        
        assert result.success is True
        assert result.channel == AlertChannel.EMAIL
        assert result.response_code == 250
        assert result.delivery_duration_ms == 150.5
    
    def test_delivery_result_string_representation(self):
        """Test delivery result string representation."""
        success_result = AlertDeliveryResult(
            alert_id="alert_123",
            channel=AlertChannel.SLACK,
            recipient="#alerts",
            success=True,
            delivered_at=datetime.now(),
            response_message="Posted to Slack"
        )
        
        result_str = str(success_result)
        assert "✅" in result_str
        assert "slack" in result_str
        assert "#alerts" in result_str
        assert "Posted to Slack" in result_str
        
        # Failed result
        failed_result = AlertDeliveryResult(
            alert_id="alert_456",
            channel=AlertChannel.EMAIL,
            recipient="invalid@email",
            success=False,
            delivered_at=datetime.now(),
            error_message="Invalid email address"
        )
        
        failed_str = str(failed_result)
        assert "❌" in failed_str
        assert "Invalid email address" in failed_str