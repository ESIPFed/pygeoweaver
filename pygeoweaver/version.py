"""
Version management for pygeoweaver.
"""
import os
import toml
from pathlib import Path


def get_version():
    """
    Get the version from pyproject.toml file.
    
    Returns:
        str: The version string from pyproject.toml
    """
    try:
        # Get the directory containing this file
        current_dir = Path(__file__).parent.parent
        pyproject_path = current_dir / "pyproject.toml"
        
        if pyproject_path.exists():
            with open(pyproject_path, 'r') as f:
                data = toml.load(f)
                return data.get('project', {}).get('version', 'unknown')
        else:
            # Fallback: try to get version from installed package
            try:
                import importlib.metadata
                return importlib.metadata.version('pygeoweaver')
            except ImportError:
                # For Python < 3.8
                try:
                    import pkg_resources
                    return pkg_resources.get_distribution('pygeoweaver').version
                except:
                    return 'unknown'
    except Exception:
        return 'unknown'


__version__ = get_version() 