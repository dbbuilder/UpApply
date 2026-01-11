"""
Configuration management for Upwork Automation Tool

Handles loading configuration from JSON files and environment variables,
with validation and default values.
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Configuration manager for the application"""
    
    def __init__(self, config_file: str = "config.json"):
        """Initialize configuration from file and environment variables"""
        self.config_file = config_file
        self._config: Dict[str, Any] = {}
        self._load_config()
        
    def _load_config(self) -> None:
        """Load configuration from JSON file"""
        try:
            config_path = Path(self.config_file)
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
            else:
                # Use default configuration if file doesn't exist
                self._config = self._get_default_config()
                self._save_default_config()
        except Exception as e:
            logging.error(f"Error loading configuration: {e}")
            self._config = self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values"""
        return {
            "openai": {
                "model": "gpt-3.5-turbo",
                "max_tokens": 1000,
                "temperature": 0.7
            },
            "browser": {
                "headless": False,
                "timeout": 30000,
                "browser_type": "chromium",
                "delay_between_actions": 2000,
                "screenshot_on_error": True
            },
            "upwork": {
                "base_url": "https://www.upwork.com",
                "saved_jobs_url": "/nx/search/jobs/saved",
                "login_url": "/ab/account-security/login"
            },
            "storage": {
                "jobs_file": "data/jobs.json",
                "applications_file": "data/applications.json",
                "cover_letters_dir": "data/cover_letters"
            },
            "cover_letter": {
                "template": "Write a professional cover letter for this Upwork job posting:\n\n{job_description}",
                "include_skills": True,
                "max_length": 500
            },
            "logging": {
                "level": "INFO",
                "file": "logs/upwork_automation.log",
                "max_size_mb": 10,
                "backup_count": 5
            }
        }
    
    def _save_default_config(self) -> None:
        """Save default configuration to file"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving default configuration: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key (supports dot notation)"""
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_openai_config(self) -> Dict[str, Any]:
        """Get OpenAI API configuration with environment variable override"""
        config = self.get('openai', {}).copy()
        
        # Override API key from environment variable
        api_key = os.getenv('OPENAI_API_KEY')
        if api_key:
            config['api_key'] = api_key
        
        if 'api_key' not in config:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
        
        return config
    
    def get_browser_config(self) -> Dict[str, Any]:
        """Get browser automation configuration with environment overrides"""
        config = self.get('browser', {}).copy()
        
        # Override from environment variables
        headless = os.getenv('BROWSER_HEADLESS')
        if headless:
            config['headless'] = headless.lower() in ('true', '1', 'yes')
        
        return config
    
    def get_upwork_config(self) -> Dict[str, Any]:
        """Get Upwork configuration"""
        return self.get('upwork', {})
    
    def get_storage_config(self) -> Dict[str, Any]:
        """Get storage configuration"""
        return self.get('storage', {})
    
    def get_cover_letter_config(self) -> Dict[str, Any]:
        """Get cover letter generation configuration"""
        return self.get('cover_letter', {})
    
    def get_logging_config(self) -> Dict[str, Any]:
        """Get logging configuration with environment override"""
        config = self.get('logging', {}).copy()
        
        # Override log level from environment variable
        log_level = os.getenv('LOG_LEVEL')
        if log_level:
            config['level'] = log_level.upper()
        
        return config

# Global configuration instance
_config: Optional[Config] = None

def get_config() -> Config:
    """Get global configuration instance"""
    global _config
    if _config is None:
        _config = Config()
    return _config

def setup_logging() -> None:
    """Set up logging configuration"""
    config = get_config()
    log_config = config.get_logging_config()
    
    # Create logs directory if it doesn't exist
    log_file = Path(log_config.get('file', 'logs/upwork_automation.log'))
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure logging
    log_level = getattr(logging, log_config.get('level', 'INFO').upper())
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Set up root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Clear existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # File handler with rotation
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=log_config.get('max_size_mb', 10) * 1024 * 1024,
        backupCount=log_config.get('backup_count', 5),
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.WARNING)  # Only show warnings and errors in console
    logger.addHandler(console_handler)
