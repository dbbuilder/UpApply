"""
Utility functions for Upwork Automation Tool

Provides common helper functions for file handling, data validation,
and other shared functionality.
"""

import json
import os
import re
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timezone
import aiofiles

logger = logging.getLogger(__name__)

def save_json(data: Any, filepath: Union[str, Path]) -> bool:
    """
    Save data to JSON file with error handling
    
    Args:
        data: Data to save
        filepath: Path to save the file
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        
        logger.debug(f"Successfully saved data to {filepath}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving JSON to {filepath}: {e}")
        return False

def load_json(filepath: Union[str, Path], default: Any = None) -> Any:
    """
    Load data from JSON file with validation
    
    Args:
        filepath: Path to the JSON file
        default: Default value if file doesn't exist or is invalid
    
    Returns:
        Loaded data or default value
    """
    try:
        filepath = Path(filepath)
        if not filepath.exists():
            logger.debug(f"JSON file {filepath} does not exist, returning default")
            return default or {}
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logger.debug(f"Successfully loaded data from {filepath}")
        return data
        
    except Exception as e:
        logger.error(f"Error loading JSON from {filepath}: {e}")
        return default or {}

async def save_json_async(data: Any, filepath: Union[str, Path]) -> bool:
    """
    Asynchronously save data to JSON file
    
    Args:
        data: Data to save
        filepath: Path to save the file
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        json_data = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        
        async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
            await f.write(json_data)
        
        logger.debug(f"Successfully saved data to {filepath} (async)")
        return True
        
    except Exception as e:
        logger.error(f"Error saving JSON to {filepath} (async): {e}")
        return False

async def load_json_async(filepath: Union[str, Path], default: Any = None) -> Any:
    """
    Asynchronously load data from JSON file
    
    Args:
        filepath: Path to the JSON file
        default: Default value if file doesn't exist or is invalid
    
    Returns:
        Loaded data or default value
    """
    try:
        filepath = Path(filepath)
        if not filepath.exists():
            logger.debug(f"JSON file {filepath} does not exist, returning default")
            return default or {}
        
        async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
            content = await f.read()
            data = json.loads(content)
        
        logger.debug(f"Successfully loaded data from {filepath} (async)")
        return data
        
    except Exception as e:
        logger.error(f"Error loading JSON from {filepath} (async): {e}")
        return default or {}

def validate_job_data(job: Dict[str, Any]) -> bool:
    """
    Validate job data structure
    
    Args:
        job: Job data dictionary
    
    Returns:
        bool: True if valid, False otherwise
    """
    required_fields = ['id', 'title', 'upwork_url']
    
    try:
        for field in required_fields:
            if field not in job or not job[field]:
                logger.warning(f"Job missing required field: {field}")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error validating job data: {e}")
        return False

def parse_job_numbers(input_str: str) -> List[int]:
    """
    Parse job numbers from user input (supports comma-separated and ranges)
    
    Args:
        input_str: User input string (e.g., "1,3,5" or "1-3,5")
    
    Returns:
        List of job numbers
    """
    job_numbers = []
    
    try:
        # Remove spaces and split by comma
        parts = [part.strip() for part in input_str.split(',')]
        
        for part in parts:
            if '-' in part:
                # Handle range (e.g., "1-3")
                start, end = part.split('-', 1)
                start, end = int(start.strip()), int(end.strip())
                job_numbers.extend(range(start, end + 1))
            else:
                # Handle single number
                job_numbers.append(int(part))
        
        # Remove duplicates and sort
        job_numbers = sorted(list(set(job_numbers)))
        
    except ValueError as e:
        logger.error(f"Error parsing job numbers '{input_str}': {e}")
        raise ValueError(f"Invalid job number format: {input_str}")
    
    return job_numbers

def format_currency(amount: str) -> str:
    """
    Format currency string for display
    
    Args:
        amount: Currency amount string
    
    Returns:
        Formatted currency string
    """
    if not amount:
        return "Not specified"
    
    # Clean up common currency formats
    amount = amount.strip()
    if amount.lower() in ['not specified', 'n/a', 'tbd']:
        return "Not specified"
    
    return amount

def format_datetime(dt: Union[str, datetime, None]) -> str:
    """
    Format datetime for display
    
    Args:
        dt: Datetime string or object
    
    Returns:
        Formatted datetime string
    """
    if not dt:
        return "Unknown"
    
    try:
        if isinstance(dt, str):
            # Try to parse ISO format
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        
        if isinstance(dt, datetime):
            # Format as relative time if recent
            now = datetime.now(timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            
            diff = now - dt
            days = diff.days
            
            if days == 0:
                return "Today"
            elif days == 1:
                return "Yesterday"
            elif days < 7:
                return f"{days} days ago"
            elif days < 30:
                weeks = days // 7
                return f"{weeks} week{'s' if weeks > 1 else ''} ago"
            else:
                return dt.strftime("%Y-%m-%d")
        
    except Exception as e:
        logger.warning(f"Error formatting datetime {dt}: {e}")
    
    return str(dt)

def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """
    Sanitize filename for safe file system storage
    
    Args:
        filename: Original filename
        max_length: Maximum length for filename
    
    Returns:
        Sanitized filename
    """
    # Remove or replace invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = re.sub(r'\s+', '_', filename)  # Replace spaces with underscores
    filename = re.sub(r'_+', '_', filename)   # Replace multiple underscores with single
    filename = filename.strip('_.')           # Remove leading/trailing underscores and dots
    
    # Truncate if too long
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        filename = name[:max_length - len(ext)] + ext
    
    return filename or "untitled"

def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to maximum length with optional suffix
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated
    
    Returns:
        Truncated text
    """
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix

def extract_upwork_job_id(url: str) -> Optional[str]:
    """
    Extract job ID from Upwork URL
    
    Args:
        url: Upwork job URL
    
    Returns:
        Job ID if found, None otherwise
    """
    try:
        # Pattern to match Upwork job URLs
        pattern = r'upwork\.com/jobs/[^/]*~([a-f0-9]+)'
        match = re.search(pattern, url)
        
        if match:
            return match.group(1)
        
        logger.warning(f"Could not extract job ID from URL: {url}")
        return None
        
    except Exception as e:
        logger.error(f"Error extracting job ID from URL {url}: {e}")
        return None

async def retry_async(func, max_retries: int = 3, delay: float = 1.0, 
                     backoff: float = 2.0, exceptions: tuple = (Exception,)):
    """
    Retry an async function with exponential backoff
    
    Args:
        func: Async function to retry
        max_retries: Maximum number of retries
        delay: Initial delay between retries
        backoff: Backoff multiplier
        exceptions: Exceptions to catch and retry
    
    Returns:
        Function result
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except exceptions as e:
            last_exception = e
            
            if attempt == max_retries:
                logger.error(f"Function failed after {max_retries} retries: {e}")
                break
            
            sleep_time = delay * (backoff ** attempt)
            logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {sleep_time:.1f}s...")
            await asyncio.sleep(sleep_time)
    
    raise last_exception

def is_valid_email(email: str) -> bool:
    """
    Validate email address format
    
    Args:
        email: Email address to validate
    
    Returns:
        bool: True if valid, False otherwise
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def ensure_directories(*paths: Union[str, Path]) -> None:
    """
    Ensure directories exist, create if they don't
    
    Args:
        *paths: Directory paths to ensure exist
    """
    for path in paths:
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Error creating directory {path}: {e}")
