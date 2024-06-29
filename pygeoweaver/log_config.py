import logging
import os


def setup_logging():
    log_file = '~/geoweaver.log'
    log_file = os.path.expanduser(log_file)

    # Ensure the directory for the log file exists, create if not
    log_dir = os.path.dirname(log_file)
    os.makedirs(log_dir, exist_ok=True)
    with open('logging.ini', 'rt') as f:
        config_str = f.read()
        config_str = config_str.replace('%(log_file)s', os.path.expanduser(log_file))

    config_file = 'logging_temp.ini'
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
