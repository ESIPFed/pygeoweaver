import inspect
import io
import logging
from functools import wraps
import os
import sys

from pygeoweaver.runtime_tags.pgw_process import geoweaver_context


logger = logging.getLogger(__name__)


def geoweaver_workflow(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        workflow_name = func.__name__
        
        # Set the current workflow in context
        geoweaver_context['current_workflow'] = workflow_name
        
        # Execute the workflow function
        result = func(*args, **kwargs)
        
        # Clear the current workflow in context
        geoweaver_context['current_workflow'] = None
        
        # Retrieve the process calls for this workflow
        process_calls = geoweaver_context['process_calls'].get(workflow_name, [])
        
        # Print process calls (for demonstration)
        for call in process_calls:
            print(f"Process Name: {call['name']}")
            print("Source Code:")
            print(call['code'])
            print("Logs:")
            print(call['log'])
            print("-" * 40)
        
        return result
    
    return wrapper

