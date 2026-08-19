"""
Google Custom Search API service for retrieving research paper summaries.
"""
import httpx
import asyncio
from typing import Optional, List
from app.config import settings
from app.schemas import ResearchPaperSummary


class GoogleSearchService:
    """Service for Google Custom Search API integration."""
    
    def __init__(self):
        self.api_key = settings.google_search_api_key
        self.engine_id = settings.google_search_engine_id
        self.base_url = "https://www.googleapis.com/customsearch/v1"
        self._available = bool(self.api_key and self.engine_id)
    
    def is_available(self) -> bool:
        """Check if Google Search API is configured."""
        return self._available
    
    async def search_research_papers(
        self, 
        query: str, 
        num_results: int = 10
    ) -> List[ResearchPaperSummary]:
        """
        Search for research papers using Google Custom Search API.
        
        Args:
            query: Search query string
            num_results: Number of results to return (max 10 per request)
        
        Returns:
            List of ResearchPaperSummary objects
        """
        if not self.is_available():
            return []
        
        if not query or not query.strip():
            return []
        
        try:
            # Google Custom Search API allows max 10 results per request
            num_results = min(num_results, 10)
            
            params = {
                'key': self.api_key,
                'cx': self.engine_id,
                'q': query,
                'num': num_results
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()
            
            papers = []
            if 'items' in data:
                for item in data['items']:
                    paper = ResearchPaperSummary(
                        title=item.get('title', ''),
                        link=item.get('link', ''),
                        snippet=item.get('snippet', ''),
                        source=item.get('displayLink', '')
                    )
                    papers.append(paper)
            
            return papers
            
        except Exception as e:
            print(f"Error searching Google: {e}")
            import traceback
            traceback.print_exc()
            return []


# Global service instance
google_search_service = GoogleSearchService()

