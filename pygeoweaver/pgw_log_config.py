import logging
import os

def setup_logging():
    # Use the $HOME environment variable to set the log path
    home_dir = os.environ.get('HOME', os.path.expanduser('~'))
    log_file = os.path.join(home_dir, 'geoweaver', 'logs', 'pygeoweaver.log')

    # Ensure the directory for the log file exists, create if not
    log_dir = os.path.dirname(log_file)
    os.makedirs(log_dir, exist_ok=True)

    # Get the root logger
    root_logger = logging.getLogger()
    
    # Check if handlers have already been added to this logger
    if root_logger.hasHandlers():
        return root_logger

    root_logger.setLevel(logging.DEBUG)

    # Create a file handler
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)

    # Create a formatter and set it for the handler
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)

    # Add the handler to the root logger
    root_logger.addHandler(file_handler)

    return root_logger

def get_logger(class_name):
    """
    Get a logger with the specified class name.
    """
    setup_logging()
    return logging.getLogger(class_name)
