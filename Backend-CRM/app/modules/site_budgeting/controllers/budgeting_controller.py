"""Re-export router for consumers that expect a controller module."""
from app.modules.site_budgeting.routes.budgeting import router

__all__ = ["router"]
