import os
import re
import shutil
import click
from pathlib import Path

def cleanup_workspace():
    """Clean up temporary directories in the gw-workspace folder."""
    try:
        # Get the user's home directory in a cross-platform way
        home_dir = str(Path.home())
        workspace_dir = os.path.join(home_dir, "gw-workspace")
        
        if not os.path.exists(workspace_dir):
            click.echo(f"Workspace directory {workspace_dir} does not exist.")
            return
        
        # Compile regex patterns for 11 and 12 character directory names
        pattern_11 = re.compile(r'^[a-zA-Z0-9]{11}$')
        pattern_12 = re.compile(r'^[a-zA-Z0-9]{12}$')
        
        # Counter for removed directories
        removed_count = 0
        
        # Iterate through immediate subdirectories
        for item in os.listdir(workspace_dir):
            item_path = os.path.join(workspace_dir, item)
            
            # Check if it's a directory and matches either pattern
            if os.path.isdir(item_path) and (pattern_11.match(item) or pattern_12.match(item)):
                try:
                    shutil.rmtree(item_path)
                    removed_count += 1
                except Exception as e:
                    click.echo(f"Error removing directory {item}: {str(e)}")
        
        if removed_count > 0:
            click.echo(f"Successfully removed {removed_count} temporary directories.")
        else:
            click.echo("No temporary directories found to clean up.")
            
    except Exception as e:
        click.echo(f"Error during cleanup: {str(e)}")