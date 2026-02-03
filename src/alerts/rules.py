"""Alert rules for triggering notifications based on specific conditions."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union

from src.core.logging import get_logger
from .models import Alert, AlertRule, AlertSeverity, AlertChannel


logger = get_logger(__name__)


class BaseAlertRule(ABC):
    """Base class for alert rules."""
    
    def __init__(self, rule_config: AlertRule):
        self.config = rule_config
        self.logger = get_logger(f"{__name__}.{self.__class__.__name__}")
    
    @abstractmethod
    def evaluate(self, data: Dict[str, Any]) -> Optional[Alert]:
        """Evaluate rule against data and return alert if triggered."""
        pass
    
    def create_alert(
        self,
        title: str,
        message: str,
        data: Dict[str, Any],
        severity: Optional[AlertSeverity] = None,
        symbol: Optional[str] = None,
        category: str = "general"
    ) -> Alert:
        """Create alert with rule configuration."""
        
        return Alert(
            rule_id=self.config.rule_id,
            title=title,
            message=message,
            severity=severity or self.config.severity,
            source=f"rule:{self.config.name}",
            category=category,
            symbol=symbol,
            data=data,
            channels=self.config.channels,
            recipients=self.config.recipients
        )


class PriceAlertRule(BaseAlertRule):
    """Alert rule for stock price changes."""
    
    def evaluate(self, data: Dict[str, Any]) -> Optional[Alert]:
        """Evaluate price change conditions."""
        try:
            symbol = data.get("symbol")
            current_price = data.get("current_price")
            previous_price = data.get("previous_price")
            
            if not all([symbol, current_price, previous_price]):
                return None
            
            # Calculate price change
            price_change = current_price - previous_price
            price_change_pct = (price_change / previous_price) * 100 if previous_price != 0 else 0
            
            # Check conditions
            conditions = self.config.conditions
            
            # Check absolute price thresholds
            if "price_above" in conditions and current_price < conditions["price_above"]:
                return None
            
            if "price_below" in conditions and current_price > conditions["price_below"]:
                return None
            
            # Check percentage change thresholds
            min_change_pct = conditions.get("min_change_percent", 0)
            max_change_pct = conditions.get("max_change_percent", float('inf'))
            
            abs_change_pct = abs(price_change_pct)
            if not (min_change_pct <= abs_change_pct <= max_change_pct):
                return None
            
            # Check direction
            direction_filter = conditions.get("direction")  # "up", "down", or None
            if direction_filter:
                if direction_filter == "up" and price_change <= 0:
                    return None
                if direction_filter == "down" and price_change >= 0:
                    return None
            
            # Determine severity based on change magnitude
            severity = self._determine_price_severity(abs_change_pct)
            
            # Create alert
            direction = "increased" if price_change > 0 else "decreased"
            title = f"{symbol} price {direction} by {abs(price_change_pct):.2f}%"
            
            message = f"""
{symbol} price alert:
• Current Price: ${current_price:.2f}
• Previous Price: ${previous_price:.2f}
• Change: ${price_change:+.2f} ({price_change_pct:+.2f}%)
• Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
            """.strip()
            
            alert_data = {
                "symbol": symbol,
                "current_price": current_price,
                "previous_price": previous_price,
                "price_change": price_change,
                "price_change_percent": price_change_pct,
                "trigger_conditions": conditions
            }
            
            return self.create_alert(
                title=title,
                message=message,
                data=alert_data,
                severity=severity,
                symbol=symbol,
                category="price"
            )
        
        except Exception as e:
            self.logger.error(f"Error evaluating price alert rule: {e}")
            return None
    
    def _determine_price_severity(self, change_pct: float) -> AlertSeverity:
        """Determine alert severity based on price change magnitude."""
        if change_pct >= 10:
            return AlertSeverity.CRITICAL
        elif change_pct >= 5:
            return AlertSeverity.HIGH
        elif change_pct >= 2:
            return AlertSeverity.MEDIUM
        else:
            return AlertSeverity.LOW


class VolumeAlertRule(BaseAlertRule):
    """Alert rule for trading volume anomalies."""
    
    def evaluate(self, data: Dict[str, Any]) -> Optional[Alert]:
        """Evaluate volume anomaly conditions."""
        try:
            symbol = data.get("symbol")
            current_volume = data.get("current_volume")
            avg_volume = data.get("average_volume")
            
            if not all([symbol, current_volume, avg_volume]) or avg_volume == 0:
                return None
            
            # Calculate volume ratio
            volume_ratio = current_volume / avg_volume
            volume_change_pct = (volume_ratio - 1) * 100
            
            # Check conditions
            conditions = self.config.conditions
            min_ratio = conditions.get("min_volume_ratio", 2.0)
            
            if volume_ratio < min_ratio:
                return None
            
            # Determine severity
            severity = self._determine_volume_severity(volume_ratio)
            
            title = f"{symbol} unusual volume: {volume_ratio:.1f}x average"
            
            message = f"""
{symbol} volume alert:
• Current Volume: {current_volume:,}
• Average Volume: {avg_volume:,}
• Volume Ratio: {volume_ratio:.2f}x ({volume_change_pct:+.1f}%)
• Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
            """.strip()
            
            alert_data = {
                "symbol": symbol,
                "current_volume": current_volume,
                "average_volume": avg_volume,
                "volume_ratio": volume_ratio,
                "volume_change_percent": volume_change_pct
            }
            
            return self.create_alert(
                title=title,
                message=message,
                data=alert_data,
                severity=severity,
                symbol=symbol,
                category="volume"
            )
        
        except Exception as e:
            self.logger.error(f"Error evaluating volume alert rule: {e}")
            return None
    
    def _determine_volume_severity(self, volume_ratio: float) -> AlertSeverity:
        """Determine alert severity based on volume ratio."""
        if volume_ratio >= 10:
            return AlertSeverity.CRITICAL
        elif volume_ratio >= 5:
            return AlertSeverity.HIGH
        elif volume_ratio >= 3:
            return AlertSeverity.MEDIUM
        else:
            return AlertSeverity.LOW


class NewsAlertRule(BaseAlertRule):
    """Alert rule for news sentiment and events."""
    
    def evaluate(self, data: Dict[str, Any]) -> Optional[Alert]:
        """Evaluate news-based conditions."""
        try:
            symbol = data.get("symbol")
            news_items = data.get("news_items", [])
            sentiment_score = data.get("sentiment_score")
            
            if not symbol or not news_items:
                return None
            
            conditions = self.config.conditions
            
            # Check news count threshold
            min_articles = conditions.get("min_articles", 1)
            if len(news_items) < min_articles:
                return None
            
            # Check sentiment conditions
            if sentiment_score is not None:
                min_sentiment = conditions.get("min_sentiment_impact")
                if min_sentiment and abs(sentiment_score) < min_sentiment:
                    return None
                
                sentiment_direction = conditions.get("sentiment_direction")
                if sentiment_direction:
                    if sentiment_direction == "positive" and sentiment_score <= 0:
                        return None
                    if sentiment_direction == "negative" and sentiment_score >= 0:
                        return None
            
            # Check for specific keywords
            required_keywords = conditions.get("keywords", [])
            if required_keywords:
                article_text = " ".join([item.get("title", "") + " " + item.get("content", "") 
                                       for item in news_items])
                article_text = article_text.lower()
                
                if not any(keyword.lower() in article_text for keyword in required_keywords):
                    return None
            
            # Determine severity based on sentiment and article count
            severity = self._determine_news_severity(len(news_items), sentiment_score)
            
            sentiment_label = "positive" if sentiment_score > 0 else "negative" if sentiment_score < 0 else "neutral"
            title = f"{symbol} news alert: {len(news_items)} {sentiment_label} articles"
            
            # Create summary of top articles
            top_articles = news_items[:3]
            articles_summary = "\n".join([
                f"• {article.get('title', 'Untitled')} ({article.get('source', 'Unknown')})"
                for article in top_articles
            ])
            
            message = f"""
{symbol} news activity detected:
• Articles: {len(news_items)}
• Sentiment Score: {sentiment_score:.2f} ({sentiment_label})
• Time Range: Last 24 hours

Top Articles:
{articles_summary}
            """.strip()
            
            alert_data = {
                "symbol": symbol,
                "article_count": len(news_items),
                "sentiment_score": sentiment_score,
                "sentiment_label": sentiment_label,
                "articles": news_items[:5],  # Include top 5 articles
                "keywords_matched": required_keywords
            }
            
            return self.create_alert(
                title=title,
                message=message,
                data=alert_data,
                severity=severity,
                symbol=symbol,
                category="news"
            )
        
        except Exception as e:
            self.logger.error(f"Error evaluating news alert rule: {e}")
            return None
    
    def _determine_news_severity(self, article_count: int, sentiment_score: Optional[float]) -> AlertSeverity:
        """Determine alert severity based on news activity."""
        base_severity = AlertSeverity.LOW
        
        # Increase severity based on article count
        if article_count >= 10:
            base_severity = AlertSeverity.HIGH
        elif article_count >= 5:
            base_severity = AlertSeverity.MEDIUM
        
        # Adjust based on sentiment intensity
        if sentiment_score and abs(sentiment_score) >= 0.8:
            if base_severity == AlertSeverity.LOW:
                base_severity = AlertSeverity.MEDIUM
            elif base_severity == AlertSeverity.MEDIUM:
                base_severity = AlertSeverity.HIGH
            elif base_severity == AlertSeverity.HIGH:
                base_severity = AlertSeverity.CRITICAL
        
        return base_severity


class ResearchCompletionRule(BaseAlertRule):
    """Alert rule for research project completion."""
    
    def evaluate(self, data: Dict[str, Any]) -> Optional[Alert]:
        """Evaluate research completion conditions."""
        try:
            project_id = data.get("project_id")
            workflow_id = data.get("workflow_id")
            status = data.get("status")
            confidence = data.get("confidence")
            companies = data.get("companies", [])
            
            if not all([project_id, status]):
                return None
            
            conditions = self.config.conditions
            
            # Only alert on specific statuses
            alert_statuses = conditions.get("alert_on_status", ["completed", "failed"])
            if status not in alert_statuses:
                return None
            
            # Check confidence threshold for completed projects
            if status == "completed":
                min_confidence = conditions.get("min_confidence", 0.0)
                if confidence and confidence < min_confidence:
                    return None
            
            # Determine severity
            severity = self._determine_completion_severity(status, confidence)
            
            if status == "completed":
                title = f"Research completed: {project_id}"
                status_emoji = "✅"
            elif status == "failed":
                title = f"Research failed: {project_id}"
                status_emoji = "❌"
            else:
                title = f"Research {status}: {project_id}"
                status_emoji = "📊"
            
            company_list = ", ".join([c.get("symbol", c.get("name", "Unknown")) 
                                    for c in companies[:3]])
            if len(companies) > 3:
                company_list += f" and {len(companies) - 3} more"
            
            message = f"""
{status_emoji} Research project update:
• Project ID: {project_id}
• Status: {status.title()}
• Companies: {company_list}
"""
            
            if confidence is not None:
                message += f"• Confidence: {confidence:.2f}\n"
            
            if workflow_id:
                message += f"• Workflow ID: {workflow_id}\n"
            
            message += f"• Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            
            alert_data = {
                "project_id": project_id,
                "workflow_id": workflow_id,
                "status": status,
                "confidence": confidence,
                "companies": companies,
                "completion_time": datetime.now().isoformat()
            }
            
            return self.create_alert(
                title=title,
                message=message,
                data=alert_data,
                severity=severity,
                category="research"
            )
        
        except Exception as e:
            self.logger.error(f"Error evaluating research completion rule: {e}")
            return None
    
    def _determine_completion_severity(self, status: str, confidence: Optional[float]) -> AlertSeverity:
        """Determine severity based on completion status and confidence."""
        if status == "failed":
            return AlertSeverity.HIGH
        elif status == "completed":
            if confidence and confidence >= 0.8:
                return AlertSeverity.MEDIUM  # High confidence completion
            else:
                return AlertSeverity.LOW     # Regular completion
        else:
            return AlertSeverity.INFO


class WorkflowErrorRule(BaseAlertRule):
    """Alert rule for workflow errors and issues."""
    
    def evaluate(self, data: Dict[str, Any]) -> Optional[Alert]:
        """Evaluate workflow error conditions."""
        try:
            workflow_id = data.get("workflow_id")
            error_type = data.get("error_type")
            error_message = data.get("error_message")
            stage = data.get("stage")
            agent = data.get("agent")
            
            if not all([workflow_id, error_type]):
                return None
            
            conditions = self.config.conditions
            
            # Check if we should alert on this error type
            error_types = conditions.get("error_types", [])
            if error_types and error_type not in error_types:
                return None
            
            # Check severity threshold
            error_severity = data.get("severity", "medium")
            min_severity_level = conditions.get("min_severity", "low")
            
            severity_levels = {"low": 1, "medium": 2, "high": 3, "critical": 4}
            if severity_levels.get(error_severity, 2) < severity_levels.get(min_severity_level, 1):
                return None
            
            # Determine alert severity
            severity = self._determine_error_severity(error_type, error_severity)
            
            title = f"Workflow error: {error_type} in {workflow_id}"
            
            message = f"""
🚨 Workflow Error Detected:
• Workflow ID: {workflow_id}
• Error Type: {error_type}
• Stage: {stage or 'Unknown'}
• Agent: {agent or 'System'}
• Message: {error_message or 'No details provided'}
• Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
            """.strip()
            
            alert_data = {
                "workflow_id": workflow_id,
                "error_type": error_type,
                "error_message": error_message,
                "stage": stage,
                "agent": agent,
                "error_severity": error_severity,
                "timestamp": datetime.now().isoformat()
            }
            
            return self.create_alert(
                title=title,
                message=message,
                data=alert_data,
                severity=severity,
                category="system"
            )
        
        except Exception as e:
            self.logger.error(f"Error evaluating workflow error rule: {e}")
            return None
    
    def _determine_error_severity(self, error_type: str, error_severity: str) -> AlertSeverity:
        """Determine alert severity based on error characteristics."""
        # Map error severity to alert severity
        severity_mapping = {
            "critical": AlertSeverity.CRITICAL,
            "high": AlertSeverity.HIGH,
            "medium": AlertSeverity.MEDIUM,
            "low": AlertSeverity.LOW
        }
        
        base_severity = severity_mapping.get(error_severity, AlertSeverity.MEDIUM)
        
        # Escalate for certain critical error types
        critical_errors = ["database_error", "api_failure", "authentication_error", "timeout"]
        if error_type in critical_errors:
            if base_severity in [AlertSeverity.LOW, AlertSeverity.MEDIUM]:
                base_severity = AlertSeverity.HIGH
        
        return base_severity


class SystemHealthRule(BaseAlertRule):
    """Alert rule for system health metrics."""
    
    def evaluate(self, data: Dict[str, Any]) -> Optional[Alert]:
        """Evaluate system health conditions."""
        try:
            metric_name = data.get("metric_name")
            metric_value = data.get("metric_value")
            threshold = data.get("threshold")
            
            if not all([metric_name, metric_value is not None, threshold is not None]):
                return None
            
            conditions = self.config.conditions
            comparison = conditions.get("comparison", "greater_than")  # greater_than, less_than, equals
            
            # Evaluate threshold condition
            triggered = False
            if comparison == "greater_than" and metric_value > threshold:
                triggered = True
            elif comparison == "less_than" and metric_value < threshold:
                triggered = True
            elif comparison == "equals" and metric_value == threshold:
                triggered = True
            
            if not triggered:
                return None
            
            # Determine severity based on how far the metric is from threshold
            severity = self._determine_health_severity(metric_name, metric_value, threshold, comparison)
            
            title = f"System health alert: {metric_name}"
            
            message = f"""
⚡ System Health Alert:
• Metric: {metric_name}
• Current Value: {metric_value}
• Threshold: {threshold}
• Condition: {comparison.replace('_', ' ')}
• Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
            """.strip()
            
            alert_data = {
                "metric_name": metric_name,
                "metric_value": metric_value,
                "threshold": threshold,
                "comparison": comparison,
                "timestamp": datetime.now().isoformat()
            }
            
            return self.create_alert(
                title=title,
                message=message,
                data=alert_data,
                severity=severity,
                category="system"
            )
        
        except Exception as e:
            self.logger.error(f"Error evaluating system health rule: {e}")
            return None
    
    def _determine_health_severity(
        self, 
        metric_name: str, 
        value: float, 
        threshold: float, 
        comparison: str
    ) -> AlertSeverity:
        """Determine severity based on metric deviation from threshold."""
        
        # Calculate deviation percentage
        if threshold != 0:
            deviation_pct = abs((value - threshold) / threshold) * 100
        else:
            deviation_pct = 100  # Assume high deviation if threshold is 0
        
        # Critical metrics that warrant higher severity
        critical_metrics = ["cpu_usage", "memory_usage", "disk_usage", "error_rate"]
        is_critical_metric = any(cm in metric_name.lower() for cm in critical_metrics)
        
        # Determine base severity
        if deviation_pct >= 50:
            base_severity = AlertSeverity.HIGH
        elif deviation_pct >= 25:
            base_severity = AlertSeverity.MEDIUM
        else:
            base_severity = AlertSeverity.LOW
        
        # Escalate for critical metrics
        if is_critical_metric and base_severity != AlertSeverity.LOW:
            if base_severity == AlertSeverity.MEDIUM:
                base_severity = AlertSeverity.HIGH
            elif base_severity == AlertSeverity.HIGH:
                base_severity = AlertSeverity.CRITICAL
        
        return base_severity


class CustomRule(BaseAlertRule):
    """Customizable rule with user-defined conditions."""
    
    def evaluate(self, data: Dict[str, Any]) -> Optional[Alert]:
        """Evaluate custom conditions."""
        try:
            conditions = self.config.conditions
            
            # Get custom evaluation function or expression
            evaluation_expr = conditions.get("expression")
            required_fields = conditions.get("required_fields", [])
            
            # Check required fields
            for field in required_fields:
                if field not in data:
                    return None
            
            # Simple expression evaluation (in production, use safer evaluation)
            if evaluation_expr:
                # This is a simplified example - in production you'd want
                # a safer expression evaluator
                try:
                    # Replace field references with actual values
                    expr = evaluation_expr
                    for key, value in data.items():
                        expr = expr.replace(f"{{{key}}}", str(value))
                    
                    # Evaluate expression (WARNING: eval is dangerous, use a safer alternative)
                    # result = eval(expr)  # Don't use eval in production!
                    # For now, just return None to be safe
                    return None
                    
                except Exception:
                    return None
            
            # If no expression, check simple conditions
            title = conditions.get("alert_title", "Custom Alert")
            message = conditions.get("alert_message", "Custom condition triggered")
            
            alert_data = data.copy()
            alert_data["custom_conditions"] = conditions
            
            return self.create_alert(
                title=title,
                message=message,
                data=alert_data,
                category="custom"
            )
        
        except Exception as e:
            self.logger.error(f"Error evaluating custom rule: {e}")
            return None