"""Utility functions for handling configuration files in Geoweaver."""

import os
import logging
from configparser import ConfigParser

logger = logging.getLogger(__name__)

def read_properties_file(file_path):
    """
    Read a Java-style properties file and return a dictionary of key-value pairs.
    
    Args:
        file_path (str): Path to the properties file
        
    Returns:
        dict: Dictionary containing the properties
    """
    properties = {}
    
    if not os.path.exists(file_path):
        logger.debug(f"Properties file not found: {file_path}")
        return properties
    
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                if '=' in line:
                    key, value = line.split('=', 1)
                    properties[key.strip()] = value.strip()
    except Exception as e:
        logger.error(f"Error reading properties file {file_path}: {e}")
    
    return properties

def get_database_url_from_properties():
    """
    Get the database URL from the application.properties file if it exists.
    
    Returns:
        str or None: The database URL if found, None otherwise
    """
    home_dir = os.path.expanduser("~")
    properties_path = os.path.join(home_dir, "geoweaver", "application.properties")
    
    properties = read_properties_file(properties_path)
    
    # Look for database URL configuration
    # Common property names for database URL in Spring applications
    possible_keys = [
        "spring.datasource.url",
        "database.url",
        "db.url",
        "datasource.url",
        "jdbc.url"
    ]
    
    for key in possible_keys:
        if key in properties:
            url = properties[key]
            logger.info(f"Found database URL in properties file: {url}")
            return url
    
    return None