import logging
import os
import tempfile

def setup_logging(log_dir=None, force_new=False):
    """
    Set up logging for pygeoweaver. If log_dir is not provided, use home directory (old behavior).
    
    Args:
        log_dir (str, optional): Directory to store log files. Defaults to home directory.
        force_new (bool): If True, force creation of new file handler even if handlers exist.
    """
    if log_dir is None:
        home_dir = os.environ.get('HOME', os.path.expanduser('~'))
        log_dir = os.path.join(home_dir, 'geoweaver', 'logs')
    else:
        print(f"Using provided log directory: {log_dir}")
    
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'pygeoweaver.log')

    root_logger = logging.getLogger()
    
    # If force_new is True, remove existing file handlers and create new one
    if force_new:
        # Remove existing file handlers
        for handler in root_logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                root_logger.removeHandler(handler)
    
    # Only add new handler if no handlers exist or if force_new is True
    if not root_logger.hasHandlers() or force_new:
        root_logger.setLevel(logging.DEBUG)
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    return root_logger

def get_logger(class_name):
    """
    Get a logger with the specified class name.
    """
    setup_logging()
    return logging.getLogger(class_name)
