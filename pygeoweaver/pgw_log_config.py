import inspect
import logging
import os


def setup_logging():
    log_file = '~/geoweaver.log'
    log_file = os.path.expanduser(log_file)

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
        config_str = config_str.replace('%(log_file)s', os.path.expanduser(log_file))

    config_file = f'{current_folder}/logging_temp.ini'
    with open(config_file, 'wt') as f:
        f.write(config_str)

    logging.config.fileConfig(config_file)
    os.remove(config_file)


def get_logger(class_name):
    """
    Get a logger with the specified class name.
    """
    logger = logging.getLogger(class_name)
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    return logger
