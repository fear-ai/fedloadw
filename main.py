# main.py

from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from bs4 import BeautifulSoup
import requests
from config_log import setup_logging
from config_manager import ConfigManager
from fed_entity_recognizer import FedEntityRecognizer


# Setup logging
logger = setup_logging()

# Initialize FastAPI app
app = FastAPI(title="FedLoad API")

# Initialize configuration
config_manager = ConfigManager("config.json")
config = config_manager.config

# Initialize entity recognizer if enabled
entity_recognizer = None
if config.get("entity_recognition", {}).get("enabled", False):
    try:
        entity_recognizer = FedEntityRecognizer()
        logger.info("Entity recognition enabled")
    except Exception as e:
        logger.error("Failed to initialize entity recognizer: %s", str(e))


class URLRequest(BaseModel):
    """Model for URL processing requests."""
    url: str
    extract_entities: bool = False


class ContentResponse(BaseModel):
    """Model for content processing responses."""
    content: str
    entities: Optional[List[Dict[str, Any]]] = None
    timestamp: str


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.post("/process", response_model=ContentResponse)
async def process_url(request: URLRequest):
    """Process a URL and extract content."""
    try:
        # Validate URL
        if not request.url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="Invalid URL format")

        # Fetch content
        response = requests.get(request.url, timeout=30)
        response.raise_for_status()

        # Parse content
        soup = BeautifulSoup(response.text, "html.parser")
        content = soup.get_text(strip=True)

        # Extract entities if requested and enabled
        entities = None
        if request.extract_entities and entity_recognizer:
            entities = entity_recognizer.process_text(content)

        return ContentResponse(
            content=content,
            entities=entities,
            timestamp=datetime.now().isoformat()
        )
    except HTTPException as e:
        # Re-raise HTTPExceptions so FastAPI handles them properly
        raise e
    except requests.RequestException as e:
        logger.error("Error fetching URL %s: %s", request.url, str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch URL")
    except Exception as e:
        logger.error("Error processing URL %s: %s", request.url, str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
