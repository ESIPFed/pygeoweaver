import logging
import os
import tempfile

def setup_logging(log_dir=None):
    """
    Set up logging for pygeoweaver. If log_dir is not provided, use home directory (old behavior).
    """
    if log_dir is None:
        home_dir = os.environ.get('HOME', os.path.expanduser('~'))
        log_dir = os.path.join(home_dir, 'geoweaver', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'pygeoweaver.log')

    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        return root_logger
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
