# utils/caching.py
"""
Caching utilities for the Lobbying Disclosure App.
Provides a simple caching system to improve performance and reduce API calls.
"""

import os
import json
import time
import hashlib
import logging
from datetime import datetime
from functools import wraps
from pathlib import Path

logger = logging.getLogger('caching')

class Cache:
    """Simple file-based cache implementation"""
    
    def __init__(self, cache_dir='cache', max_age_seconds=3600, max_size_mb=50):
        """
        Initialize the cache.
        
        Args:
            cache_dir: Directory to store cache files
            max_age_seconds: Maximum age of cached items in seconds (default: 1 hour)
            max_size_mb: Maximum size of cache directory in MB (default: 50MB)
        """
        self.cache_dir = Path(cache_dir)
        self.max_age_seconds = max_age_seconds
        self.max_size_mb = max_size_mb
        
        # Create cache directory if it doesn't exist
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Clean up old cache files on startup
        self.cleanup()
    
    def get(self, key):
        """Get an item from the cache"""
        # Create a cache key that can be used as a filename
        file_key = self._hash_key(key)
        cache_file = self.cache_dir / f"{file_key}.json"
        
        # Check if the cache file exists
        if not cache_file.exists():
            return None
        
        try:
            # Read and parse the cache file
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Check if the cache has expired
            if cache_data['expires'] < time.time():
                logger.debug(f"Cache expired for key: {file_key}")
                os.remove(cache_file)
                return None
            
            logger.debug(f"Cache hit for key: {file_key}")
            return cache_data['data']
        except (json.JSONDecodeError, KeyError) as e:
            # Invalid cache file - remove it
            logger.warning(f"Invalid cache file for key: {file_key}. Error: {str(e)}")
            os.remove(cache_file)
            return None
        except Exception as e:
            logger.error(f"Error reading cache file: {str(e)}")
            return None
    
    def set(self, key, data, expires_in=None):
        """Set an item in the cache"""
        # Use default expiration if not specified
        if expires_in is None:
            expires_in = self.max_age_seconds
        
        # Create a cache key that can be used as a filename
        file_key = self._hash_key(key)
        cache_file = self.cache_dir / f"{file_key}.json"
        
        try:
            # Create cache data structure
            cache_data = {
                'data': data,
                'created': time.time(),
                'expires': time.time() + expires_in,
                'key': key
            }
            
            # Write to cache file
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f)
            
            logger.debug(f"Cache set for key: {file_key}")
            return True
        except Exception as e:
            logger.error(f"Error writing to cache file: {str(e)}")
            return False
    
    def delete(self, key):
        """Delete an item from the cache"""
        file_key = self._hash_key(key)
        cache_file = self.cache_dir / f"{file_key}.json"
        
        if cache_file.exists():
            try:
                os.remove(cache_file)
                logger.debug(f"Cache deleted for key: {file_key}")
                return True
            except Exception as e:
                logger.error(f"Error deleting cache file: {str(e)}")
                return False
        return False
    
    def cleanup(self):
        """Clean up expired and excess cache files"""
        try:
            # Get all cache files
            cache_files = list(self.cache_dir.glob("*.json"))
            
            # Remove expired files
            now = time.time()
            expired_count = 0
            
            for cache_file in cache_files:
                try:
                    with open(cache_file, 'r') as f:
                        cache_data = json.load(f)
                    
                    if cache_data.get('expires', 0) < now:
                        os.remove(cache_file)
                        expired_count += 1
                except:
                    # If we can't read the file, consider it invalid and remove it
                    os.remove(cache_file)
                    expired_count += 1
            
            # Check cache size
            total_size_mb = sum(f.stat().st_size for f in self.cache_dir.glob("*.json")) / (1024 * 1024)
            
            if total_size_mb > self.max_size_mb:
                # If cache is too large, remove oldest files first
                cache_files = list(self.cache_dir.glob("*.json"))
                cache_files.sort(key=lambda f: f.stat().st_mtime)
                
                # Remove files until we're under the size limit
                files_removed = 0
                while total_size_mb > self.max_size_mb and cache_files:
                    file_to_remove = cache_files.pop(0)  # Get oldest file
                    size_mb = file_to_remove.stat().st_size / (1024 * 1024)
                    os.remove(file_to_remove)
                    total_size_mb -= size_mb
                    files_removed += 1
                
                logger.info(f"Removed {files_removed} cache files due to size limit")
            
            logger.info(f"Cache cleanup complete. Removed {expired_count} expired files. Current size: {total_size_mb:.2f}MB")
        except Exception as e:
            logger.error(f"Error during cache cleanup: {str(e)}")
    
    def clear(self):
        """Clear all cache files"""
        try:
            cache_files = list(self.cache_dir.glob("*.json"))
            for cache_file in cache_files:
                os.remove(cache_file)
            logger.info(f"Cache cleared. Removed {len(cache_files)} files.")
            return True
        except Exception as e:
            logger.error(f"Error clearing cache: {str(e)}")
            return False
    
    def _hash_key(self, key):
        """Create a file-safe hash from a cache key"""
        if isinstance(key, (dict, list, tuple)):
            key = json.dumps(key, sort_keys=True)
        
        return hashlib.md5(str(key).encode('utf-8')).hexdigest()

# Create a function decorator for caching
def cached(cache_instance, expires_in=None):
    """
    Decorator to cache function results.
    
    Args:
        cache_instance: Cache instance to use
        expires_in: Custom expiration time in seconds
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create a cache key from function name and arguments
            cache_key = {
                'func': func.__name__,
                'args': args,
                'kwargs': kwargs
            }
            
            # Try to get cached result
            cached_result = cache_instance.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # If not in cache, call the function
            result = func(*args, **kwargs)
            
            # Cache the result
            cache_instance.set(cache_key, result, expires_in)
            
            return result
        return wrapper
    return decorator

# Create a global cache instance
app_cache = Cache()

# Example usage:
# @cached(app_cache, expires_in=1800)  # Cache for 30 minutes
# def expensive_function(arg1, arg2):
#     # ...
#     return result