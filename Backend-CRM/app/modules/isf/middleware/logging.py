import time
import logging
from datetime import datetime, timezone
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Log request
        logger.info(f"[{datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%dT%H:%M:%S.%fZ')}] {request.method} {request.url}")
        
        # Log params if present
        if request.path_params:
            logger.info(f"Request params: {request.path_params}")
        
        # Process request
        response = await call_next(request)
        
        # Calculate processing time
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        
        # Log response
        logger.info(f"Response status: {response.status_code}, Process time: {process_time:.4f}s")
        
        return response
