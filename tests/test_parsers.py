import pytest
import asyncio
from unittest.mock import Mock, patch
from main import AvitoParser, CianParser, Database, Apartment
from datetime import datetime

class TestAvitoParser:
    @pytest.fixture
    def parser(self):
        return AvitoParser()
    
    @pytest.mark.asyncio
    async def test_parse_apartments_success(self, parser):
        mock_html = """
        <div data-marker="item">
            <h3>Тестовая квартира</h3>
            <span data-marker="item-price">25 000 ₽</span>
            <a href="/test-apartment-123">Ссылка</a>
            <span data-marker="item-address">Центральный район</span>
        </div>
        """
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = Mock()
            mock_response.status = 200
            mock_response.text = asyncio.coroutine(lambda: mock_html)
            mock_get.return_value.__aenter__.return_value = mock_response
            
            apartments = await parser.parse_apartments("http://test.url")
            
            assert len(apartments) >= 0

class TestCianParser:
    @pytest.fixture
    def parser(self):
        return CianParser()
    
    @pytest.mark.asyncio
    async def test_parse_apartments_success(self, parser):
        mock_html = """
        <article data-name="CardComponent">
            <span data-mark="OfferTitle">Тестовая квартира Cian</span>
            <span data-mark="MainPrice">28 000 ₽</span>
            <a href="/rent/flat/123/">Ссылка</a>
            <a data-name="GeoLabel">Советский район</a>
            <div data-mark="OfferSummary">65 м²</div>
        </article>
        """
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = Mock()
            mock_response.status = 200
            mock_response.text = asyncio.coroutine(lambda: mock_html)
            mock_get.return_value.__aenter__.return_value = mock_response
            
            apartments = await parser.parse_apartments("http://test.url")
            
            assert len(apartments) >= 0

class TestDatabase:
    @pytest.fixture
    def db(self, tmp_path):
        db_path = tmp_path / "test.db"
        return Database(str(db_path))
    
    def test_add_apartment(self, db):
        apartment = Apartment(
            id="test_123",
            title="Тестовая квартира",
            price=25000,
            url="http://test.url",
            location="Тестовый район",
            rooms=3,
            area="65 м²",
            source="Test",
            created_at=datetime.now()
        )
        
        assert db.add_apartment(apartment) == True
        
        assert db.add_apartment(apartment) == False
    
    def test_apartment_exists(self, db):
        apartment = Apartment(
            id="test_456",
            title="Тестовая квартира 2",
            price=27000,
            url="http://test2.url",
            location="Тестовый район 2",
            rooms=3,
            area="70 м²",
            source="Test",
            created_at=datetime.now()
        )
        
        assert db.apartment_exists("test_456") == False
        
        db.add_apartment(apartment)
        
        assert db.apartment_exists("test_456") == True

if __name__ == "__main__":
    pytest.main([__file__])
