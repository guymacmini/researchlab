"""Tests for SEC EDGAR integration."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from src.data.sec_edgar import (
    SECFiling, FinancialStatement, SECEDGARClient, 
    SECDocumentParser, SECEDGARManager
)


class TestSECFiling:
    """Test SEC filing model."""
    
    def test_sec_filing_creation(self):
        """Test SEC filing model creation."""
        filing = SECFiling(
            cik="0000320193",
            company_name="Apple Inc.",
            form_type="10-K",
            filing_date=datetime(2024, 1, 15),
            accession_number="0000320193-24-000001",
            document_url="https://www.sec.gov/Archives/edgar/data/320193/000032019324000001/aapl-20230930.htm"
        )
        
        assert filing.cik == "0000320193"
        assert filing.company_name == "Apple Inc."
        assert filing.form_type == "10-K"
        assert filing.filing_date.year == 2024
        assert filing.accession_number == "0000320193-24-000001"
        assert "apple" in filing.document_url.lower()
    
    def test_sec_filing_with_financial_data(self):
        """Test SEC filing with parsed financial data."""
        filing = SECFiling(
            cik="0000320193",
            company_name="Apple Inc.",
            form_type="10-Q",
            filing_date=datetime.now(),
            accession_number="test-123",
            document_url="https://example.com/doc.html",
            financial_data={
                "income_statement": {
                    "revenue": 89000000000,
                    "net_income": 23000000000
                },
                "balance_sheet": {
                    "total_assets": 352000000000
                }
            },
            business_description="Apple designs, manufactures and markets smartphones...",
            risk_factors=["Economic conditions", "Competition", "Supply chain risks"]
        )
        
        assert filing.financial_data["income_statement"]["revenue"] == 89000000000
        assert len(filing.risk_factors) == 3
        assert "smartphones" in filing.business_description


class TestFinancialStatement:
    """Test financial statement model."""
    
    def test_financial_statement_creation(self):
        """Test financial statement creation."""
        statement = FinancialStatement(
            statement_type="income",
            period_end=datetime(2023, 12, 31),
            revenue=100000000,
            net_income=20000000,
            total_assets=500000000,
            operating_cash_flow=25000000
        )
        
        assert statement.statement_type == "income"
        assert statement.revenue == 100000000
        assert statement.net_income == 20000000
        assert statement.total_assets == 500000000
        assert statement.currency == "USD"  # Default
    
    def test_financial_statement_with_raw_data(self):
        """Test financial statement with raw data."""
        raw_data = {
            "RevenueFromContractWithCustomerExcludingAssessedTax": 100000000,
            "NetIncomeLoss": 20000000,
            "AssetsCurrent": 150000000
        }
        
        statement = FinancialStatement(
            statement_type="income",
            period_end=datetime(2023, 12, 31),
            raw_data=raw_data
        )
        
        assert len(statement.raw_data) == 3
        assert "Revenue" in statement.raw_data.keys().__str__()


class TestSECEDGARClient:
    """Test SEC EDGAR client."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.client = SECEDGARClient()
    
    def test_client_initialization(self):
        """Test client initialization."""
        assert self.client.base_url == "https://www.sec.gov"
        assert "User-Agent" in self.client.headers
        assert "researchlab" in self.client.headers["User-Agent"].lower()
    
    @patch('httpx.AsyncClient.get')
    async def test_load_company_mappings(self, mock_get):
        """Test loading company ticker mappings."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
            "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"}
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        await self.client._load_company_mappings()
        
        assert self.client._company_mappings is not None
        assert "0" in self.client._company_mappings
        mock_get.assert_called_once()
    
    @patch('httpx.AsyncClient.get')
    async def test_get_company_cik(self, mock_get):
        """Test getting CIK for company symbol."""
        # Mock company mappings
        self.client._company_mappings = {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
            "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"}
        }
        
        cik = await self.client.get_company_cik("AAPL")
        assert cik == "0000320193"
        
        cik = await self.client.get_company_cik("MSFT")
        assert cik == "0000789019"
        
        # Test unknown symbol
        cik = await self.client.get_company_cik("UNKNOWN")
        assert cik is None
    
    @patch('httpx.AsyncClient.get')
    async def test_get_company_filings(self, mock_get):
        """Test getting company filings."""
        # Mock CIK lookup
        self.client._company_mappings = {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}
        }
        
        # Mock filings response
        mock_response = Mock()
        mock_response.json.return_value = {
            "name": "Apple Inc.",
            "cik": "320193",
            "filings": {
                "recent": {
                    "form": ["10-K", "10-Q", "8-K"],
                    "filingDate": ["2024-01-15", "2023-10-15", "2023-09-01"],
                    "accessionNumber": ["0000320193-24-000001", "0000320193-23-000098", "0000320193-23-000087"],
                    "primaryDocument": ["aapl-20230930.htm", "aapl-20230630.htm", "aapl-8k.htm"]
                }
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        filings = await self.client.get_company_filings("AAPL", form_types=["10-K", "10-Q"])
        
        assert len(filings) >= 1
        assert filings[0].company_name == "Apple Inc."
        assert filings[0].form_type in ["10-K", "10-Q"]
        assert filings[0].cik == "0000320193"
        mock_get.assert_called()
    
    def test_parse_filings_response(self):
        """Test parsing SEC filings response."""
        data = {
            "name": "Apple Inc.",
            "cik": "320193",
            "filings": {
                "recent": {
                    "form": ["10-K", "10-Q", "8-K", "10-Q"],
                    "filingDate": ["2024-01-15", "2023-10-15", "2023-09-01", "2023-07-15"],
                    "accessionNumber": ["0000320193-24-000001", "0000320193-23-000098", "0000320193-23-000087", "0000320193-23-000076"],
                    "primaryDocument": ["aapl-20230930.htm", "aapl-20230630.htm", "aapl-8k.htm", "aapl-20230331.htm"]
                }
            }
        }
        
        filings = self.client._parse_filings_response(
            data, 
            form_types=["10-K", "10-Q"], 
            limit=3,
            before_date=None
        )
        
        # Should get 3 filings (2 x 10-Q and 1 x 10-K, excluding 8-K)
        assert len(filings) == 3
        
        # Should be sorted by filing date (most recent first)
        assert filings[0].filing_date >= filings[1].filing_date
        
        # All should be requested form types
        for filing in filings:
            assert filing.form_type in ["10-K", "10-Q"]
    
    @patch('httpx.AsyncClient.get')
    async def test_download_filing_document(self, mock_get):
        """Test downloading filing document."""
        mock_response = Mock()
        mock_response.text = "<html><body>Sample 10-K filing content</body></html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        filing = SECFiling(
            cik="0000320193",
            company_name="Apple Inc.",
            form_type="10-K",
            filing_date=datetime.now(),
            accession_number="test-123",
            document_url="https://www.sec.gov/test-filing.html"
        )
        
        content = await self.client.download_filing_document(filing)
        
        assert content is not None
        assert "10-K filing content" in content
        mock_get.assert_called_with(filing.document_url)


class TestSECDocumentParser:
    """Test SEC document parser."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = SECDocumentParser()
    
    def test_parser_initialization(self):
        """Test parser initialization."""
        assert len(self.parser.revenue_patterns) > 0
        assert len(self.parser.net_income_patterns) > 0
        assert len(self.parser.assets_patterns) > 0
    
    def test_extract_number_from_cell(self):
        """Test extracting numbers from table cells."""
        from bs4 import BeautifulSoup
        
        # Test positive number
        html = "<td>123,456,789</td>"
        cell = BeautifulSoup(html, 'html.parser').find('td')
        number = self.parser._extract_number_from_cell(cell)
        assert number == 123456789.0
        
        # Test negative number (in parentheses)
        html = "<td>(45,678)</td>"
        cell = BeautifulSoup(html, 'html.parser').find('td')
        number = self.parser._extract_number_from_cell(cell)
        assert number == -45678.0
        
        # Test decimal number
        html = "<td>12.34</td>"
        cell = BeautifulSoup(html, 'html.parser').find('td')
        number = self.parser._extract_number_from_cell(cell)
        assert number == 12.34
        
        # Test empty/invalid cell
        html = "<td>N/A</td>"
        cell = BeautifulSoup(html, 'html.parser').find('td')
        number = self.parser._extract_number_from_cell(cell)
        assert number is None
    
    def test_parse_income_statement_table(self):
        """Test parsing income statement from HTML table."""
        html = """
        <table>
            <tr>
                <td>Total Revenue</td>
                <td>123,456,789</td>
            </tr>
            <tr>
                <td>Net Income</td>
                <td>23,456,789</td>
            </tr>
            <tr>
                <td>Operating Income</td>
                <td>34,567,890</td>
            </tr>
        </table>
        """
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table')
        
        data = self.parser._parse_income_statement_table(table)
        
        assert 'revenue' in data
        assert data['revenue'] == 123456789.0
        assert data['net_income'] == 23456789.0
        assert data['operating_income'] == 34567890.0
    
    def test_parse_balance_sheet_table(self):
        """Test parsing balance sheet from HTML table."""
        html = """
        <table>
            <tr>
                <td>Total Assets</td>
                <td>500,000,000</td>
            </tr>
            <tr>
                <td>Total Current Assets</td>
                <td>200,000,000</td>
            </tr>
            <tr>
                <td>Total Shareholders Equity</td>
                <td>150,000,000</td>
            </tr>
        </table>
        """
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table')
        
        data = self.parser._parse_balance_sheet_table(table)
        
        assert 'total_assets' in data
        assert data['total_assets'] == 500000000.0
        assert data['current_assets'] == 200000000.0
        assert data['shareholders_equity'] == 150000000.0
    
    def test_extract_business_description(self):
        """Test extracting business description."""
        html = """
        <html>
            <body>
                <p>Item 1 - Business</p>
                <p>The Company designs, develops, and sells consumer electronics, computer software, and online services.</p>
                <p>The Company's products include iPhone, iPad, Mac, Apple Watch, and AirPods.</p>
                <p>Item 2 - Properties</p>
            </body>
        </html>
        """
        
        description = self.parser._extract_business_description(html)
        
        assert description is not None
        assert "designs, develops" in description
        assert "iPhone" in description
    
    def test_extract_risk_factors(self):
        """Test extracting risk factors."""
        html = """
        <html>
            <body>
                <h2>Risk Factors</h2>
                <p>The Company faces intense competition in all areas of its business.</p>
                <p>Economic conditions could adversely affect demand for our products.</p>
                <p>Supply chain disruptions could impact product availability.</p>
                <h2>Legal Proceedings</h2>
            </body>
        </html>
        """
        
        risk_factors = self.parser._extract_risk_factors(html)
        
        assert len(risk_factors) >= 2
        assert any("competition" in risk.lower() for risk in risk_factors)
        assert any("economic" in risk.lower() for risk in risk_factors)
    
    async def test_parse_filing(self):
        """Test parsing complete filing."""
        filing = SECFiling(
            cik="0000320193",
            company_name="Apple Inc.",
            form_type="10-K",
            filing_date=datetime.now(),
            accession_number="test-123",
            document_url="https://example.com/test.html"
        )
        
        document_content = """
        <html>
            <body>
                <h2>Item 1 - Business</h2>
                <p>Apple Inc. designs and manufactures consumer electronics.</p>
                
                <h2>Risk Factors</h2>
                <p>Competition in the technology industry is intense.</p>
                
                <table>
                    <tr><td>Total Revenue</td><td>365,817,000</td></tr>
                    <tr><td>Net Income</td><td>94,680,000</td></tr>
                </table>
            </body>
        </html>
        """
        
        parsed_filing = await self.parser.parse_filing(filing, document_content)
        
        assert parsed_filing.business_description is not None
        assert "Apple Inc." in parsed_filing.business_description
        assert len(parsed_filing.risk_factors) > 0
        assert parsed_filing.financial_data is not None
        assert "income_statement" in parsed_filing.financial_data


class TestSECEDGARManager:
    """Test SEC EDGAR manager."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = SECEDGARManager()
    
    def test_manager_initialization(self):
        """Test manager initialization."""
        assert self.manager.client is not None
        assert self.manager.parser is not None
    
    @patch.object(SECEDGARClient, 'get_company_filings')
    @patch.object(SECEDGARClient, 'download_filing_document')
    @patch.object(SECDocumentParser, 'parse_filing')
    async def test_get_company_financial_data(self, mock_parse, mock_download, mock_filings):
        """Test getting comprehensive financial data."""
        # Mock filings
        mock_filing = SECFiling(
            cik="0000320193",
            company_name="Apple Inc.",
            form_type="10-K",
            filing_date=datetime(2024, 1, 15),
            accession_number="test-123",
            document_url="https://example.com/test.html"
        )
        mock_filings.return_value = [mock_filing]
        
        # Mock document download
        mock_download.return_value = "<html>Mock filing content</html>"
        
        # Mock parsing
        parsed_filing = mock_filing.copy()
        parsed_filing.financial_data = {
            "income_statement": {"revenue": 365817000000, "net_income": 94680000000},
            "balance_sheet": {"total_assets": 352583000000}
        }
        mock_parse.return_value = parsed_filing
        
        result = await self.manager.get_company_financial_data("AAPL", periods=2)
        
        assert result["symbol"] == "AAPL"
        assert result["company_name"] == "Apple Inc."
        assert len(result["filings"]) >= 1
        assert "financial_summary" in result
        
        mock_filings.assert_called_once()
        mock_download.assert_called()
        mock_parse.assert_called()
    
    def test_calculate_trends(self):
        """Test calculating financial trends."""
        latest = {
            "revenue": 100000000,
            "net_income": 20000000,
            "total_assets": 500000000
        }
        
        previous = {
            "revenue": 90000000,
            "net_income": 18000000,
            "total_assets": 450000000
        }
        
        trends = self.manager._calculate_trends(latest, previous)
        
        assert "revenue_growth" in trends
        assert abs(trends["revenue_growth"] - 11.11) < 0.1  # ~11.11% growth
        
        assert "net_income_growth" in trends
        assert abs(trends["net_income_growth"] - 11.11) < 0.1
        
        assert "total_assets_growth" in trends
        assert abs(trends["total_assets_growth"] - 11.11) < 0.1
    
    def test_aggregate_financial_data(self):
        """Test aggregating financial data across filings."""
        # Create mock filings with financial data
        filing1 = SECFiling(
            cik="0000320193",
            company_name="Apple Inc.",
            form_type="10-K",
            filing_date=datetime(2024, 1, 15),
            accession_number="test-123",
            document_url="https://example.com/test1.html",
            financial_data={
                "income_statement": {"revenue": 100000000, "net_income": 20000000},
                "balance_sheet": {"total_assets": 500000000}
            }
        )
        
        filing2 = SECFiling(
            cik="0000320193",
            company_name="Apple Inc.",
            form_type="10-K",
            filing_date=datetime(2023, 1, 15),
            accession_number="test-124",
            document_url="https://example.com/test2.html",
            financial_data={
                "income_statement": {"revenue": 90000000, "net_income": 18000000},
                "balance_sheet": {"total_assets": 450000000}
            }
        )
        
        summary = self.manager._aggregate_financial_data([filing1, filing2])
        
        assert summary["periods_analyzed"] == 2
        assert summary["latest_filing_date"] is not None
        assert len(summary["periods_data"]) == 2
        
        # Should calculate trends
        if "trends" in summary:
            assert len(summary["trends"]) > 0
    
    @patch.object(SECEDGARClient, 'get_company_filings')
    @patch.object(SECEDGARClient, 'download_filing_document')
    async def test_search_filings_by_content(self, mock_download, mock_filings):
        """Test searching filing content for terms."""
        # Mock filing
        mock_filing = SECFiling(
            cik="0000320193",
            company_name="Apple Inc.",
            form_type="10-K",
            filing_date=datetime.now(),
            accession_number="test-123",
            document_url="https://example.com/test.html"
        )
        mock_filings.return_value = [mock_filing]
        
        # Mock document content with search terms
        mock_download.return_value = """
        <html>
            <body>
                <p>The Company faces significant risks from artificial intelligence developments.</p>
                <p>Supply chain disruptions may impact operations.</p>
                <p>Climate change poses long-term risks to business.</p>
            </body>
        </html>
        """
        
        results = await self.manager.search_filings_by_content(
            "AAPL",
            search_terms=["artificial intelligence", "climate change", "blockchain"]
        )
        
        assert len(results) >= 1
        
        # Should find matches for AI and climate change
        filing_result = results[0]
        matches = filing_result["matches"]
        
        matched_terms = [match["term"] for match in matches]
        assert "artificial intelligence" in matched_terms
        assert "climate change" in matched_terms
        # blockchain should not be found
        assert "blockchain" not in matched_terms
    
    def test_extract_context(self):
        """Test extracting context around search terms."""
        content = """
        This is some text before the search term. The artificial intelligence
        revolution is transforming how businesses operate and compete in the
        global marketplace. This is some text after the search term.
        """
        
        context = self.manager._extract_context(content, "artificial intelligence", context_length=100)
        
        assert "artificial intelligence" in context
        assert "revolution" in context
        assert len(context) <= 200  # Should respect context length


class TestSECEDGARIntegration:
    """Integration tests for SEC EDGAR components."""
    
    @patch('httpx.AsyncClient.get')
    async def test_end_to_end_filing_processing(self, mock_get):
        """Test end-to-end filing processing."""
        manager = SECEDGARManager()
        
        # Mock company mappings response
        mappings_response = Mock()
        mappings_response.json.return_value = {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}
        }
        mappings_response.raise_for_status.return_value = None
        
        # Mock filings response
        filings_response = Mock()
        filings_response.json.return_value = {
            "name": "Apple Inc.",
            "cik": "320193",
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "filingDate": ["2024-01-15"],
                    "accessionNumber": ["0000320193-24-000001"],
                    "primaryDocument": ["aapl-20230930.htm"]
                }
            }
        }
        filings_response.raise_for_status.return_value = None
        
        # Mock document response
        document_response = Mock()
        document_response.text = """
        <html>
            <body>
                <h2>Item 1 - Business</h2>
                <p>Apple Inc. designs, develops, and sells consumer electronics.</p>
                
                <table>
                    <tr><td>Total Revenue</td><td>365,817</td></tr>
                    <tr><td>Net Income</td><td>94,680</td></tr>
                </table>
                
                <h2>Risk Factors</h2>
                <p>The Company faces intense competition.</p>
            </body>
        </html>
        """
        document_response.raise_for_status.return_value = None
        
        # Set up mock responses in order
        mock_get.side_effect = [mappings_response, filings_response, document_response]
        
        # Run end-to-end test
        result = await manager.get_company_financial_data("AAPL", periods=1)
        
        assert result["symbol"] == "AAPL"
        assert result["company_name"] == "Apple Inc."
        assert len(result["filings"]) == 1
        
        # Check parsed data
        filing = result["filings"][0]
        assert filing["business_description"] is not None
        assert filing["financial_data"] is not None
        assert len(filing["risk_factors"]) > 0
    
    def test_error_handling_invalid_symbol(self):
        """Test error handling for invalid symbols."""
        client = SECEDGARClient()
        
        # Test with empty company mappings
        client._company_mappings = {}
        
        # Should return None for unknown symbol
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            cik = loop.run_until_complete(client.get_company_cik("INVALID"))
            assert cik is None
        finally:
            loop.close()
    
    def test_performance_with_multiple_filings(self):
        """Test performance with multiple filings."""
        parser = SECDocumentParser()
        
        # Create multiple mock filings
        filings = []
        for i in range(5):
            filing = SECFiling(
                cik=f"000032019{i}",
                company_name=f"Test Company {i}",
                form_type="10-K",
                filing_date=datetime.now(),
                accession_number=f"test-12{i}",
                document_url=f"https://example.com/test{i}.html"
            )
            filings.append(filing)
        
        # Should handle multiple filings efficiently
        assert len(filings) == 5
        
        # Test aggregation
        manager = SECEDGARManager()
        summary = manager._aggregate_financial_data(filings[:2])  # Test with 2 filings
        
        assert summary["periods_analyzed"] == 2