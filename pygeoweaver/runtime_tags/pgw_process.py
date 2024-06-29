import inspect
import io
import logging
from functools import wraps
import os
import sys

from pygeoweaver.commands.pgw_history import save_history

logger = logging.getLogger(__name__)


def geoweaver_process(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        try:
            # Capture the source code of the wrapped function
            func_code = inspect.getsource(func)
        except OSError:
            func_code = f"# Source code not available for {func_name}"

        # Capture logging output
        logger.info(f"Starting {func_name}")

        # Capture console output
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        
        try:
            result = func(*args, **kwargs)
        finally:
            # Restore standard output and error
            stdout_content = sys.stdout.getvalue()
            stderr_content = sys.stderr.getvalue()
            sys.stdout = old_stdout
            sys.stderr = old_stderr

            # Log the captured output
            if stdout_content:
                logger.info(f"Standard Output:\n{stdout_content}")
            if stderr_content:
                logger.error(f"Standard Error:\n{stderr_content}")

        save_history(code=func_code, log_output=stdout_content, status=None)

        logger.info(f"Finished {func_name}")
        
        return result
    
    return wrapper
