import os
import uuid
import hashlib
import aiofiles
from fastapi import UploadFile
from typing import Optional

from ..core.config import settings


class FileHandler:
    def __init__(self):
        self.upload_dir = settings.UPLOAD_DIR
        self.temp_dir = settings.TEMP_DIR
        
        # Ensure directories exist
        os.makedirs(self.upload_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
    
    async def save_upload_file(self, file: UploadFile) -> str:
        """Save uploaded file and return file URL"""
        try:
            # Generate unique filename
            file_extension = os.path.splitext(file.filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            file_path = os.path.join(self.upload_dir, unique_filename)
            
            # Save file
            async with aiofiles.open(file_path, 'wb') as f:
                content = await file.read()
                await f.write(content)
            
            # Generate file URL (in production, this would be a proper URL)
            file_url = f"/uploads/{unique_filename}"
            
            return file_url
            
        except Exception as e:
            raise Exception(f"Failed to save file: {str(e)}")
    
    async def save_temp_file(self, file: UploadFile) -> str:
        """Save temporary file and return file path"""
        try:
            # Generate unique filename
            file_extension = os.path.splitext(file.filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            file_path = os.path.join(self.temp_dir, unique_filename)
            
            # Save file
            async with aiofiles.open(file_path, 'wb') as f:
                content = await file.read()
                await f.write(content)
            
            return file_path
            
        except Exception as e:
            raise Exception(f"Failed to save temp file: {str(e)}")
    
    def delete_temp_file(self, file_path: str) -> bool:
        """Delete temporary file"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            return True
        except Exception:
            return False
    
    def calculate_file_hash(self, content: bytes) -> str:
        """Calculate SHA-256 hash of file content"""
        return hashlib.sha256(content).hexdigest()
    
    def get_file_size(self, file_path: str) -> int:
        """Get file size in bytes"""
        try:
            return os.path.getsize(file_path)
        except OSError:
            return 0
