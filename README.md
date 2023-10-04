
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

To install PyGeoWeaver, simply use pip:

```bash
pip install pygeoweaver
```

## Features

- Simplified creation of geospatial processes and workflows.
- Support for multiple programming languages.
- Seamless integration with the GeoWeaver API for efficient process execution.
- Comprehensive documentation available at [https://pygeoweaver.readthedocs.io/](https://pygeoweaver.readthedocs.io/).

## Usage

1. **Launching GeoWeaver GUI**: To open the GeoWeaver graphical user interface, create a new cell and execute the following code:

```python
import geoweaver
geoweaver.start()
```

This command checks if GeoWeaver is already installed. If not, it will automatically download and install GeoWeaver in your local environment. The GeoWeaver interface will then open in the cell output as an iframe, allowing you to access and utilize all the features provided by GeoWeaver.

2. **Stopping GeoWeaver**: To stop GeoWeaver, use the following command:

```python
geoweaver.stop()
```

3. **Listing Existing Objects**: To list the existing hosts, processes, and workflows, execute the respective commands:

```python
geoweaver.list_hosts()
geoweaver.list_processes()
geoweaver.list_workflows()
```

4. **Running a Workflow**: To execute a workflow, use the following command:

```python
geoweaver.run_workflow("workflow_id", "host_id_list", "password_list", "environment_list")
```

Alternatively, you can run a workflow by specifying the path to the workflow ZIP file or the local folder containing the workflow files.

5. **Exporting a Workflow**: To export a workflow, use the following command:

```python
geoweaver.export_workflow("workflow_id", "workflow_zip_save_path")
```

This command exports the specified workflow to a ZIP file, which is saved at the provided save path.

6. **Importing a Workflow**: To import a workflow, use the following command:

```python
geoweaver.import_workflow("<workflow_zip_file_path>")
```

Alternatively, you can import a workflow by specifying the path to the workflow folder.

7. **Viewing Workflow and Process History**: To retrieve the history of a workflow run or a process run, use the respective commands:

```python
geoweaver.get_workflow_history("<workflow_history_id>")
geoweaver.get_process_history("<process_history_id>")
```

8. **Inspecting Process Source Code**: To view the source code of a process, use the following command:

```python
geoweaver.detail_process("<process_id>")
```

9. **Inspecting Workflow Configuration**: To check the configuration details of a workflow, execute the following command:

```python
geoweaver.detail_workflow("<workflow_id>")
```

10. **Inspecting Host Details**: To retrieve the details of a host, use the following command:

```python
geoweaver.detail_host("<host_id>")
```

## Documentation

For detailed documentation and examples, please visit the [PyGeoWeaver Documentation](https://pygeoweaver.readthedocs.io/).

## Contributing

Contributions to PyGeoWeaver are welcome!

 If you encounter any issues or have suggestions for improvements, please feel free to open an issue or submit a pull request on the GitHub repository.

## License

PyGeoWeaver is licensed under the MIT License. 

---

Thank you for choosing PyGeoWeaver! We hope this package enhances your geospatial data processing workflows. If you have any questions or need assistance, please refer to the documentation or reach out to us. Happy geospatial processing!
