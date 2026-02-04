"""SEC EDGAR API client for filings and earnings call transcripts."""

import asyncio
import json
import re
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
import structlog

import httpx

logger = structlog.get_logger()


class SECClient:
    """
    SEC EDGAR API client for accessing public filings.
    
    Free API with rate limits: 10 requests per second, proper User-Agent required.
    Docs: https://www.sec.gov/edgar/sec-api-documentation
    """
    
    def __init__(self, user_agent: str = "ResearchLab/1.0 (institutional-research)"):
        self.base_url = "https://data.sec.gov"
        self.user_agent = user_agent
        self.session = httpx.AsyncClient(
            timeout=30.0,
            headers={
                'User-Agent': self.user_agent,
                'Accept-Encoding': 'gzip, deflate',
                'Host': 'data.sec.gov'
            }
        )
        self._last_request = None
        self._request_interval = 0.1  # 10 requests per second = 0.1s interval
    
    async def _rate_limit(self):
        """Implement SEC rate limiting (10 requests per second max)."""
        if self._last_request:
            elapsed = (datetime.utcnow() - self._last_request).total_seconds()
            if elapsed < self._request_interval:
                wait_time = self._request_interval - elapsed
                await asyncio.sleep(wait_time)
        
        self._last_request = datetime.utcnow()
    
    async def _request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make rate-limited request to SEC API."""
        await self._rate_limit()
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = await self.session.get(url, params=params)
            response.raise_for_status()
            
            # Handle different content types
            content_type = response.headers.get('content-type', '')
            
            if 'application/json' in content_type:
                return response.json()
            else:
                # Return text content for HTML/XML filings
                return {'content': response.text, 'content_type': content_type}
            
        except httpx.HTTPStatusError as e:
            logger.error("SEC API HTTP error", status=e.response.status_code, endpoint=endpoint)
            return {}
        except Exception as e:
            logger.error("SEC API request failed", error=str(e), endpoint=endpoint)
            return {}
    
    async def get_company_info(self, ticker: str) -> Dict[str, Any]:
        """Get company information and CIK number from ticker."""
        # SEC company tickers endpoint
        endpoint = "/files/company_tickers.json"
        response = await self._request(endpoint)
        
        if not response:
            return {}
        
        # Find company by ticker
        ticker_upper = ticker.upper()
        for company_data in response.values():
            if company_data.get('ticker', '').upper() == ticker_upper:
                return {
                    'cik': str(company_data['cik_str']).zfill(10),  # CIK with leading zeros
                    'ticker': company_data['ticker'],
                    'title': company_data['title'],
                    'found': True
                }
        
        logger.warning("Company not found in SEC database", ticker=ticker)
        return {'found': False}
    
    async def get_company_submissions(self, cik: str) -> Dict[str, Any]:
        """Get all submissions for a company by CIK."""
        endpoint = f"/submissions/CIK{cik.zfill(10)}.json"
        return await self._request(endpoint)
    
    async def get_recent_filings(self, ticker: str, form_types: List[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent filings for a company.
        
        Args:
            ticker: Stock ticker symbol
            form_types: List of form types to filter (e.g., ['10-K', '10-Q', '8-K'])
            limit: Maximum number of filings to return
        """
        if form_types is None:
            form_types = ['10-K', '10-Q', '8-K', 'DEF 14A']  # Key filing types
        
        # Get company info first
        company_info = await self.get_company_info(ticker)
        if not company_info.get('found'):
            return []
        
        cik = company_info['cik']
        
        # Get submissions
        submissions = await self.get_company_submissions(cik)
        if not submissions or 'filings' not in submissions:
            return []
        
        filings = submissions['filings']['recent']
        
        # Filter and format filings
        filtered_filings = []
        
        for i in range(min(len(filings['form']), limit * 3)):  # Get extra to filter
            form = filings['form'][i]
            
            if form in form_types:
                filing = {
                    'form': form,
                    'filing_date': filings['filingDate'][i],
                    'acceptance_date': filings['acceptanceDateTime'][i],
                    'accession_number': filings['accessionNumber'][i],
                    'primary_document': filings['primaryDocument'][i],
                    'primary_doc_description': filings['primaryDocDescription'][i],
                    'filing_url': f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{filings['accessionNumber'][i].replace('-', '')}/{filings['primaryDocument'][i]}",
                    'company': company_info['title'],
                    'ticker': ticker.upper()
                }
                
                filtered_filings.append(filing)
                
                if len(filtered_filings) >= limit:
                    break
        
        return filtered_filings
    
    async def get_filing_content(self, accession_number: str, document: str, cik: str) -> Dict[str, Any]:
        """Get the actual content of a filing."""
        # Remove hyphens from accession number for URL
        clean_accession = accession_number.replace('-', '')
        
        endpoint = f"/Archives/edgar/data/{int(cik)}/{clean_accession}/{document}"
        
        response = await self._request(endpoint)
        
        if response and 'content' in response:
            # Try to extract key sections for 10-K/10-Q filings
            content = response['content']
            
            if any(doc_type in document.lower() for doc_type in ['10-k', '10-q']):
                sections = self._extract_filing_sections(content)
                return {
                    'raw_content': content,
                    'sections': sections,
                    'content_type': response.get('content_type', ''),
                    'accession_number': accession_number,
                    'document': document
                }
        
        return response
    
    def _extract_filing_sections(self, content: str) -> Dict[str, str]:
        """Extract key sections from 10-K/10-Q filings."""
        sections = {}
        
        # Define section patterns for 10-K filings
        section_patterns = {
            'business': r'item\s+1\.\s*business',
            'risk_factors': r'item\s+1a\.\s*risk\s+factors',
            'properties': r'item\s+2\.\s*properties',
            'legal_proceedings': r'item\s+3\.\s*legal\s+proceedings',
            'management_discussion': r'item\s+7\.\s*management[\s\']s\s+discussion\s+and\s+analysis',
            'financial_statements': r'item\s+8\.\s*financial\s+statements',
            'controls_procedures': r'item\s+9a\.\s*controls\s+and\s+procedures'
        }
        
        content_lower = content.lower()
        
        for section_name, pattern in section_patterns.items():
            match = re.search(pattern, content_lower)
            if match:
                start_pos = match.start()
                
                # Find the next section or end of content
                next_item_match = re.search(r'item\s+\d+[a-z]?\.\s*', content_lower[start_pos + 100:])
                if next_item_match:
                    end_pos = start_pos + 100 + next_item_match.start()
                else:
                    end_pos = start_pos + 10000  # Take next 10k characters
                
                section_text = content[start_pos:min(end_pos, len(content))]
                
                # Clean up the text
                section_text = re.sub(r'<[^>]+>', '', section_text)  # Remove HTML tags
                section_text = re.sub(r'\s+', ' ', section_text).strip()  # Normalize whitespace
                
                if len(section_text) > 200:  # Only include substantial sections
                    sections[section_name] = section_text[:5000]  # Limit section length
        
        return sections
    
    async def get_earnings_call_transcripts(self, ticker: str, limit: int = 4) -> List[Dict[str, Any]]:
        """
        Get recent earnings call transcripts from 8-K filings.
        
        Note: Not all 8-K filings contain earnings calls, and transcripts
        might not always be in a structured format.
        """
        # Get recent 8-K filings
        filings = await self.get_recent_filings(ticker, form_types=['8-K'], limit=limit * 3)
        
        transcripts = []
        
        for filing in filings:
            # Check if this might be an earnings call filing
            if any(keyword in filing['primary_doc_description'].lower() 
                  for keyword in ['earnings', 'results', 'conference', 'call']):
                
                # Get the filing content
                company_info = await self.get_company_info(ticker)
                if not company_info.get('found'):
                    continue
                
                content = await self.get_filing_content(
                    filing['accession_number'],
                    filing['primary_document'],
                    company_info['cik']
                )
                
                if content and 'raw_content' in content:
                    # Look for transcript-like content
                    text = content['raw_content']
                    
                    if any(keyword in text.lower() for keyword in 
                          ['conference call', 'earnings call', 'q&a', 'operator']):
                        
                        transcript_data = {
                            'filing_date': filing['filing_date'],
                            'accession_number': filing['accession_number'],
                            'title': filing['primary_doc_description'],
                            'content_excerpt': text[:2000] + "..." if len(text) > 2000 else text,
                            'full_content_available': True,
                            'filing_url': filing['filing_url']
                        }
                        
                        transcripts.append(transcript_data)
                        
                        if len(transcripts) >= limit:
                            break
        
        return transcripts
    
    async def get_comprehensive_filings(self, ticker: str) -> Dict[str, Any]:
        """Get comprehensive SEC filing data for institutional research."""
        logger.info("Fetching SEC filings", ticker=ticker)
        
        try:
            # Get company info
            company_info = await self.get_company_info(ticker)
            if not company_info.get('found'):
                return {'error': f'Company {ticker} not found in SEC database'}
            
            # Get recent filings
            recent_filings = await self.get_recent_filings(ticker, limit=10)
            
            # Get earnings call transcripts
            earnings_calls = await self.get_earnings_call_transcripts(ticker, limit=4)
            
            # Categorize filings
            filings_by_type = {}
            for filing in recent_filings:
                form_type = filing['form']
                if form_type not in filings_by_type:
                    filings_by_type[form_type] = []
                filings_by_type[form_type].append(filing)
            
            result = {
                'company_info': company_info,
                'recent_filings': recent_filings,
                'filings_by_type': filings_by_type,
                'earnings_calls': earnings_calls,
                'filing_summary': {
                    'total_filings': len(recent_filings),
                    'form_types': list(filings_by_type.keys()),
                    'latest_10k': next((f for f in recent_filings if f['form'] == '10-K'), None),
                    'latest_10q': next((f for f in recent_filings if f['form'] == '10-Q'), None),
                    'recent_8k_count': len([f for f in recent_filings if f['form'] == '8-K'])
                },
                'retrieved_at': datetime.utcnow().isoformat(),
                'data_source': 'sec_edgar'
            }
            
            logger.info("SEC filings fetch completed", ticker=ticker,
                       total_filings=len(recent_filings),
                       earnings_calls=len(earnings_calls))
            
            return result
            
        except Exception as e:
            logger.error("Failed to get SEC filings", ticker=ticker, error=str(e))
            return {'error': str(e)}
    
    async def close(self):
        """Close HTTP session."""
        await self.session.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# Convenience functions
async def get_sec_filings(ticker: str) -> Dict[str, Any]:
    """Get comprehensive SEC filing data."""
    async with SECClient() as client:
        return await client.get_comprehensive_filings(ticker)


async def get_latest_10k_summary(ticker: str) -> Dict[str, Any]:
    """Get summary of the latest 10-K filing."""
    async with SECClient() as client:
        filings = await client.get_recent_filings(ticker, form_types=['10-K'], limit=1)
        
        if not filings:
            return {'error': 'No 10-K filing found'}
        
        latest_10k = filings[0]
        
        # Get company info for CIK
        company_info = await client.get_company_info(ticker)
        if not company_info.get('found'):
            return {'error': 'Company not found'}
        
        # Get filing content
        content = await client.get_filing_content(
            latest_10k['accession_number'],
            latest_10k['primary_document'],
            company_info['cik']
        )
        
        if content and 'sections' in content:
            return {
                'filing_info': latest_10k,
                'key_sections': content['sections'],
                'analysis_summary': {
                    'has_business_section': 'business' in content['sections'],
                    'has_risk_factors': 'risk_factors' in content['sections'],
                    'has_md_a': 'management_discussion' in content['sections'],
                    'sections_extracted': len(content['sections'])
                }
            }
        
        return {'filing_info': latest_10k, 'content_available': False}


# Test function
async def test_sec_client():
    """Test SEC client with a known ticker."""
    async with SECClient() as client:
        data = await client.get_comprehensive_filings("AAPL")
        print(f"Company: {data.get('company_info', {}).get('title')}")
        print(f"Recent filings: {data.get('filing_summary', {}).get('total_filings')}")
        print(f"Form types: {data.get('filing_summary', {}).get('form_types')}")


if __name__ == "__main__":
    asyncio.run(test_sec_client())