import inspect
import logging
from logging.config import fileConfig
import os


def setup_logging():
    # Use the $HOME environment variable to set the log path
    home_dir = os.environ.get('HOME', os.path.expanduser('~'))
    log_file = os.path.join(home_dir, 'geoweaver', 'logs', 'pygeoweaver.log')

    # Ensure the directory for the log file exists, create if not
    log_dir = os.path.dirname(log_file)
    os.makedirs(log_dir, exist_ok=True)
    
    # Get the absolute path of the current script or notebook file
    current_file = inspect.getfile(inspect.currentframe())
    current_file_path = os.path.abspath(current_file)
    current_folder = os.path.dirname(current_file_path)
    # Get the absolute path to the pgw_logging.ini file
    logging_ini_path = os.path.abspath(f'{current_folder}/pgw_logging.ini')

    # Open the pgw_logging.ini file
    with open(logging_ini_path, 'rt') as f:
        config_str = f.read()
        config_str = config_str.replace('%(log_file)s', os.path.abspath(log_file).replace('\\', '/'))

    config_file = f'{current_folder}/logging_temp.ini'
    with open(config_file, 'wt') as f:
        f.write(config_str)

    # Configure the root logger
    fileConfig(config_file)
    
    # Ensure all module-level loggers also use the file handler
    root_logger = logging.getLogger()
    
    # Check if the root logger has a file handler
    has_file_handler = False
    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            has_file_handler = True
            break
    
    # If no file handler is present, add one manually
    if not has_file_handler:
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Set the root logger level
    root_logger.setLevel(logging.DEBUG)
    
    # Ensure propagation to child loggers
    root_logger.propagate = True
    
    # Clean up the temporary config file
    os.remove(config_file)
    
    # Return the root logger for debugging purposes
    return root_logger


def get_logger(class_name):
    """
    Get a logger with the specified class name.
    """
    setup_logging()
    
    logger = logging.getLogger(class_name)
    logger.setLevel(logging.DEBUG)  # Set to DEBUG level to capture all messages
    
    # Check if handlers are already present
    if not logger.handlers:
        # Add a console handler
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)
        logger.addHandler(console_handler)
    
    return logger
