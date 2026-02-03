"""SEC EDGAR data integration for financial document parsing."""

import re
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
import xml.etree.ElementTree as ET

import httpx
import pandas as pd
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.logging import get_logger
from src.data.clients.base_client import BaseDataClient


logger = get_logger(__name__)


class SECFiling(BaseModel):
    """Represents an SEC filing."""
    
    cik: str = Field(..., description="Central Index Key")
    company_name: str = Field(..., description="Company name")
    form_type: str = Field(..., description="Form type (10-K, 10-Q, etc.)")
    filing_date: datetime = Field(..., description="Filing date")
    accession_number: str = Field(..., description="Accession number")
    document_url: str = Field(..., description="Document URL")
    
    # Parsed financial data
    financial_data: Optional[Dict[str, Any]] = Field(default=None)
    business_description: Optional[str] = Field(default=None)
    risk_factors: Optional[List[str]] = Field(default=None)
    management_discussion: Optional[str] = Field(default=None)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class FinancialStatement(BaseModel):
    """Represents parsed financial statement data."""
    
    statement_type: str = Field(..., description="Type of statement (income, balance, cash)")
    period_end: datetime = Field(..., description="Period end date")
    currency: str = Field(default="USD", description="Currency")
    
    # Income Statement
    revenue: Optional[float] = Field(default=None)
    gross_profit: Optional[float] = Field(default=None)
    operating_income: Optional[float] = Field(default=None)
    net_income: Optional[float] = Field(default=None)
    eps_basic: Optional[float] = Field(default=None)
    eps_diluted: Optional[float] = Field(default=None)
    
    # Balance Sheet
    total_assets: Optional[float] = Field(default=None)
    current_assets: Optional[float] = Field(default=None)
    total_liabilities: Optional[float] = Field(default=None)
    current_liabilities: Optional[float] = Field(default=None)
    shareholders_equity: Optional[float] = Field(default=None)
    cash_and_equivalents: Optional[float] = Field(default=None)
    
    # Cash Flow Statement
    operating_cash_flow: Optional[float] = Field(default=None)
    investing_cash_flow: Optional[float] = Field(default=None)
    financing_cash_flow: Optional[float] = Field(default=None)
    free_cash_flow: Optional[float] = Field(default=None)
    
    # Additional metrics
    raw_data: Dict[str, Any] = Field(default_factory=dict)


class SECEDGARClient(BaseDataClient):
    """Client for accessing SEC EDGAR database."""
    
    def __init__(self):
        super().__init__()
        self.base_url = "https://www.sec.gov"
        self.api_base = f"{self.base_url}/files"
        self.company_tickers_url = f"{self.base_url}/files/company_tickers.json"
        
        # SEC requires User-Agent header
        self.headers = {
            "User-Agent": f"{settings.app.app_name} {settings.app.version} (contact@researchlab.ai)",
            "Accept": "application/json, text/html, application/xhtml+xml",
            "Accept-Encoding": "gzip, deflate",
            "Host": "www.sec.gov"
        }
        
        # Rate limiting: SEC allows 10 requests per second
        self.rate_limiter.set_limit("sec_edgar", 10, 1)
        
        # Cache for company mappings
        self._company_mappings: Optional[Dict[str, str]] = None
        
        logger.info("SEC EDGAR client initialized", component="sec_edgar")
    
    async def get_company_cik(self, symbol: str) -> Optional[str]:
        """Get CIK (Central Index Key) for a company symbol."""
        if not self._company_mappings:
            await self._load_company_mappings()
        
        # Normalize symbol
        symbol = symbol.upper().strip()
        
        # Look up CIK
        for cik, data in self._company_mappings.items():
            if data.get("ticker", "").upper() == symbol:
                return str(cik).zfill(10)  # Pad with zeros
        
        logger.warning(f"CIK not found for symbol {symbol}", component="sec_edgar")
        return None
    
    async def _load_company_mappings(self):
        """Load company ticker to CIK mappings."""
        try:
            await self.rate_limiter.acquire("sec_edgar")
            
            async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
                response = await client.get(self.company_tickers_url)
                response.raise_for_status()
                
                self._company_mappings = response.json()
                logger.info(
                    f"Loaded {len(self._company_mappings)} company mappings",
                    component="sec_edgar"
                )
        
        except Exception as e:
            logger.error(f"Failed to load company mappings: {e}", component="sec_edgar")
            self._company_mappings = {}
    
    async def get_company_filings(
        self,
        symbol: str,
        form_types: List[str] = None,
        limit: int = 10,
        before_date: Optional[datetime] = None
    ) -> List[SECFiling]:
        """Get company filings from SEC EDGAR."""
        if form_types is None:
            form_types = ["10-K", "10-Q"]
        
        cik = await self.get_company_cik(symbol)
        if not cik:
            logger.error(f"Cannot find CIK for symbol {symbol}", component="sec_edgar")
            return []
        
        try:
            await self.rate_limiter.acquire("sec_edgar")
            
            # Build submissions URL
            submissions_url = f"{self.api_base}/eid/data/{cik}/submissions.json"
            
            async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
                response = await client.get(submissions_url)
                response.raise_for_status()
                
                data = response.json()
                filings = self._parse_filings_response(data, form_types, limit, before_date)
                
                logger.info(
                    f"Retrieved {len(filings)} filings for {symbol}",
                    component="sec_edgar",
                    symbol=symbol,
                    filings_count=len(filings)
                )
                
                return filings
        
        except Exception as e:
            logger.error(
                f"Failed to get filings for {symbol}: {e}",
                component="sec_edgar",
                error=str(e)
            )
            return []
    
    def _parse_filings_response(
        self,
        data: Dict,
        form_types: List[str],
        limit: int,
        before_date: Optional[datetime]
    ) -> List[SECFiling]:
        """Parse SEC filings response data."""
        filings = []
        
        try:
            recent_filings = data.get("filings", {}).get("recent", {})
            
            if not recent_filings:
                return filings
            
            # Extract filing data
            forms = recent_filings.get("form", [])
            filing_dates = recent_filings.get("filingDate", [])
            accession_numbers = recent_filings.get("accessionNumber", [])
            primary_documents = recent_filings.get("primaryDocument", [])
            
            company_name = data.get("name", "Unknown Company")
            cik = data.get("cik", "")
            
            for i in range(len(forms)):
                form_type = forms[i]
                
                # Filter by form type
                if form_type not in form_types:
                    continue
                
                # Parse filing date
                try:
                    filing_date = datetime.strptime(filing_dates[i], "%Y-%m-%d")
                except (ValueError, IndexError):
                    continue
                
                # Filter by date
                if before_date and filing_date >= before_date:
                    continue
                
                # Build document URL
                accession_clean = accession_numbers[i].replace("-", "")
                document_url = (
                    f"{self.base_url}/Archives/edgar/data/{cik}/"
                    f"{accession_clean}/{primary_documents[i]}"
                )
                
                filing = SECFiling(
                    cik=str(cik).zfill(10),
                    company_name=company_name,
                    form_type=form_type,
                    filing_date=filing_date,
                    accession_number=accession_numbers[i],
                    document_url=document_url
                )
                
                filings.append(filing)
                
                # Apply limit
                if len(filings) >= limit:
                    break
            
            # Sort by filing date (most recent first)
            filings.sort(key=lambda x: x.filing_date, reverse=True)
            
        except Exception as e:
            logger.error(f"Failed to parse filings response: {e}", component="sec_edgar")
        
        return filings
    
    async def download_filing_document(self, filing: SECFiling) -> Optional[str]:
        """Download the full filing document."""
        try:
            await self.rate_limiter.acquire("sec_edgar")
            
            async with httpx.AsyncClient(headers=self.headers, timeout=60) as client:
                response = await client.get(filing.document_url)
                response.raise_for_status()
                
                logger.debug(
                    f"Downloaded filing document",
                    component="sec_edgar",
                    form_type=filing.form_type,
                    filing_date=filing.filing_date.isoformat()
                )
                
                return response.text
        
        except Exception as e:
            logger.error(
                f"Failed to download filing document: {e}",
                component="sec_edgar",
                document_url=filing.document_url
            )
            return None


class SECDocumentParser:
    """Parser for SEC filing documents."""
    
    def __init__(self):
        self.logger = get_logger(f"{__name__}.parser")
        
        # Common financial statement patterns
        self.revenue_patterns = [
            r"total\s+(?:net\s+)?(?:sales|revenue)",
            r"(?:net\s+)?revenue",
            r"sales\s+and\s+service\s+revenue",
            r"product\s+revenue",
            r"service\s+revenue"
        ]
        
        self.net_income_patterns = [
            r"net\s+income\s+(?:\(loss\))?",
            r"net\s+earnings\s+(?:\(loss\))?",
            r"income\s+(?:\(loss\))\s+from\s+continuing\s+operations"
        ]
        
        self.assets_patterns = [
            r"total\s+assets",
            r"total\s+current\s+assets"
        ]
    
    async def parse_filing(self, filing: SECFiling, document_content: str) -> SECFiling:
        """Parse SEC filing document and extract structured data."""
        
        # Update filing with parsed data
        if filing.form_type in ["10-K", "10-Q"]:
            financial_data = await self._parse_financial_statements(document_content)
            business_desc = self._extract_business_description(document_content)
            risk_factors = self._extract_risk_factors(document_content)
            md_and_a = self._extract_management_discussion(document_content)
            
            filing.financial_data = financial_data
            filing.business_description = business_desc
            filing.risk_factors = risk_factors
            filing.management_discussion = md_and_a
        
        return filing
    
    async def _parse_financial_statements(self, content: str) -> Dict[str, Any]:
        """Parse financial statements from filing content."""
        
        # Parse both HTML and XBRL content
        financial_data = {
            "income_statement": {},
            "balance_sheet": {},
            "cash_flow": {},
            "parsing_metadata": {
                "parsed_at": datetime.now().isoformat(),
                "method": "regex_and_table_extraction"
            }
        }
        
        try:
            # Try to parse structured tables first
            soup = BeautifulSoup(content, 'html.parser')
            
            # Find financial tables
            tables = soup.find_all('table')
            
            for table in tables:
                table_text = table.get_text().lower()
                
                # Identify statement type
                if any(term in table_text for term in ['income', 'operations', 'earnings']):
                    income_data = self._parse_income_statement_table(table)
                    financial_data["income_statement"].update(income_data)
                
                elif any(term in table_text for term in ['balance sheet', 'financial position']):
                    balance_data = self._parse_balance_sheet_table(table)
                    financial_data["balance_sheet"].update(balance_data)
                
                elif any(term in table_text for term in ['cash flow', 'cash flows']):
                    cash_data = self._parse_cash_flow_table(table)
                    financial_data["cash_flow"].update(cash_data)
            
            # Fallback to regex parsing if tables don't work
            if not any(financial_data[key] for key in ["income_statement", "balance_sheet", "cash_flow"]):
                financial_data = self._parse_with_regex(content)
        
        except Exception as e:
            self.logger.error(f"Failed to parse financial statements: {e}")
            financial_data["parsing_metadata"]["error"] = str(e)
        
        return financial_data
    
    def _parse_income_statement_table(self, table) -> Dict[str, float]:
        """Parse income statement from HTML table."""
        data = {}
        
        try:
            rows = table.find_all('tr')
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) < 2:
                    continue
                
                label = cells[0].get_text().strip().lower()
                
                # Look for revenue
                if any(pattern in label for pattern in ['revenue', 'sales', 'total revenue']):
                    value = self._extract_number_from_cell(cells[1])
                    if value:
                        data['revenue'] = value
                
                # Look for net income
                elif any(pattern in label for pattern in ['net income', 'net earnings']):
                    value = self._extract_number_from_cell(cells[1])
                    if value:
                        data['net_income'] = value
                
                # Look for operating income
                elif 'operating income' in label or 'income from operations' in label:
                    value = self._extract_number_from_cell(cells[1])
                    if value:
                        data['operating_income'] = value
        
        except Exception as e:
            self.logger.debug(f"Error parsing income statement table: {e}")
        
        return data
    
    def _parse_balance_sheet_table(self, table) -> Dict[str, float]:
        """Parse balance sheet from HTML table."""
        data = {}
        
        try:
            rows = table.find_all('tr')
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) < 2:
                    continue
                
                label = cells[0].get_text().strip().lower()
                
                # Look for total assets
                if 'total assets' in label:
                    value = self._extract_number_from_cell(cells[1])
                    if value:
                        data['total_assets'] = value
                
                # Look for current assets
                elif 'current assets' in label and 'total' in label:
                    value = self._extract_number_from_cell(cells[1])
                    if value:
                        data['current_assets'] = value
                
                # Look for shareholders equity
                elif any(term in label for term in ['shareholders equity', 'stockholders equity', 'total equity']):
                    value = self._extract_number_from_cell(cells[1])
                    if value:
                        data['shareholders_equity'] = value
        
        except Exception as e:
            self.logger.debug(f"Error parsing balance sheet table: {e}")
        
        return data
    
    def _parse_cash_flow_table(self, table) -> Dict[str, float]:
        """Parse cash flow statement from HTML table."""
        data = {}
        
        try:
            rows = table.find_all('tr')
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) < 2:
                    continue
                
                label = cells[0].get_text().strip().lower()
                
                # Look for operating cash flow
                if 'operating activities' in label or 'cash from operations' in label:
                    value = self._extract_number_from_cell(cells[1])
                    if value:
                        data['operating_cash_flow'] = value
                
                # Look for investing cash flow
                elif 'investing activities' in label:
                    value = self._extract_number_from_cell(cells[1])
                    if value:
                        data['investing_cash_flow'] = value
                
                # Look for financing cash flow
                elif 'financing activities' in label:
                    value = self._extract_number_from_cell(cells[1])
                    if value:
                        data['financing_cash_flow'] = value
        
        except Exception as e:
            self.logger.debug(f"Error parsing cash flow table: {e}")
        
        return data
    
    def _extract_number_from_cell(self, cell) -> Optional[float]:
        """Extract numeric value from table cell."""
        try:
            text = cell.get_text().strip()
            
            # Remove common formatting
            text = re.sub(r'[^\d\.\-\(\)]+', '', text)
            text = text.replace('(', '-').replace(')', '')
            
            if text and text != '-':
                return float(text)
        
        except (ValueError, AttributeError):
            pass
        
        return None
    
    def _parse_with_regex(self, content: str) -> Dict[str, Any]:
        """Fallback regex-based parsing."""
        data = {
            "income_statement": {},
            "balance_sheet": {},
            "cash_flow": {},
            "parsing_metadata": {"method": "regex_fallback"}
        }
        
        # This would implement regex-based extraction
        # For now, return empty structure
        return data
    
    def _extract_business_description(self, content: str) -> Optional[str]:
        """Extract business description section."""
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for Item 1 - Business
            for element in soup.find_all(['p', 'div']):
                text = element.get_text()
                if 'item 1' in text.lower() and 'business' in text.lower():
                    # Extract following paragraphs
                    description_parts = []
                    current = element
                    
                    for _ in range(10):  # Look at next 10 elements
                        current = current.find_next(['p', 'div'])
                        if not current:
                            break
                        
                        para_text = current.get_text().strip()
                        if para_text and len(para_text) > 50:
                            description_parts.append(para_text)
                        
                        # Stop at next major section
                        if any(term in para_text.lower() for term in ['item 2', 'risk factors']):
                            break
                    
                    if description_parts:
                        return ' '.join(description_parts[:3])  # First 3 paragraphs
        
        except Exception as e:
            self.logger.debug(f"Error extracting business description: {e}")
        
        return None
    
    def _extract_risk_factors(self, content: str) -> List[str]:
        """Extract risk factors from filing."""
        risk_factors = []
        
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for Risk Factors section
            for element in soup.find_all(['p', 'div', 'h1', 'h2', 'h3']):
                text = element.get_text()
                if 'risk factors' in text.lower():
                    # Extract following list items or paragraphs
                    current = element
                    
                    for _ in range(20):  # Look at next 20 elements
                        current = current.find_next(['li', 'p', 'div'])
                        if not current:
                            break
                        
                        risk_text = current.get_text().strip()
                        if risk_text and len(risk_text) > 30:
                            risk_factors.append(risk_text)
                        
                        # Stop at next major section
                        if len(risk_factors) >= 10:  # Limit to top 10 risks
                            break
        
        except Exception as e:
            self.logger.debug(f"Error extracting risk factors: {e}")
        
        return risk_factors[:10]  # Return top 10 risk factors
    
    def _extract_management_discussion(self, content: str) -> Optional[str]:
        """Extract Management Discussion and Analysis section."""
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for MD&A section
            for element in soup.find_all(['p', 'div']):
                text = element.get_text().lower()
                if ('management' in text and 'discussion' in text and 'analysis' in text) or \
                   'md&a' in text:
                    
                    # Extract following content
                    md_a_parts = []
                    current = element
                    
                    for _ in range(15):  # Look at next 15 elements
                        current = current.find_next(['p', 'div'])
                        if not current:
                            break
                        
                        para_text = current.get_text().strip()
                        if para_text and len(para_text) > 50:
                            md_a_parts.append(para_text)
                        
                        # Stop at next major section
                        if 'item' in para_text.lower() and len(md_a_parts) > 3:
                            break
                    
                    if md_a_parts:
                        return ' '.join(md_a_parts[:5])  # First 5 paragraphs
        
        except Exception as e:
            self.logger.debug(f"Error extracting MD&A: {e}")
        
        return None


class SECEDGARManager:
    """High-level manager for SEC EDGAR operations."""
    
    def __init__(self):
        self.client = SECEDGARClient()
        self.parser = SECDocumentParser()
        self.logger = get_logger(f"{__name__}.manager")
    
    async def get_company_financial_data(
        self,
        symbol: str,
        periods: int = 4,
        include_quarterly: bool = True
    ) -> Dict[str, Any]:
        """Get comprehensive financial data for a company."""
        
        try:
            # Determine form types
            form_types = ["10-K"]
            if include_quarterly:
                form_types.append("10-Q")
            
            # Get recent filings
            filings = await self.client.get_company_filings(
                symbol=symbol,
                form_types=form_types,
                limit=periods * 2  # Get extra in case some fail to parse
            )
            
            if not filings:
                self.logger.warning(f"No filings found for {symbol}")
                return {"symbol": symbol, "filings": [], "financial_data": {}}
            
            # Process filings
            processed_filings = []
            
            for filing in filings[:periods]:
                try:
                    # Download document
                    document_content = await self.client.download_filing_document(filing)
                    
                    if document_content:
                        # Parse document
                        parsed_filing = await self.parser.parse_filing(filing, document_content)
                        processed_filings.append(parsed_filing)
                    
                    # Respect rate limiting
                    await asyncio.sleep(0.1)
                
                except Exception as e:
                    self.logger.error(f"Failed to process filing: {e}")
                    continue
            
            # Aggregate financial data
            financial_summary = self._aggregate_financial_data(processed_filings)
            
            result = {
                "symbol": symbol,
                "company_name": filings[0].company_name if filings else "Unknown",
                "cik": filings[0].cik if filings else "",
                "filings": [f.dict() for f in processed_filings],
                "financial_summary": financial_summary,
                "updated_at": datetime.now().isoformat()
            }
            
            self.logger.info(
                f"Successfully processed {len(processed_filings)} filings for {symbol}",
                symbol=symbol,
                filings_processed=len(processed_filings)
            )
            
            return result
        
        except Exception as e:
            self.logger.error(f"Failed to get financial data for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e)}
    
    def _aggregate_financial_data(self, filings: List[SECFiling]) -> Dict[str, Any]:
        """Aggregate financial data across multiple filings."""
        
        summary = {
            "periods_analyzed": len(filings),
            "latest_filing_date": None,
            "trends": {},
            "metrics": {}
        }
        
        if not filings:
            return summary
        
        # Sort by filing date
        filings.sort(key=lambda x: x.filing_date, reverse=True)
        summary["latest_filing_date"] = filings[0].filing_date.isoformat()
        
        # Extract metrics from each period
        periods_data = []
        
        for filing in filings:
            if filing.financial_data:
                period_data = {
                    "filing_date": filing.filing_date.isoformat(),
                    "form_type": filing.form_type,
                    "period_end": filing.filing_date.isoformat()  # Simplified
                }
                
                # Extract key metrics
                income = filing.financial_data.get("income_statement", {})
                balance = filing.financial_data.get("balance_sheet", {})
                cash_flow = filing.financial_data.get("cash_flow", {})
                
                period_data.update({
                    "revenue": income.get("revenue"),
                    "net_income": income.get("net_income"),
                    "operating_income": income.get("operating_income"),
                    "total_assets": balance.get("total_assets"),
                    "shareholders_equity": balance.get("shareholders_equity"),
                    "operating_cash_flow": cash_flow.get("operating_cash_flow")
                })
                
                periods_data.append(period_data)
        
        summary["periods_data"] = periods_data
        
        # Calculate trends if we have multiple periods
        if len(periods_data) >= 2:
            latest = periods_data[0]
            previous = periods_data[1]
            
            summary["trends"] = self._calculate_trends(latest, previous)
        
        return summary
    
    def _calculate_trends(self, latest: Dict, previous: Dict) -> Dict[str, Any]:
        """Calculate growth trends between periods."""
        trends = {}
        
        metrics_to_compare = [
            "revenue", "net_income", "operating_income", 
            "total_assets", "shareholders_equity", "operating_cash_flow"
        ]
        
        for metric in metrics_to_compare:
            latest_val = latest.get(metric)
            previous_val = previous.get(metric)
            
            if latest_val is not None and previous_val is not None and previous_val != 0:
                growth_rate = ((latest_val - previous_val) / abs(previous_val)) * 100
                trends[f"{metric}_growth"] = round(growth_rate, 2)
        
        return trends
    
    async def search_filings_by_content(
        self,
        symbol: str,
        search_terms: List[str],
        form_types: List[str] = None
    ) -> List[Dict[str, Any]]:
        """Search filing content for specific terms."""
        
        if form_types is None:
            form_types = ["10-K", "10-Q"]
        
        filings = await self.client.get_company_filings(
            symbol=symbol,
            form_types=form_types,
            limit=5  # Recent filings only
        )
        
        results = []
        
        for filing in filings:
            try:
                content = await self.client.download_filing_document(filing)
                if not content:
                    continue
                
                # Search for terms
                content_lower = content.lower()
                matches = []
                
                for term in search_terms:
                    if term.lower() in content_lower:
                        # Find context around the term
                        context = self._extract_context(content, term)
                        matches.append({
                            "term": term,
                            "context": context
                        })
                
                if matches:
                    results.append({
                        "filing": filing.dict(),
                        "matches": matches
                    })
            
            except Exception as e:
                self.logger.error(f"Error searching filing content: {e}")
                continue
        
        return results
    
    def _extract_context(self, content: str, term: str, context_length: int = 200) -> str:
        """Extract context around a search term."""
        content_lower = content.lower()
        term_lower = term.lower()
        
        index = content_lower.find(term_lower)
        if index == -1:
            return ""
        
        start = max(0, index - context_length // 2)
        end = min(len(content), index + len(term) + context_length // 2)
        
        context = content[start:end].strip()
        
        # Clean up context
        context = re.sub(r'\s+', ' ', context)
        
        return context