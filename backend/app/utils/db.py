from pymongo import MongoClient
from app.config import Config
import re

class MongoDB:
    _client = None
    
    @classmethod
    def get_client(cls):
        if cls._client is None:
            cls._client = MongoClient(Config.MONGODB_URI)
        return cls._client
    
    @classmethod
    def get_database(cls, db_name):
        """Get a specific database"""
        client = cls.get_client()
        return client[db_name]
    
    @classmethod
    def normalize_name(cls, name):
        """Normalize name for use as database/collection name"""
        # Convert to lowercase
        normalized = name.lower()
        # Replace spaces and special chars with underscores
        normalized = re.sub(r'[^a-z0-9_]', '_', normalized)
        # Remove consecutive underscores
        normalized = re.sub(r'_+', '_', normalized)
        # Remove leading/trailing underscores
        normalized = normalized.strip('_')
        return normalized
    
    @classmethod
    def get_championship_db_name(cls, championship_name):
        """Get database name for a championship"""
        normalized = cls.normalize_name(championship_name)
        return f"campeonato_{normalized}"
    
    @classmethod
    def championship_exists(cls, championship_name):
        """
        Check if a championship database exists
        
        Args:
            championship_name: Name of the championship
            
        Returns:
            bool: True if championship exists, False otherwise
        """
        db_name = cls.get_championship_db_name(championship_name)
        client = cls.get_client()
        # Check if database exists and has metadata collection
        if db_name in client.list_database_names():
            db = client[db_name]
            return 'metadata' in db.list_collection_names()
        return False
    
    @classmethod
    def list_championships(cls):
        """
        List all championship databases
        
        Returns:
            list: List of championship database names
        """
        client = cls.get_client()
        championships = []
        for db_name in client.list_database_names():
            if db_name.startswith('campeonato_'):
                db = client[db_name]
                # Verify it has metadata collection
                if 'metadata' in db.list_collection_names():
                    championships.append(db_name)
        return championships
    
    @classmethod
    def close(cls):
        """Close MongoDB connection"""
        if cls._client:
            cls._client.close()
            cls._client = None
