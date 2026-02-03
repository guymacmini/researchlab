"""Agent orchestrator for coordinating multi-agent research workflows."""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Set
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import DatabaseManager
from src.data.models import ResearchProject, AgentAnalysis, ResearchStatus
from .base import BaseAgent, AgentRole, AgentMessage, AgentResult
from .research_director import ResearchDirectorAgent
from .fundamental_analyst import FundamentalAnalystAgent
from .supply_chain_analyst import SupplyChainAnalystAgent

logger = structlog.get_logger()


class AgentOrchestrator:
    """Orchestrates multi-agent research workflows."""
    
    def __init__(self):
        self.agents: Dict[AgentRole, BaseAgent] = {}
        self.active_sessions: Dict[str, 'ResearchSession'] = {}
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.logger = logger.bind(component="orchestrator")
        
        # Initialize available agents
        self._initialize_agents()
        
    def _initialize_agents(self) -> None:
        """Initialize all available agent types."""
        self.agents = {
            AgentRole.RESEARCH_DIRECTOR: ResearchDirectorAgent(),
            AgentRole.FUNDAMENTAL_ANALYST: FundamentalAnalystAgent(),
            AgentRole.SUPPLY_CHAIN_ANALYST: SupplyChainAnalystAgent(),
            # TODO: Add other agents as they're implemented
        }
        
        self.logger.info("agents_initialized", count=len(self.agents))
    
    async def start_research_project(
        self,
        project_id: str,
        agent_roles: Optional[List[AgentRole]] = None
    ) -> 'ResearchSession':
        """Start a new research project with specified agents."""
        
        if agent_roles is None:
            agent_roles = [AgentRole.RESEARCH_DIRECTOR, AgentRole.FUNDAMENTAL_ANALYST]
        
        correlation_id = str(uuid.uuid4())
        
        session = ResearchSession(
            project_id=project_id,
            correlation_id=correlation_id,
            orchestrator=self,
            agent_roles=agent_roles
        )
        
        self.active_sessions[project_id] = session
        
        self.logger.info(
            "research_session_started",
            project_id=project_id,
            correlation_id=correlation_id,
            agents=len(agent_roles)
        )
        
        return session
    
    async def execute_research_workflow(
        self,
        project_id: str,
        agent_roles: Optional[List[AgentRole]] = None
    ) -> Dict[AgentRole, AgentResult]:
        """Execute a complete research workflow."""
        
        session = await self.start_research_project(project_id, agent_roles)
        return await session.execute_workflow()
    
    async def send_message(self, message: AgentMessage) -> None:
        """Send a message through the orchestrator."""
        await self.message_queue.put(message)
        
        self.logger.debug(
            "message_sent",
            sender=message.sender.value,
            recipient=message.recipient.value if message.recipient else "broadcast",
            correlation_id=message.correlation_id
        )
    
    async def process_messages(self) -> None:
        """Process messages in the queue (background task)."""
        while True:
            try:
                message = await asyncio.wait_for(
                    self.message_queue.get(), timeout=1.0
                )
                
                # Route message to appropriate agents or sessions
                await self._route_message(message)
                
            except asyncio.TimeoutError:
                # No messages to process
                continue
            except Exception as e:
                self.logger.error("message_processing_error", error=str(e))
    
    async def _route_message(self, message: AgentMessage) -> None:
        """Route a message to the appropriate recipient."""
        
        if message.recipient:
            # Direct message to specific agent
            if message.recipient in self.agents:
                agent = self.agents[message.recipient]
                await agent.handle_message(message)
        else:
            # Broadcast message to all agents in the session
            for session in self.active_sessions.values():
                if session.correlation_id == message.correlation_id:
                    await session.handle_broadcast_message(message)
                    break
    
    def get_session(self, project_id: str) -> Optional['ResearchSession']:
        """Get an active research session."""
        return self.active_sessions.get(project_id)
    
    async def stop_research_project(self, project_id: str) -> None:
        """Stop and cleanup a research project."""
        if project_id in self.active_sessions:
            session = self.active_sessions[project_id]
            await session.cleanup()
            del self.active_sessions[project_id]
            
            self.logger.info("research_session_stopped", project_id=project_id)


class ResearchSession:
    """Represents an active research session with multiple agents."""
    
    def __init__(
        self,
        project_id: str,
        correlation_id: str,
        orchestrator: AgentOrchestrator,
        agent_roles: List[AgentRole]
    ):
        self.project_id = project_id
        self.correlation_id = correlation_id
        self.orchestrator = orchestrator
        self.agent_roles = agent_roles
        
        self.results: Dict[AgentRole, AgentResult] = {}
        self.active_agents: Set[AgentRole] = set()
        self.completed_agents: Set[AgentRole] = set()
        self.failed_agents: Set[AgentRole] = set()
        
        self.started_at = datetime.utcnow()
        self.logger = logger.bind(
            project_id=project_id,
            correlation_id=correlation_id
        )
    
    async def execute_workflow(self) -> Dict[AgentRole, AgentResult]:
        """Execute the complete research workflow."""
        
        self.logger.info("workflow_execution_started")
        
        try:
            # Update project status to in_progress
            await self._update_project_status(ResearchStatus.IN_PROGRESS)
            
            # Load project context
            context = await self._load_project_context()
            
            # Execute agents based on workflow dependencies
            if AgentRole.RESEARCH_DIRECTOR in self.agent_roles:
                # Start with Research Director for scope clarification
                await self._execute_agent(AgentRole.RESEARCH_DIRECTOR, context)
                
                # Update context with Research Director results
                if AgentRole.RESEARCH_DIRECTOR in self.results:
                    rd_result = self.results[AgentRole.RESEARCH_DIRECTOR]
                    if rd_result.success:
                        context.update(rd_result.data)
            
            # Execute remaining agents in parallel
            remaining_agents = [
                role for role in self.agent_roles 
                if role != AgentRole.RESEARCH_DIRECTOR
            ]
            
            if remaining_agents:
                tasks = [
                    self._execute_agent(role, context)
                    for role in remaining_agents
                ]
                await asyncio.gather(*tasks, return_exceptions=True)
            
            # Determine final project status
            if self.failed_agents:
                final_status = ResearchStatus.FAILED
            else:
                final_status = ResearchStatus.COMPLETED
            
            await self._update_project_status(final_status)
            
            self.logger.info(
                "workflow_execution_completed",
                completed=len(self.completed_agents),
                failed=len(self.failed_agents),
                total=len(self.agent_roles)
            )
            
            return self.results
            
        except Exception as e:
            self.logger.error("workflow_execution_failed", error=str(e))
            await self._update_project_status(ResearchStatus.FAILED)
            raise
    
    async def _execute_agent(self, role: AgentRole, context: dict) -> None:
        """Execute a specific agent."""
        
        if role not in self.orchestrator.agents:
            self.logger.error("agent_not_available", role=role.value)
            self.failed_agents.add(role)
            return
        
        agent = self.orchestrator.agents[role]
        self.active_agents.add(role)
        
        self.logger.info("agent_execution_started", agent=role.value)
        
        try:
            # Validate inputs
            if not await agent.validate_inputs(context):
                raise ValueError(f"Invalid inputs for agent {role.value}")
            
            # Execute agent analysis
            result = await agent.analyze(context)
            
            # Store result
            self.results[role] = result
            
            # Save to database
            await self._save_agent_result(role, result)
            
            if result.success:
                self.completed_agents.add(role)
                self.logger.info(
                    "agent_execution_completed",
                    agent=role.value,
                    confidence=result.confidence
                )
            else:
                self.failed_agents.add(role)
                self.logger.warning(
                    "agent_execution_failed",
                    agent=role.value,
                    errors=result.errors
                )
                
        except Exception as e:
            self.failed_agents.add(role)
            self.logger.error(
                "agent_execution_exception",
                agent=role.value,
                error=str(e)
            )
            
            # Create failure result
            self.results[role] = AgentResult(
                agent=role,
                success=False,
                data={},
                confidence=0.0,
                sources=[],
                reasoning=f"Agent execution failed: {str(e)}",
                errors=[str(e)]
            )
        
        finally:
            self.active_agents.discard(role)
    
    async def _load_project_context(self) -> dict:
        """Load project data as context for agents."""
        
        async with DatabaseManager() as db:
            project = await db.get(ResearchProject, self.project_id)
            
            if not project:
                raise ValueError(f"Project {self.project_id} not found")
            
            return {
                'project_id': self.project_id,
                'user_id': project.user_id,
                'query': project.query,
                'scope': project.scope,
                'correlation_id': self.correlation_id,
            }
    
    async def _update_project_status(self, status: ResearchStatus) -> None:
        """Update project status in database."""
        
        async with DatabaseManager() as db:
            project = await db.get(ResearchProject, self.project_id)
            
            if project:
                project.status = status.value
                
                if status == ResearchStatus.IN_PROGRESS and not project.started_at:
                    project.started_at = datetime.utcnow()
                elif status in [ResearchStatus.COMPLETED, ResearchStatus.FAILED]:
                    project.completed_at = datetime.utcnow()
                
                await db.commit()
    
    async def _save_agent_result(self, role: AgentRole, result: AgentResult) -> None:
        """Save agent result to database."""
        
        async with DatabaseManager() as db:
            analysis = AgentAnalysis(
                project_id=self.project_id,
                agent_role=role.value,
                success=result.success,
                confidence=result.confidence,
                data=result.data,
                reasoning=result.reasoning,
                sources=result.sources,
                errors=result.errors,
                started_at=self.started_at,
                completed_at=datetime.utcnow(),
                duration_seconds=(datetime.utcnow() - self.started_at).total_seconds()
            )
            
            db.add(analysis)
            await db.commit()
    
    async def handle_broadcast_message(self, message: AgentMessage) -> None:
        """Handle a broadcast message within this session."""
        
        for role in self.agent_roles:
            if role in self.orchestrator.agents and role != message.sender:
                agent = self.orchestrator.agents[role]
                await agent.handle_message(message)
    
    async def cleanup(self) -> None:
        """Clean up session resources."""
        self.active_agents.clear()
        self.logger.info("session_cleanup_completed")


# Global orchestrator instance
_orchestrator: Optional[AgentOrchestrator] = None


async def get_orchestrator() -> AgentOrchestrator:
    """Get the global agent orchestrator instance."""
    global _orchestrator
    
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
        
        # Start background message processing
        asyncio.create_task(_orchestrator.process_messages())
    
    return _orchestrator