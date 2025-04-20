
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

### resetpassword

- **Usage**: `resetpassword`
- **Description**: Resets the password for localhost.
- **Options**:
  - `-p <password>`: Specify the password to reset.
- **Expected Behavior**: Prompts for password input twice to ensure accuracy.
- **Output**: Confirmation of password reset.

### cleanh2db

- **Usage**: `cleanh2db`
- **Description**: Cleans the H2 database.
- **Options**: None
- **Expected Behavior**: Removes unnecessary data from the H2 database.
- **Output**: Confirmation of database cleanup.

### create

- **Usage**: `create`
- **Description**: Creates a new object.
- **Options**:
  - `-t <type>`: Specify the type of object to create.
- **Expected Behavior**: Creates the specified object type.
- **Output**: Confirmation of object creation.

### detail

- **Usage**: `detail`
- **Description**: Provides detailed information about an object.
- **Options**:
  - `-i <id>`: Specify the ID of the object.
- **Expected Behavior**: Displays detailed information about the specified object.
- **Output**: Detailed object information.

### export

- **Usage**: `export`
- **Description**: Exports data to a specified format.
- **Options**:
  - `-f <format>`: Specify the export format.
- **Expected Behavior**: Exports data in the specified format.
- **Output**: Confirmation of data export.

### find

- **Usage**: `find`
- **Description**: Finds objects based on criteria.
- **Options**:
  - `-c <criteria>`: Specify the search criteria.
- **Expected Behavior**: Searches for objects matching the criteria.
- **Output**: List of matching objects.

### help

- **Usage**: `help`
- **Description**: Displays help information.
- **Options**: None
- **Expected Behavior**: Shows help information for commands.
- **Output**: Help information.

### history

- **Usage**: `history`
- **Description**: Displays command history.
- **Options**: None
- **Expected Behavior**: Shows the history of executed commands.
- **Output**: Command history.

### import

- **Usage**: `import`
- **Description**: Imports data from a specified source.
- **Options**:
  - `-s <source>`: Specify the import source.
- **Expected Behavior**: Imports data from the specified source.
- **Output**: Confirmation of data import.

### interface

- **Usage**: `interface`
- **Description**: Manages interface settings.
- **Options**:
  - `-s <setting>`: Specify the setting to manage.
- **Expected Behavior**: Adjusts interface settings.
- **Output**: Confirmation of setting adjustment.

### list

- **Usage**: `list`
- **Description**: Lists available objects.
- **Options**:
  - `-t <type>`: Specify the type of objects to list.
- **Expected Behavior**: Lists objects of the specified type.
- **Output**: List of objects.

### run

- **Usage**: `run`
- **Description**: Executes a specified command.
- **Options**:
  - `-c <command>`: Specify the command to execute.
- **Expected Behavior**: Runs the specified command.
- **Output**: Command execution result.

### sync

- **Usage**: `sync`
- **Description**: Synchronizes data.
- **Options**: None
- **Expected Behavior**: Synchronizes data between sources.
- **Output**: Confirmation of synchronization.

### upgrade

- **Usage**: `upgrade`
- **Description**: Upgrades the application.
- **Options**: None
- **Expected Behavior**: Upgrades to the latest version.
- **Output**: Confirmation of upgrade.
