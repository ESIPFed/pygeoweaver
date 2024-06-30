import inspect
import io
import logging
from functools import wraps
import os
import sys

from pygeoweaver.commands.pgw_history import save_history

logger = logging.getLogger(__name__)

# Global context for tracking
geoweaver_context = {
    'current_workflow': None,
    'process_calls': {}
}


def pygeoweaver_process(func):
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        current_file = inspect.getfile(inspect.currentframe())
        current_file = os.path.basename(current_file)
        current_file_without_extension = os.path.splitext(current_file)[0]
        try:
            # Capture the source code of the wrapped function
            func_code = inspect.getsource(func)
        except OSError:
            func_code = f"# Source code not available for {func_name}"

        geoweaver_process_id = f"{current_file_without_extension}.{func_name}"
        logger.info("this process id should be unique: %s", geoweaver_process_id)
        
        # Capture logging output
        logger.info(f"geoweaver captured {func_name}")

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

            logger.info(f"Finished {func_name}")
            
        current_workflow = geoweaver_context['current_workflow']
        if current_workflow:
            if current_workflow not in geoweaver_context['process_calls']:
                geoweaver_context['process_calls'][current_workflow] = []
            geoweaver_context['process_calls'][current_workflow].append({
                'name': func_name,
                'code': func_code,
                'log': f"{stdout_content}\n{stderr_content}"
            })
            
        return result
    
    return wrapper
