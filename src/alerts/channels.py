"""Alert delivery channels for various notification systems."""

import json
import smtplib
from abc import ABC, abstractmethod
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional, List

import httpx

from src.core.config import settings
from src.core.logging import get_logger
from .models import Alert, AlertDeliveryResult, AlertChannel


logger = get_logger(__name__)


class BaseAlertChannel(ABC):
    """Base class for alert delivery channels."""
    
    def __init__(self, channel_config: Dict[str, Any] = None):
        self.config = channel_config or {}
        self.channel_type = AlertChannel.EMAIL  # Override in subclasses
    
    @abstractmethod
    async def send_alert(self, alert: Alert, recipient: str) -> AlertDeliveryResult:
        """Send alert to recipient."""
        pass
    
    def format_message(self, alert: Alert) -> Dict[str, str]:
        """Format alert message for this channel."""
        return {
            "title": alert.title,
            "message": alert.message
        }


class EmailChannel(BaseAlertChannel):
    """Email alert delivery channel."""
    
    def __init__(self, channel_config: Dict[str, Any] = None):
        super().__init__(channel_config)
        self.channel_type = AlertChannel.EMAIL
        
        # Email configuration
        self.smtp_host = self.config.get("smtp_host", "smtp.gmail.com")
        self.smtp_port = self.config.get("smtp_port", 587)
        self.username = self.config.get("username", "")
        self.password = self.config.get("password", "")
        self.from_email = self.config.get("from_email", self.username)
        self.use_tls = self.config.get("use_tls", True)
    
    async def send_alert(self, alert: Alert, recipient: str) -> AlertDeliveryResult:
        """Send alert via email."""
        start_time = datetime.now()
        
        try:
            # Format message
            formatted = self.format_message(alert)
            
            # Create email
            msg = MIMEMultipart('alternative')
            msg['Subject'] = formatted["title"]
            msg['From'] = self.from_email
            msg['To'] = recipient
            
            # Add severity indicator to subject
            severity_indicator = {
                "critical": "🚨 CRITICAL",
                "high": "⚠️ HIGH",
                "medium": "📢 MEDIUM",
                "low": "ℹ️ LOW",
                "info": "📋 INFO"
            }.get(alert.severity.value, "")
            
            if severity_indicator:
                msg['Subject'] = f"{severity_indicator}: {formatted['title']}"
            
            # Create HTML and text versions
            html_body = self._create_html_email(alert, formatted)
            text_body = self._create_text_email(alert, formatted)
            
            msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                
                if self.username and self.password:
                    server.login(self.username, self.password)
                
                server.send_message(msg)
            
            # Calculate delivery time
            delivery_time = (datetime.now() - start_time).total_seconds() * 1000
            
            logger.info(
                "Email alert sent successfully",
                alert_id=alert.alert_id,
                recipient=recipient,
                delivery_time_ms=delivery_time
            )
            
            return AlertDeliveryResult(
                alert_id=alert.alert_id,
                channel=self.channel_type,
                recipient=recipient,
                success=True,
                delivered_at=datetime.now(),
                response_code=250,
                response_message="Email sent successfully",
                delivery_duration_ms=delivery_time
            )
        
        except Exception as e:
            delivery_time = (datetime.now() - start_time).total_seconds() * 1000
            
            logger.error(
                "Failed to send email alert",
                alert_id=alert.alert_id,
                recipient=recipient,
                error=str(e),
                delivery_time_ms=delivery_time
            )
            
            return AlertDeliveryResult(
                alert_id=alert.alert_id,
                channel=self.channel_type,
                recipient=recipient,
                success=False,
                delivered_at=datetime.now(),
                error_type=type(e).__name__,
                error_message=str(e),
                delivery_duration_ms=delivery_time
            )
    
    def _create_html_email(self, alert: Alert, formatted: Dict[str, str]) -> str:
        """Create HTML email body."""
        
        severity_colors = {
            "critical": "#dc3545",
            "high": "#fd7e14", 
            "medium": "#ffc107",
            "low": "#17a2b8",
            "info": "#6c757d"
        }
        
        color = severity_colors.get(alert.severity.value, "#6c757d")
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{formatted['title']}</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="border-left: 4px solid {color}; padding-left: 20px; margin-bottom: 20px;">
                <h1 style="color: {color}; margin-top: 0;">{formatted['title']}</h1>
                <p style="color: #666; margin: 5px 0;">
                    <strong>Severity:</strong> {alert.severity.value.title()} | 
                    <strong>Source:</strong> {alert.source} |
                    <strong>Time:</strong> {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}
                </p>
            </div>
            
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin-bottom: 20px;">
                <pre style="white-space: pre-wrap; margin: 0; font-family: inherit;">{formatted['message']}</pre>
            </div>
        """
        
        # Add context information
        if alert.symbol:
            html += f'<p><strong>Symbol:</strong> {alert.symbol}</p>'
        
        if alert.category:
            html += f'<p><strong>Category:</strong> {alert.category.title()}</p>'
        
        if alert.tags:
            html += f'<p><strong>Tags:</strong> {", ".join(alert.tags)}</p>'
        
        # Add data table if present
        if alert.data:
            html += """
            <div style="margin-top: 20px;">
                <h3>Additional Details:</h3>
                <table style="border-collapse: collapse; width: 100%; font-size: 14px;">
            """
            
            for key, value in alert.data.items():
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, indent=2)
                
                html += f"""
                <tr>
                    <td style="border: 1px solid #ddd; padding: 8px; background-color: #f9f9f9; font-weight: bold; width: 30%;">{key.replace('_', ' ').title()}</td>
                    <td style="border: 1px solid #ddd; padding: 8px;">{value}</td>
                </tr>
                """
            
            html += "</table></div>"
        
        html += """
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; color: #666; font-size: 12px;">
                <p>This alert was generated by ResearchLab. Alert ID: {alert_id}</p>
            </div>
        </body>
        </html>
        """.format(alert_id=alert.alert_id)
        
        return html
    
    def _create_text_email(self, alert: Alert, formatted: Dict[str, str]) -> str:
        """Create plain text email body."""
        
        text = f"""
{formatted['title']}
{'=' * len(formatted['title'])}

Severity: {alert.severity.value.title()}
Source: {alert.source}
Time: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
        
        if alert.symbol:
            text += f"Symbol: {alert.symbol}\n"
        
        if alert.category:
            text += f"Category: {alert.category.title()}\n"
        
        text += f"\nMessage:\n{formatted['message']}\n"
        
        if alert.tags:
            text += f"\nTags: {', '.join(alert.tags)}\n"
        
        if alert.data:
            text += "\nAdditional Details:\n"
            for key, value in alert.data.items():
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, indent=2)
                text += f"  {key.replace('_', ' ').title()}: {value}\n"
        
        text += f"\n---\nAlert ID: {alert.alert_id}\nGenerated by ResearchLab\n"
        
        return text


class WebhookChannel(BaseAlertChannel):
    """Webhook alert delivery channel."""
    
    def __init__(self, channel_config: Dict[str, Any] = None):
        super().__init__(channel_config)
        self.channel_type = AlertChannel.WEBHOOK
        
        # Webhook configuration
        self.timeout = self.config.get("timeout", 10)
        self.headers = self.config.get("headers", {"Content-Type": "application/json"})
        self.retry_attempts = self.config.get("retry_attempts", 3)
        self.verify_ssl = self.config.get("verify_ssl", True)
    
    async def send_alert(self, alert: Alert, recipient: str) -> AlertDeliveryResult:
        """Send alert via webhook."""
        start_time = datetime.now()
        
        try:
            # Format payload
            payload = self._create_webhook_payload(alert)
            
            # Send webhook
            async with httpx.AsyncClient(timeout=self.timeout, verify=self.verify_ssl) as client:
                response = await client.post(
                    recipient,  # recipient is the webhook URL
                    json=payload,
                    headers=self.headers
                )
                response.raise_for_status()
            
            delivery_time = (datetime.now() - start_time).total_seconds() * 1000
            
            logger.info(
                "Webhook alert sent successfully",
                alert_id=alert.alert_id,
                webhook_url=recipient,
                status_code=response.status_code,
                delivery_time_ms=delivery_time
            )
            
            return AlertDeliveryResult(
                alert_id=alert.alert_id,
                channel=self.channel_type,
                recipient=recipient,
                success=True,
                delivered_at=datetime.now(),
                response_code=response.status_code,
                response_message=response.text[:200] if response.text else "Success",
                delivery_duration_ms=delivery_time,
                response_data={"headers": dict(response.headers)}
            )
        
        except Exception as e:
            delivery_time = (datetime.now() - start_time).total_seconds() * 1000
            
            logger.error(
                "Failed to send webhook alert",
                alert_id=alert.alert_id,
                webhook_url=recipient,
                error=str(e),
                delivery_time_ms=delivery_time
            )
            
            return AlertDeliveryResult(
                alert_id=alert.alert_id,
                channel=self.channel_type,
                recipient=recipient,
                success=False,
                delivered_at=datetime.now(),
                error_type=type(e).__name__,
                error_message=str(e),
                delivery_duration_ms=delivery_time
            )
    
    def _create_webhook_payload(self, alert: Alert) -> Dict[str, Any]:
        """Create webhook payload."""
        return {
            "alert_id": alert.alert_id,
            "title": alert.title,
            "message": alert.message,
            "severity": alert.severity.value,
            "source": alert.source,
            "category": alert.category,
            "symbol": alert.symbol,
            "project_id": alert.project_id,
            "workflow_id": alert.workflow_id,
            "tags": alert.tags,
            "data": alert.data,
            "created_at": alert.created_at.isoformat(),
            "status": alert.status.value
        }


class SlackChannel(BaseAlertChannel):
    """Slack alert delivery channel."""
    
    def __init__(self, channel_config: Dict[str, Any] = None):
        super().__init__(channel_config)
        self.channel_type = AlertChannel.SLACK
        
        # Slack configuration
        self.webhook_url = self.config.get("webhook_url", "")
        self.username = self.config.get("username", "ResearchLab")
        self.icon_emoji = self.config.get("icon_emoji", ":chart_with_upwards_trend:")
    
    async def send_alert(self, alert: Alert, recipient: str) -> AlertDeliveryResult:
        """Send alert to Slack channel."""
        start_time = datetime.now()
        
        try:
            # Create Slack message
            slack_payload = self._create_slack_payload(alert, recipient)
            
            # Send to Slack
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    self.webhook_url,
                    json=slack_payload,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
            
            delivery_time = (datetime.now() - start_time).total_seconds() * 1000
            
            logger.info(
                "Slack alert sent successfully",
                alert_id=alert.alert_id,
                channel=recipient,
                delivery_time_ms=delivery_time
            )
            
            return AlertDeliveryResult(
                alert_id=alert.alert_id,
                channel=self.channel_type,
                recipient=recipient,
                success=True,
                delivered_at=datetime.now(),
                response_code=response.status_code,
                response_message="Message sent to Slack",
                delivery_duration_ms=delivery_time
            )
        
        except Exception as e:
            delivery_time = (datetime.now() - start_time).total_seconds() * 1000
            
            logger.error(
                "Failed to send Slack alert",
                alert_id=alert.alert_id,
                channel=recipient,
                error=str(e),
                delivery_time_ms=delivery_time
            )
            
            return AlertDeliveryResult(
                alert_id=alert.alert_id,
                channel=self.channel_type,
                recipient=recipient,
                success=False,
                delivered_at=datetime.now(),
                error_type=type(e).__name__,
                error_message=str(e),
                delivery_duration_ms=delivery_time
            )
    
    def _create_slack_payload(self, alert: Alert, channel: str) -> Dict[str, Any]:
        """Create Slack message payload."""
        
        # Color based on severity
        severity_colors = {
            "critical": "#dc3545",
            "high": "#fd7e14",
            "medium": "#ffc107", 
            "low": "#17a2b8",
            "info": "#6c757d"
        }
        
        color = severity_colors.get(alert.severity.value, "#6c757d")
        
        # Create attachment
        attachment = {
            "color": color,
            "title": alert.title,
            "text": alert.message,
            "fields": [
                {
                    "title": "Severity",
                    "value": alert.severity.value.title(),
                    "short": True
                },
                {
                    "title": "Source",
                    "value": alert.source,
                    "short": True
                },
                {
                    "title": "Category",
                    "value": alert.category.title(),
                    "short": True
                },
                {
                    "title": "Time",
                    "value": alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
                    "short": True
                }
            ],
            "footer": f"ResearchLab | Alert ID: {alert.alert_id}",
            "ts": int(alert.created_at.timestamp())
        }
        
        # Add symbol if present
        if alert.symbol:
            attachment["fields"].append({
                "title": "Symbol",
                "value": alert.symbol,
                "short": True
            })
        
        # Add tags if present
        if alert.tags:
            attachment["fields"].append({
                "title": "Tags",
                "value": ", ".join(alert.tags),
                "short": True
            })
        
        payload = {
            "channel": channel,
            "username": self.username,
            "icon_emoji": self.icon_emoji,
            "attachments": [attachment]
        }
        
        return payload


class DiscordChannel(BaseAlertChannel):
    """Discord alert delivery channel."""
    
    def __init__(self, channel_config: Dict[str, Any] = None):
        super().__init__(channel_config)
        self.channel_type = AlertChannel.DISCORD
        
        # Discord configuration
        self.webhook_url = self.config.get("webhook_url", "")
        self.username = self.config.get("username", "ResearchLab")
        self.avatar_url = self.config.get("avatar_url", "")
    
    async def send_alert(self, alert: Alert, recipient: str) -> AlertDeliveryResult:
        """Send alert to Discord channel."""
        start_time = datetime.now()
        
        try:
            # Create Discord embed
            discord_payload = self._create_discord_payload(alert)
            
            # Send to Discord
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    self.webhook_url,
                    json=discord_payload,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
            
            delivery_time = (datetime.now() - start_time).total_seconds() * 1000
            
            logger.info(
                "Discord alert sent successfully",
                alert_id=alert.alert_id,
                delivery_time_ms=delivery_time
            )
            
            return AlertDeliveryResult(
                alert_id=alert.alert_id,
                channel=self.channel_type,
                recipient=recipient,
                success=True,
                delivered_at=datetime.now(),
                response_code=response.status_code,
                response_message="Message sent to Discord",
                delivery_duration_ms=delivery_time
            )
        
        except Exception as e:
            delivery_time = (datetime.now() - start_time).total_seconds() * 1000
            
            logger.error(
                "Failed to send Discord alert",
                alert_id=alert.alert_id,
                error=str(e),
                delivery_time_ms=delivery_time
            )
            
            return AlertDeliveryResult(
                alert_id=alert.alert_id,
                channel=self.channel_type,
                recipient=recipient,
                success=False,
                delivered_at=datetime.now(),
                error_type=type(e).__name__,
                error_message=str(e),
                delivery_duration_ms=delivery_time
            )
    
    def _create_discord_payload(self, alert: Alert) -> Dict[str, Any]:
        """Create Discord embed payload."""
        
        # Color based on severity
        severity_colors = {
            "critical": 0xdc3545,  # Red
            "high": 0xfd7e14,      # Orange
            "medium": 0xffc107,    # Yellow
            "low": 0x17a2b8,       # Blue
            "info": 0x6c757d       # Gray
        }
        
        color = severity_colors.get(alert.severity.value, 0x6c757d)
        
        # Create embed
        embed = {
            "title": alert.title,
            "description": alert.message,
            "color": color,
            "timestamp": alert.created_at.isoformat(),
            "fields": [
                {
                    "name": "Severity",
                    "value": alert.severity.value.title(),
                    "inline": True
                },
                {
                    "name": "Source", 
                    "value": alert.source,
                    "inline": True
                },
                {
                    "name": "Category",
                    "value": alert.category.title(),
                    "inline": True
                }
            ],
            "footer": {
                "text": f"ResearchLab | {alert.alert_id}"
            }
        }
        
        # Add symbol field
        if alert.symbol:
            embed["fields"].append({
                "name": "Symbol",
                "value": alert.symbol,
                "inline": True
            })
        
        # Add tags field
        if alert.tags:
            embed["fields"].append({
                "name": "Tags",
                "value": ", ".join(alert.tags),
                "inline": True
            })
        
        payload = {
            "username": self.username,
            "embeds": [embed]
        }
        
        if self.avatar_url:
            payload["avatar_url"] = self.avatar_url
        
        return payload


class SMSChannel(BaseAlertChannel):
    """SMS alert delivery channel (using Twilio or similar service)."""
    
    def __init__(self, channel_config: Dict[str, Any] = None):
        super().__init__(channel_config)
        self.channel_type = AlertChannel.SMS
        
        # SMS configuration (would need Twilio credentials)
        self.account_sid = self.config.get("account_sid", "")
        self.auth_token = self.config.get("auth_token", "")
        self.from_number = self.config.get("from_number", "")
        self.max_length = self.config.get("max_length", 160)
    
    async def send_alert(self, alert: Alert, recipient: str) -> AlertDeliveryResult:
        """Send alert via SMS."""
        start_time = datetime.now()
        
        try:
            # Format SMS message
            sms_message = self._format_sms_message(alert)
            
            # Note: This is a placeholder implementation
            # In production, you would integrate with Twilio or another SMS service
            
            logger.info(
                "SMS alert would be sent",
                alert_id=alert.alert_id,
                recipient=recipient,
                message=sms_message
            )
            
            # Simulate success for now
            delivery_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return AlertDeliveryResult(
                alert_id=alert.alert_id,
                channel=self.channel_type,
                recipient=recipient,
                success=True,
                delivered_at=datetime.now(),
                response_message="SMS delivery simulated",
                delivery_duration_ms=delivery_time
            )
        
        except Exception as e:
            delivery_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return AlertDeliveryResult(
                alert_id=alert.alert_id,
                channel=self.channel_type,
                recipient=recipient,
                success=False,
                delivered_at=datetime.now(),
                error_type=type(e).__name__,
                error_message=str(e),
                delivery_duration_ms=delivery_time
            )
    
    def _format_sms_message(self, alert: Alert) -> str:
        """Format alert message for SMS."""
        # Create concise SMS message
        severity_emoji = {
            "critical": "🚨",
            "high": "⚠️",
            "medium": "📢",
            "low": "ℹ️",
            "info": "📋"
        }.get(alert.severity.value, "")
        
        message = f"{severity_emoji} {alert.title}"
        
        if alert.symbol:
            message += f" ({alert.symbol})"
        
        # Add truncated alert message
        remaining_length = self.max_length - len(message) - 20  # Leave room for footer
        if remaining_length > 0:
            truncated_msg = alert.message[:remaining_length]
            if len(alert.message) > remaining_length:
                truncated_msg += "..."
            message += f": {truncated_msg}"
        
        return message