import inspect
import io
import logging
from functools import wraps
import os
import sys

# Ensure the log directory exists
LOG_DIR = os.path.expanduser("~/geoweaver_logs")
os.makedirs(LOG_DIR, exist_ok=True)

def get_log_file_path(func_name):
    return os.path.join(LOG_DIR, f"{func_name}_logs.log")

logger = logging.getLogger(__name__)


def geoweaver_workflow(func):
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        workflow_name = func.__name__
        try:
            # Capture the source code of the wrapped function
            workflow_code = inspect.getsource(func)
        except OSError:
            workflow_code = f"# Source code not available for {workflow_name}"

        with open(f"{LOG_DIR}/{workflow_name}_code.py", "w") as code_file:
            code_file.write(workflow_code)

        # Capture logging output
        logger.info(f"Starting workflow {workflow_name}")

        # Capture console output
        captured_stdout = io.StringIO()
        captured_stderr = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = captured_stdout
        sys.stderr = captured_stderr

        try:
            result = func(*args, **kwargs)
        finally:
            # Restore standard output and error
            sys.stdout = old_stdout
            sys.stderr = old_stderr

            # Log the captured output
            stdout_content = captured_stdout.getvalue()
            stderr_content = captured_stderr.getvalue()
            if stdout_content:
                logger.info(f"Standard Output:\n{stdout_content}")
                print(stdout_content)
            if stderr_content:
                logger.error(f"Standard Error:\n{stderr_content}")
                print(stderr_content)

            logger.info(f"Finished workflow {workflow_name}")

        return result

    return wrapper

