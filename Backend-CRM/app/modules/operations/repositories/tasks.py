"""Operations domain repositories (MongoDB-backed).

Moved from app/repositories/mongo_repository.py during folder cleanup.
Holds TaskRepository.
"""
"""
MongoDB repository base class and implementations for conversation/message data.
This module contains repositories for MongoDB-backed entities.
"""
from typing import Optional, List, Dict, Any
from uuid import UUID
import uuid
import re
from datetime import datetime, timezone
from bson import ObjectId
from pymongo import DESCENDING
from app.db.mongo import get_mongo_db
from app.models import MessageDirection, MessageChannel, MessageStatus
import logging

logger = logging.getLogger(__name__)


def uuid_to_str(uuid_val: UUID) -> str:
    """Convert UUID to string for MongoDB storage."""
    return str(uuid_val) if uuid_val else None


def str_to_uuid(str_val: str) -> Optional[UUID]:
    """Convert string to UUID."""
    try:
        return UUID(str_val) if str_val else None
    except (ValueError, AttributeError):
        return None




class TaskRepository:
    """Repository for Task documents in MongoDB."""
    
    COLLECTION_NAME = "tasks"
    
    @staticmethod
    async def create(task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new task."""
        db = await get_mongo_db()
        collection = db[TaskRepository.COLLECTION_NAME]
        
        # Ensure id is string
        if 'id' in task_data and isinstance(task_data['id'], UUID):
            task_data['id'] = str(task_data['id'])
        elif 'id' not in task_data:
            task_data['id'] = str(uuid.uuid4())
        
        # Set timestamps if not present
        now = datetime.now(timezone.utc)
        if 'createdAt' not in task_data:
            task_data['createdAt'] = now.isoformat()
        if 'updatedAt' not in task_data:
            task_data['updatedAt'] = now.isoformat()
        
        result = await collection.insert_one(task_data)
        logger.info(f"[MONGO] Created task: {task_data.get('id', result.inserted_id)}")
        
        created = await collection.find_one({"_id": result.inserted_id})
        return TaskRepository._normalize_doc(created)
    
    @staticmethod
    async def get_by_id(task_id: str) -> Optional[Dict[str, Any]]:
        """Get task by ID."""
        db = await get_mongo_db()
        collection = db[TaskRepository.COLLECTION_NAME]
        
        doc = await collection.find_one({"id": task_id})
        return TaskRepository._normalize_doc(doc) if doc else None
    
    @staticmethod
    async def list(
        limit: int = 50,
        offset: int = 0,
        **filters
    ) -> List[Dict[str, Any]]:
        """List tasks with optional filters."""
        db = await get_mongo_db()
        collection = db[TaskRepository.COLLECTION_NAME]
        
        query = {}
        # Handle nested filters (e.g., links.conversationId)
        for key, value in filters.items():
            if value is not None:
                query[key] = value
        
        cursor = collection.find(query).sort("createdAt", DESCENDING).skip(offset).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [TaskRepository._normalize_doc(doc) for doc in docs]
    
    @staticmethod
    async def update(task_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update a task."""
        db = await get_mongo_db()
        collection = db[TaskRepository.COLLECTION_NAME]
        
        # Ensure updatedAt is set
        updates['updatedAt'] = datetime.now(timezone.utc).isoformat()
        
        result = await collection.update_one(
            {"id": task_id},
            {"$set": updates}
        )
        
        if result.matched_count == 0:
            raise ValueError(f"Task {task_id} not found")
        
        updated = await collection.find_one({"id": task_id})
        return TaskRepository._normalize_doc(updated)
    
    @staticmethod
    async def delete(task_id: str) -> bool:
        """Delete a task."""
        db = await get_mongo_db()
        collection = db[TaskRepository.COLLECTION_NAME]
        
        result = await collection.delete_one({"id": task_id})
        logger.info(f"[MONGO] Deleted task: {task_id} (matched: {result.deleted_count})")
        return result.deleted_count > 0
    
    @staticmethod
    def _normalize_doc(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize MongoDB document."""
        if not doc:
            return None
        normalized = dict(doc)
        normalized.pop('_id', None)
        return normalized



