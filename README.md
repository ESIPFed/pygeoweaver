# Pygeoweaver

Pygeoweaver is a Python library for geospatial data processing and analysis. It provides a user-friendly functionality to create and execute processes and workflows for geospatial tasks.

## Features

- Easy creation of geospatial processes and workflows.
- Support for multiple programming languages.
- Integration with GeoWeaver API for process execution.
- Documentation available at [https://gokulprathin8.github.io/pygeoweaver-docs.github.io/](https://gokulprathin8.github.io/pygeoweaver-docs.github.io/).

## Installation

You can install Pygeoweaver using pip:

```bash
pip install pygeoweaver
```

## Usage

Here's a basic example of how to use Pygeoweaver to create a process:

```python
from pygeoweaver import create_process

lang = "python"
description = "Process for calculating NDVI"
name = "NDVI Calculation"
code = """
# Python code for calculating NDVI
# ...

# Your code here
"""

# Create the process
process_id = create_process(lang, description, name, code)
```

To create a process from a file:

```python
from pygeoweaver import create_process_from_file

lang = "python"
description = "Process for calculating NDVI"
name = "NDVI Calculation"
file_path = "ndvi_calculation.py"

# Create the process from the file
process_id = create_process_from_file(lang, description, name, file_path)
```

Creating a workflow:

```python
from pygeoweaver import create_workflow

description = "Workflow for processing geospatial data"
edges = "..."
name = "Data Processing Workflow"
nodes = "..."

# Create the workflow
workflow_id = create_workflow(description, edges, name, nodes)
```

For more information and detailed documentation, please visit [https://gokulprathin8.github.io/pygeoweaver-docs.github.io/](https://gokulprathin8.github.io/pygeoweaver-docs.github.io/).

## Contributing

Contributions to Pygeoweaver are welcome! If you find any issues or have suggestions for improvements, please feel free to open an issue or submit a pull request on the GitHub repository.

## License

Pygeoweaver is licensed under the MIT License. 

---

Thank you for choosing Pygeoweaver! We hope this library simplifies your geospatial data processing tasks. If you have any questions or need further assistance, please refer to the documentation or reach out to us. Happy coding!
