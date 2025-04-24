
## PyGeoWeaver

||  |
|--|--|
|Latest Release|![Static Badge](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54&label=python%203.9%20%7C%20python%203.10%20%7C%20python%203.11)  ![PyPI](https://img.shields.io/pypi/v/pygeoweaver?style=for-the-badge&label=Pygeoweaver)|
|Getting Help| [![Documentation Status](https://readthedocs.org/projects/pygeoweaver/badge/?version=latest&style=for-the-badge)](https://pygeoweaver.readthedocs.io/en/latest/?badge=latest) |
|Activity|![PyPI - Downloads](https://img.shields.io/pypi/dm/pygeoweaver?style=for-the-badge) ![GitHub commit activity (branch)](https://img.shields.io/github/commit-activity/m/ESIPFed/pygeoweaver?style=for-the-badge&label=Commit%20Activity)|
|Community| ![Static Badge](https://img.shields.io/badge/ESIP-blue?style=for-the-badge&link=https%3A%2F%2Fwww.esipfed.org%2F)|
|License|![GitHub](https://img.shields.io/github/license/ESIPFed/pygeoweaver?style=for-the-badge)|

PyGeoWeaver is a Python package that provides a convenient and user-friendly interface to interact with GeoWeaver, a powerful geospatial data processing application written in Java. With PyGeoWeaver, Jupyter notebook and JupyterLab users can seamlessly integrate and utilize the capabilities of GeoWeaver within their Python workflows.

## Installation

To install PyGeoWeaver, ensure you have Python 3.7 or later installed. You can then install PyGeoWeaver using pip:

```bash
pip install pygeoweaver
```

## Startup

To start using PyGeoWeaver, you can launch the GeoWeaver graphical user interface by executing the following command in a Jupyter notebook cell:

```python
import geoweaver
geoweaver.start()
```

Alternatively, you can start GeoWeaver directly from the terminal:

```shell
gw start
```

## Options and Help Text

PyGeoWeaver provides several commands to interact with GeoWeaver. Below is a list of available options and their descriptions:

- **Launching GeoWeaver GUI**: Opens the GeoWeaver interface.
  ```python
  geoweaver.start()
  ```
  or
  ```shell
gw start
  ```

- **Stopping GeoWeaver**: Stops the GeoWeaver interface.
  ```python
  geoweaver.stop()
  ```
  or
  ```shell
gw stop
  ```

- **Listing Existing Objects**: Lists hosts, processes, and workflows.
  ```python
  geoweaver.list_hosts()
  geoweaver.list_processes()
  geoweaver.list_workflows()
  ```

- **Running a Workflow**: Executes a specified workflow.
  ```python
  geoweaver.run_workflow("workflow_id", "host_id_list", "password_list", "environment_list")
  ```

- **Exporting a Workflow**: Exports a workflow to a ZIP file.
  ```python
  geoweaver.export_workflow("workflow_id", "workflow_zip_save_path")
  ```

- **Importing a Workflow**: Imports a workflow from a ZIP file.
  ```python
  geoweaver.import_workflow("<workflow_zip_file_path>")
  ```

- **Viewing Workflow and Process History**: Retrieves the history of a workflow or process run.
  ```python
  geoweaver.get_workflow_history("<workflow_history_id>")
  geoweaver.get_process_history("<process_history_id>")
  ```

- **Inspecting Process Source Code**: Views the source code of a process.
  ```python
  geoweaver.detail_process("<process_id>")
  ```

- **Inspecting Workflow Configuration**: Checks the configuration details of a workflow.
  ```python
  geoweaver.detail_workflow("<workflow_id>")
  ```

- **Inspecting Host Details**: Retrieves the details of a host.
  ```python
  geoweaver.detail_host("<host_id>")
  ```

## Documentation

For detailed documentation and examples, please visit the [PyGeoWeaver Documentation](https://pygeoweaver.readthedocs.io/).

## Contributing

Contributions to PyGeoWeaver are welcome! If you encounter any issues or have suggestions for improvements, please feel free to open an issue or submit a pull request on the GitHub repository.

## License

PyGeoWeaver is licensed under the MIT License. See the LICENSE file for more details.

---

Thank you for choosing PyGeoWeaver! We hope this package enhances your geospatial data processing workflows. If you have any questions or need assistance, please refer to the documentation or reach out to us. Happy geospatial processing!

## Subcommands Documentation

### cleanh2db

- **Usage**: `gw cleanh2db [OPTIONS]`
- **Description**: Clean and reduce the size of the H2 database used by Geoweaver.
  
  This command follows these steps:
  1. Stop Geoweaver if it's running
  2. Create a temporary directory if one is not provided
  3. Copy database files to the temporary directory
  4. Export data from the database to a SQL file
  5. Remove the original database files
  6. Import the SQL file into a new database
  7. Start Geoweaver

- **Options**:
  - `--h2-jar-path PATH`: Path to the H2 database JAR file. If not provided, will use h2-2.2.224.jar in the current directory.
  - `--temp-dir PATH`: Path to a temporary directory for the recovery process. If not provided, will create one.
  - `--db-path PATH`: Path to the H2 database files. If not provided, will use ~/h2/gw.
  - `--username TEXT`: Username for the H2 database. Defaults to "geoweaver".
  - `--password TEXT`: Password for the H2 database. If not provided, will prompt the user.
  - `--help`: Show this message and exit.

### create

- **Usage**: `gw create [OPTIONS] COMMAND [ARGS]...`
- **Description**: Create commands for Geoweaver.
- **Commands**:
  - `process`: Create a process with given code or file path
    - **Options**:
      - `--lang`: Programming language of the process
      - `--description`: Description of the process
      - `--name`: Name of the process
      - `--code`: Process code
      - `--file-path`: Path to file containing the code
      - `--owner`: Owner ID (default: "111111")
      - `--confidential`: Privacy flag (default: false)
  - `workflow`: Create a workflow with given configuration
    - **Options**:
      - `--description`: Workflow description
      - `--edges`: Workflow edges configuration
      - `--name`: Workflow name
      - `--nodes`: Workflow nodes configuration
      - `--owner`: Owner ID (default: "111111")
      - `--confidential`: Privacy flag (default: false)
- **Examples**:
  ```shell
  # Create a process
  gw create process --lang python --name "my_process" --description "My process" --code "print('Hello')" 
  
  # Create a process from file
  gw create process --lang python --name "file_process" --description "Process from file" --file-path "script.py"
  
  # Create a workflow
  gw create workflow --name "my_workflow" --description "My workflow" --nodes "[...]" --edges "[...]"
  ```

### detail

- **Usage**: `gw detail [OPTIONS] COMMAND [ARGS]...`
- **Description**: Display detailed information about Geoweaver objects.
- **Commands**:
  - `code`: Get the code of a process.
  - `host`: Display detailed information about a host.
  - `process`: Display detailed information about a process.
  - `workflow`: Display detailed information about a workflow.
- **Options**:
  - `--help`: Show help message and exit.
- **Examples**:
  ```shell
  gw detail process <process_id>
  gw detail workflow <workflow_id>
  gw detail host <host_id>
  gw detail code <process_id>
  ```

### export

- **Usage**: `gw export workflow [OPTIONS] WORKFLOW_ID TARGET_FILE_PATH`
- **Description**: Exports a workflow to a specified file.
- **Arguments**:
  - `workflow_id`: Geoweaver workflow ID
  - `target_file_path`: Target file path to save the workflow zip
- **Options**:
  - `--mode INTEGER`: Export mode (default: 4)
    - 1: Workflow only
    - 2: Workflow with process code
    - 3: Workflow with process code and only good history
    - 4: Workflow with process code and all history
  - `--unzip`: Unzip the exported file
  - `--unzip-directory-name TEXT`: Specify the directory name when unzipping
- **Example**:
  ```shell
  # Export workflow with all history
  gw export workflow my_workflow_id ./my_workflow.zip
  
  # Export workflow and unzip to specific directory
  gw export workflow --unzip --unzip-directory-name my_workflow my_workflow_id ./my_workflow.zip
  ```

### find

- **Usage**: `gw find [OPTIONS] COMMAND [ARGS]...`
- **Description**: Find commands for Geoweaver.
- **Commands**:
  - `id`: Get a process by its ID
    ```shell
    gw find id <process_id>
    ```
  - `language`: Get processes by their programming language
    ```shell
    gw find language <programming_language>
    ```
  - `name`: Get processes by their name
    ```shell
    gw find name <process_name>
    ```

### help

- **Usage**: `gw help [command]`
- **Description**: Displays help information for Geoweaver commands.
- **Arguments**: Optional command name to get specific help

### history

- **Usage**: `gw history [OPTIONS] COMMAND [ARGS]...`
- **Description**: History commands for Geoweaver.
- **Commands**:
  - `get_process`: Get list of history for a process using process id.
  - `get_workflow`: Get list of history for a workflow using workflow id.
  - `show`: Show history for a workflow or process.
- **Examples**:
  ```shell
  # Get history for a specific process
  gw history get_process <process_id>
  
  # Get history for a specific workflow
  gw history get_workflow <workflow_id>
  
  # Show detailed history information
  gw history show <history_id>
  ```

### import

- **Usage**: `gw import [OPTIONS] COMMAND [ARGS]...`
- **Description**: Import commands for Geoweaver.
- **Options**:
  - `--help`: Show this message and exit.

- **Commands**:
  - **workflow**: Import a workflow from a zip file.
    - **Usage**: `gw import workflow <workflow_zip_file_path>`
    - **Description**: Imports a workflow from a zip file.
    - **Arguments**:
      - `workflow_zip_file_path`: Path to the Geoweaver workflow zip file

For detailed usage examples and additional information, please refer to the [PyGeoWeaver Documentation](https://pygeoweaver.readthedocs.io/).
