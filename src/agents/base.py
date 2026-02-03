"""Base agent class for all specialist agents."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional
import structlog

logger = structlog.get_logger()


class AgentRole(Enum):
    """Specialist agent roles."""
    RESEARCH_DIRECTOR = "research_director"
    FUNDAMENTAL_ANALYST = "fundamental_analyst"
    SUPPLY_CHAIN_ANALYST = "supply_chain_analyst"
    SENTIMENT_ANALYST = "sentiment_analyst"
    QUANTITATIVE_ANALYST = "quantitative_analyst"
    RISK_ANALYST = "risk_analyst"


@dataclass
class AgentMessage:
    """Message passed between agents."""
    sender: AgentRole
    recipient: Optional[AgentRole]  # None = broadcast
    content: dict[str, Any]
    correlation_id: str


@dataclass
class AgentResult:
    """Result from an agent's analysis."""
    agent: AgentRole
    success: bool
    data: dict[str, Any]
    confidence: float  # 0.0 - 1.0
    sources: list[str]
    reasoning: str
    errors: list[str] = None


class BaseAgent(ABC):
    """Abstract base class for all specialist agents."""
    
    role: AgentRole
    
    def __init__(self, config: dict[str, Any] = None):
        self.config = config or {}
        self.logger = logger.bind(agent=self.role.value)
    
    @abstractmethod
    async def analyze(self, context: dict[str, Any]) -> AgentResult:
        """
        Perform the agent's specialized analysis.
        
        Args:
            context: Research context including query, scope, and any 
                    prior agent results
        
        Returns:
            AgentResult with analysis data, confidence, and reasoning
        """
        pass
    
    @abstractmethod
    async def validate_inputs(self, context: dict[str, Any]) -> bool:
        """Validate that required inputs are present."""
        pass
    
    async def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Handle incoming messages from other agents."""
        self.logger.info("received_message", sender=message.sender.value)
        return None  # Default: no response
    
    def get_confidence_level(self, confidence: float) -> str:
        """Convert numeric confidence to human-readable level."""
        if confidence >= 0.8:
            return "High"
        elif confidence >= 0.5:
            return "Medium"
        return "Low"
