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
    
    # Ensure the log directory exists
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception as e:
        print(f"Warning: Could not create log directory {log_dir}: {e}")
        # Fallback to home directory
        home_dir = os.environ.get('HOME', os.path.expanduser('~'))
        log_dir = os.path.join(home_dir, 'geoweaver', 'logs')
        os.makedirs(log_dir, exist_ok=True)
        print(f"Using fallback log directory: {log_dir}")
    
    log_file = os.path.join(log_dir, 'pygeoweaver.log')

    root_logger = logging.getLogger()
    
    # If force_new is True, remove existing file handlers and create new one
    if force_new:
        # Remove existing file handlers and close them properly
        for handler in root_logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                try:
                    handler.close()
                except:
                    pass
                root_logger.removeHandler(handler)
    
    # Only add new handler if no handlers exist or if force_new is True
    if not root_logger.hasHandlers() or force_new:
        root_logger.setLevel(logging.DEBUG)
        
        # Create file handler with error handling
        try:
            file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            print(f"Warning: Could not create file handler for {log_file}: {e}")
            # Try to create a basic file handler without encoding
            try:
                file_handler = logging.FileHandler(log_file, mode='a')
                file_handler.setLevel(logging.DEBUG)
                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                file_handler.setFormatter(formatter)
                root_logger.addHandler(file_handler)
            except Exception as e2:
                print(f"Error: Could not create any file handler: {e2}")
                # Continue without file logging
    
    return root_logger

def get_logger(class_name):
    """
    Get a logger with the specified class name.
    """
    setup_logging()
    return logging.getLogger(class_name)
