"""Supply Chain Analyst agent for company relationship mapping and supply chain analysis."""

from typing import Dict, List, Any, Optional, Set
import asyncio
from datetime import datetime, timedelta
import json
import re

import structlog
import anthropic
import httpx

from src.core.config import settings
from src.core.database import DatabaseManager  
from src.data.models import Company, CompanyAnalysis
from src.data.clients.finnhub_client import FinnhubClient
from .base import BaseAgent, AgentRole, AgentResult


class SupplyChainAnalystAgent(BaseAgent):
    """
    Supply Chain Analyst agent responsible for:
    - Mapping company relationships (suppliers, customers, partners)
    - Identifying supply chain dependencies and vulnerabilities
    - Analyzing second and third-order effects
    - Detecting supply chain risks and opportunities
    - Creating company relationship networks
    """
    
    role = AgentRole.SUPPLY_CHAIN_ANALYST
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.client = anthropic.Anthropic(api_key=settings.api.anthropic_api_key)
        self.finnhub_client = FinnhubClient()
        self.model = settings.agents.get('supply_chain_analyst_model', 'claude-3-sonnet-20240229')
        
        # Common supply chain relationship types
        self.relationship_types = {
            'supplier': 'Companies that provide goods/services to target company',
            'customer': 'Companies that purchase goods/services from target company',
            'partner': 'Strategic partnerships, joint ventures, alliances',
            'competitor': 'Direct and indirect competitors in same market',
            'distributor': 'Companies that distribute/sell target company products',
            'contractor': 'Third-party service providers',
            'subsidiary': 'Owned or controlled entities',
            'parent': 'Parent or controlling entities'
        }
        
    async def validate_inputs(self, context: Dict[str, Any]) -> bool:
        """Validate that required inputs are present."""
        required_fields = ['project_id', 'companies']
        
        for field in required_fields:
            if field not in context:
                self.logger.error("missing_required_field", field=field)
                return False
        
        companies = context.get('companies', [])
        if not companies:
            self.logger.error("no_companies_provided")
            return False
            
        return True
    
    async def analyze(self, context: Dict[str, Any]) -> AgentResult:
        """Perform supply chain analysis of companies and their relationships."""
        
        self.logger.info("supply_chain_analysis_started", 
                        companies_count=len(context.get('companies', [])))
        
        try:
            companies = context.get('companies', [])
            project_id = context['project_id']
            investment_thesis = context.get('investment_thesis', '')
            
            # Analyze each company's supply chain
            company_analyses = []
            relationship_network = {}
            
            for company in companies:
                symbol = company.get('symbol')
                if not symbol:
                    continue
                    
                self.logger.info("analyzing_company_relationships", symbol=symbol)
                
                # Get company relationships
                relationships = await self._extract_company_relationships(symbol, company)
                
                # Analyze supply chain risks and opportunities
                analysis = await self._analyze_supply_chain_impact(
                    symbol, company, relationships, investment_thesis
                )
                
                company_analyses.append({
                    'symbol': symbol,
                    'company_name': company.get('name', symbol),
                    'relationships': relationships,
                    'supply_chain_analysis': analysis,
                    'risk_score': analysis.get('overall_risk_score', 0.5),
                    'opportunity_score': analysis.get('opportunity_score', 0.5)
                })
                
                relationship_network[symbol] = relationships
            
            # Create network-level analysis
            network_analysis = await self._analyze_relationship_network(
                relationship_network, investment_thesis
            )
            
            # Calculate confidence based on data quality and completeness
            confidence = await self._calculate_confidence(company_analyses, network_analysis)
            
            result_data = {
                'company_analyses': company_analyses,
                'network_analysis': network_analysis,
                'analysis_timestamp': datetime.now().isoformat(),
                'methodology': self._get_methodology_summary()
            }
            
            self.logger.info("supply_chain_analysis_completed", 
                           confidence=confidence,
                           companies_analyzed=len(company_analyses))
            
            return AgentResult(
                agent=self.role,
                success=True,
                data=result_data,
                confidence=confidence,
                sources=self._get_data_sources(),
                reasoning=self._generate_analysis_reasoning(result_data),
                errors=None
            )
            
        except Exception as e:
            self.logger.error("supply_chain_analysis_failed", error=str(e))
            return AgentResult(
                agent=self.role,
                success=False,
                data={},
                confidence=0.0,
                sources=[],
                reasoning=f"Analysis failed: {str(e)}",
                errors=[str(e)]
            )
    
    async def _extract_company_relationships(self, symbol: str, company_data: Dict) -> Dict[str, List[Dict]]:
        """Extract company relationships from multiple sources."""
        relationships = {rel_type: [] for rel_type in self.relationship_types.keys()}
        
        try:
            # Get company profile from Finnhub (includes some relationship data)
            profile = await self.finnhub_client.get_company_profile(symbol)
            
            # Use LLM to extract relationships from company description and news
            if profile.get('description'):
                llm_relationships = await self._llm_extract_relationships(
                    symbol, profile['description'], company_data
                )
                
                for rel_type, entities in llm_relationships.items():
                    relationships[rel_type].extend(entities)
            
            # Get recent news and extract relationship mentions
            news_relationships = await self._extract_relationships_from_news(symbol)
            for rel_type, entities in news_relationships.items():
                relationships[rel_type].extend(entities)
            
            # Remove duplicates and validate
            for rel_type in relationships:
                relationships[rel_type] = self._deduplicate_relationships(
                    relationships[rel_type]
                )
            
        except Exception as e:
            self.logger.warning("relationship_extraction_error", 
                              symbol=symbol, error=str(e))
        
        return relationships
    
    async def _llm_extract_relationships(self, symbol: str, description: str, 
                                       company_data: Dict) -> Dict[str, List[Dict]]:
        """Use LLM to extract company relationships from text."""
        
        prompt = f"""
        Analyze the following company information and extract key business relationships.
        
        Company: {symbol}
        Name: {company_data.get('name', 'Unknown')}
        Description: {description}
        
        Please identify and categorize companies that have relationships with {symbol} into these categories:
        - Suppliers: Companies that provide goods/services TO {symbol}
        - Customers: Companies that purchase goods/services FROM {symbol}  
        - Partners: Strategic partners, joint ventures, alliances
        - Competitors: Direct competitors in same markets
        - Distributors: Companies that sell/distribute {symbol}'s products
        - Subsidiaries: Companies owned/controlled by {symbol}
        - Parent: Companies that own/control {symbol}
        
        For each relationship, provide:
        - Company name and ticker symbol (if known)
        - Relationship type
        - Brief description of the relationship
        - Confidence level (high/medium/low)
        
        Return as JSON with this structure:
        {{
            "suppliers": [
                {{"name": "Company Name", "symbol": "TICK", "description": "brief desc", "confidence": "high"}}
            ],
            "customers": [...],
            "partners": [...],
            "competitors": [...],
            "distributors": [...],
            "subsidiaries": [...],
            "parent": [...]
        }}
        
        Only include relationships you're confident about. Return empty arrays for categories with no clear relationships.
        """
        
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Extract JSON from response
            content = response.content[0].text
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
            if json_match:
                relationships_data = json.loads(json_match.group())
                return relationships_data
            else:
                self.logger.warning("no_json_found_in_llm_response", symbol=symbol)
                return {rel_type: [] for rel_type in self.relationship_types.keys()}
                
        except Exception as e:
            self.logger.error("llm_relationship_extraction_failed", 
                            symbol=symbol, error=str(e))
            return {rel_type: [] for rel_type in self.relationship_types.keys()}
    
    async def _extract_relationships_from_news(self, symbol: str) -> Dict[str, List[Dict]]:
        """Extract company relationships mentioned in recent news."""
        relationships = {rel_type: [] for rel_type in self.relationship_types.keys()}
        
        try:
            # Get recent news
            news = await self.finnhub_client.get_company_news(symbol, days_back=30)
            
            if not news:
                return relationships
            
            # Analyze news headlines and summaries for relationship keywords
            news_text = " ".join([
                f"{item.get('headline', '')} {item.get('summary', '')}" 
                for item in news[:10]  # Analyze top 10 recent news items
            ])
            
            if len(news_text) > 100:  # Only if we have substantial text
                news_relationships = await self._llm_extract_relationships(
                    symbol, news_text, {'name': symbol}
                )
                
                for rel_type, entities in news_relationships.items():
                    for entity in entities:
                        entity['source'] = 'news'
                        entity['confidence'] = 'medium'  # Lower confidence from news
                    
                    relationships[rel_type].extend(entities)
            
        except Exception as e:
            self.logger.warning("news_relationship_extraction_error", 
                              symbol=symbol, error=str(e))
        
        return relationships
    
    async def _analyze_supply_chain_impact(self, symbol: str, company_data: Dict, 
                                         relationships: Dict, investment_thesis: str) -> Dict:
        """Analyze supply chain risks and opportunities for investment thesis."""
        
        prompt = f"""
        Analyze the supply chain implications for investment thesis.
        
        Company: {symbol} - {company_data.get('name', 'Unknown')}
        Investment Thesis: {investment_thesis}
        
        Company Relationships:
        {json.dumps(relationships, indent=2)}
        
        Please analyze:
        1. Supply Chain Risks:
           - Single points of failure
           - Geographic concentration risks  
           - Supplier dependency risks
           - Customer concentration risks
           - Competitive pressures from relationships
        
        2. Supply Chain Opportunities:
           - Strategic partnerships that support thesis
           - Supplier advantages (cost, quality, exclusivity)
           - Customer relationships that drive growth
           - Market position strengthening
           - Vertical integration opportunities
        
        3. Second-Order Effects:
           - How changes to suppliers/customers could impact the company
           - Ripple effects through the supply chain
           - Industry-wide disruption potential
        
        4. Investment Thesis Impact:
           - How supply chain supports or threatens the thesis
           - Key supply chain factors to monitor
           - Supply chain catalysts for thesis realization
        
        Provide scores (0.0-1.0):
        - Overall risk score (0.0 = low risk, 1.0 = high risk)
        - Opportunity score (0.0 = low opportunity, 1.0 = high opportunity)
        - Thesis alignment score (0.0 = harmful to thesis, 1.0 = strongly supports)
        
        Return as JSON with detailed analysis and scores.
        """
        
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
            if json_match:
                analysis = json.loads(json_match.group())
                return analysis
            else:
                # Fallback basic analysis
                return {
                    'supply_chain_risks': ['Unable to perform detailed analysis'],
                    'supply_chain_opportunities': [],
                    'second_order_effects': [],
                    'thesis_impact': 'Analysis unavailable',
                    'overall_risk_score': 0.5,
                    'opportunity_score': 0.3,
                    'thesis_alignment_score': 0.5
                }
                
        except Exception as e:
            self.logger.error("supply_chain_impact_analysis_failed", 
                            symbol=symbol, error=str(e))
            return {
                'supply_chain_risks': [f'Analysis failed: {str(e)}'],
                'supply_chain_opportunities': [],
                'second_order_effects': [],
                'thesis_impact': 'Analysis failed',
                'overall_risk_score': 0.5,
                'opportunity_score': 0.3,
                'thesis_alignment_score': 0.5
            }
    
    async def _analyze_relationship_network(self, relationship_network: Dict, 
                                          investment_thesis: str) -> Dict:
        """Analyze the overall relationship network across all companies."""
        
        # Find interconnections between companies in our analysis
        interconnections = []
        companies = list(relationship_network.keys())
        
        for i, company1 in enumerate(companies):
            for j, company2 in enumerate(companies[i+1:], i+1):
                connections = self._find_interconnections(
                    company1, company2, relationship_network
                )
                if connections:
                    interconnections.extend(connections)
        
        # Identify network-level risks and opportunities
        network_risks = self._identify_network_risks(relationship_network, interconnections)
        network_opportunities = self._identify_network_opportunities(
            relationship_network, interconnections, investment_thesis
        )
        
        return {
            'interconnections': interconnections,
            'network_risks': network_risks,
            'network_opportunities': network_opportunities,
            'portfolio_diversification': self._assess_diversification(relationship_network),
            'systemic_risk_score': self._calculate_systemic_risk(relationship_network)
        }
    
    def _find_interconnections(self, company1: str, company2: str, 
                              network: Dict) -> List[Dict]:
        """Find direct connections between two companies."""
        connections = []
        
        # Check if company1 appears in company2's relationships
        for rel_type, relationships in network.get(company2, {}).items():
            for rel in relationships:
                if (rel.get('symbol') == company1 or 
                    company1.lower() in rel.get('name', '').lower()):
                    connections.append({
                        'company1': company1,
                        'company2': company2, 
                        'relationship': rel_type,
                        'description': rel.get('description', ''),
                        'confidence': rel.get('confidence', 'medium')
                    })
        
        # Check if company2 appears in company1's relationships  
        for rel_type, relationships in network.get(company1, {}).items():
            for rel in relationships:
                if (rel.get('symbol') == company2 or 
                    company2.lower() in rel.get('name', '').lower()):
                    connections.append({
                        'company1': company1,
                        'company2': company2,
                        'relationship': rel_type,
                        'description': rel.get('description', ''),
                        'confidence': rel.get('confidence', 'medium')
                    })
        
        return connections
    
    def _identify_network_risks(self, network: Dict, interconnections: List[Dict]) -> List[str]:
        """Identify portfolio-level supply chain risks."""
        risks = []
        
        # Check for common suppliers/customers across portfolio
        common_entities = {}
        for company, relationships in network.items():
            for rel_type in ['supplier', 'customer']:
                for rel in relationships.get(rel_type, []):
                    entity_name = rel.get('name', '').lower()
                    if entity_name:
                        if entity_name not in common_entities:
                            common_entities[entity_name] = []
                        common_entities[entity_name].append((company, rel_type))
        
        # Identify concentration risks
        for entity, companies in common_entities.items():
            if len(companies) > 1:
                company_list = [c[0] for c in companies]
                risks.append(f"Concentration risk: {entity} is connected to multiple portfolio companies: {', '.join(company_list)}")
        
        # Check for cyclical dependencies
        if interconnections:
            risks.append(f"Found {len(interconnections)} direct interconnections between portfolio companies")
        
        return risks
    
    def _identify_network_opportunities(self, network: Dict, interconnections: List[Dict], 
                                      thesis: str) -> List[str]:
        """Identify portfolio-level supply chain opportunities."""
        opportunities = []
        
        # Synergies from interconnections
        if interconnections:
            opportunities.append(f"Portfolio synergies: {len(interconnections)} interconnections may create value")
        
        # Complementary supply chains
        supplier_coverage = set()
        customer_coverage = set()
        
        for company, relationships in network.items():
            for supplier in relationships.get('supplier', []):
                supplier_coverage.add(supplier.get('name', '').lower())
            for customer in relationships.get('customer', []):
                customer_coverage.add(customer.get('name', '').lower())
        
        if len(supplier_coverage) > len(network) * 2:
            opportunities.append("Diversified supplier base across portfolio reduces supplier risk")
        
        if len(customer_coverage) > len(network) * 2:
            opportunities.append("Diversified customer base across portfolio reduces customer concentration risk")
        
        return opportunities
    
    def _assess_diversification(self, network: Dict) -> str:
        """Assess portfolio diversification from supply chain perspective."""
        if not network:
            return "No data available"
        
        total_relationships = sum(
            len(relationships.get('supplier', [])) + len(relationships.get('customer', []))
            for relationships in network.values()
        )
        
        avg_relationships_per_company = total_relationships / len(network)
        
        if avg_relationships_per_company > 10:
            return "Well-diversified supply chain relationships"
        elif avg_relationships_per_company > 5:
            return "Moderately diversified supply chain relationships"
        else:
            return "Limited supply chain relationship diversity"
    
    def _calculate_systemic_risk(self, network: Dict) -> float:
        """Calculate portfolio-level systemic risk score."""
        if not network:
            return 0.5
        
        risk_factors = []
        
        # Calculate average risk scores
        total_companies = len(network)
        if total_companies == 0:
            return 0.5
        
        # This is a simplified calculation - in practice would be more sophisticated
        base_risk = 0.3  # Base systemic risk
        
        # Add risk for interconnections
        interconnection_penalty = min(0.2, len(network) * 0.05)
        
        return min(1.0, base_risk + interconnection_penalty)
    
    def _deduplicate_relationships(self, relationships: List[Dict]) -> List[Dict]:
        """Remove duplicate relationships and merge similar ones."""
        if not relationships:
            return relationships
        
        seen = {}
        deduplicated = []
        
        for rel in relationships:
            key = f"{rel.get('name', '').lower()}_{rel.get('symbol', '').lower()}"
            
            if key not in seen:
                seen[key] = rel
                deduplicated.append(rel)
            else:
                # Merge confidence levels (take highest)
                existing = seen[key]
                confidence_map = {'high': 3, 'medium': 2, 'low': 1}
                
                existing_conf = confidence_map.get(existing.get('confidence', 'medium'), 2)
                new_conf = confidence_map.get(rel.get('confidence', 'medium'), 2)
                
                if new_conf > existing_conf:
                    existing['confidence'] = rel.get('confidence', 'medium')
        
        return deduplicated
    
    async def _calculate_confidence(self, company_analyses: List[Dict], 
                                  network_analysis: Dict) -> float:
        """Calculate overall confidence in the supply chain analysis."""
        if not company_analyses:
            return 0.1
        
        # Base confidence on data quality
        base_confidence = 0.4
        
        # Boost confidence based on number of companies analyzed
        company_bonus = min(0.2, len(company_analyses) * 0.05)
        
        # Boost confidence based on relationship data quality
        total_relationships = sum(
            sum(len(rels) for rels in analysis.get('relationships', {}).values())
            for analysis in company_analyses
        )
        
        relationship_bonus = min(0.2, total_relationships * 0.01)
        
        # Reduce confidence if many errors
        error_penalty = 0.0
        for analysis in company_analyses:
            if 'error' in str(analysis.get('supply_chain_analysis', {})).lower():
                error_penalty += 0.05
        
        final_confidence = base_confidence + company_bonus + relationship_bonus - error_penalty
        return max(0.1, min(0.9, final_confidence))
    
    def _get_data_sources(self) -> List[str]:
        """Get list of data sources used."""
        return [
            "Finnhub Company Profiles",
            "Finnhub Company News",
            "Claude LLM Analysis",
            "Relationship Network Analysis"
        ]
    
    def _generate_analysis_reasoning(self, result_data: Dict) -> str:
        """Generate human-readable reasoning for the analysis."""
        company_count = len(result_data.get('company_analyses', []))
        
        reasoning = f"Analyzed supply chain relationships for {company_count} companies. "
        
        total_relationships = sum(
            sum(len(rels) for rels in analysis.get('relationships', {}).values())
            for analysis in result_data.get('company_analyses', [])
        )
        
        reasoning += f"Identified {total_relationships} total business relationships. "
        
        network_risks = len(result_data.get('network_analysis', {}).get('network_risks', []))
        network_opportunities = len(result_data.get('network_analysis', {}).get('network_opportunities', []))
        
        reasoning += f"Found {network_risks} network-level risks and {network_opportunities} opportunities. "
        
        reasoning += "Analysis combines company relationship mapping with investment thesis alignment assessment."
        
        return reasoning
    
    def _get_methodology_summary(self) -> Dict[str, str]:
        """Get summary of analysis methodology."""
        return {
            'relationship_extraction': 'LLM analysis of company descriptions and recent news',
            'network_analysis': 'Graph analysis of interconnections and dependencies',
            'risk_assessment': 'Multi-factor risk scoring including concentration and systemic risks',
            'opportunity_identification': 'Strategic relationship and synergy analysis',
            'thesis_alignment': 'Investment thesis relevance scoring for supply chain factors'
        }