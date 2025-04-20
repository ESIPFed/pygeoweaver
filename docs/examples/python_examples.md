# Python Code Examples for PyGeoWeaver

## Starting GeoWeaver

To start GeoWeaver from a Python script, use the following code:

```python
import geoweaver
geoweaver.start()
```

## Stopping GeoWeaver

To stop GeoWeaver, execute:

```python
import geoweaver
geoweaver.stop()
```

## Listing Existing Objects

To list all hosts, processes, and workflows:

```python
import geoweaver
geoweaver.list_hosts()
geoweaver.list_processes()
geoweaver.list_workflows()
```

## Running a Workflow

To run a specific workflow, use:

```python
import geoweaver
geoweaver.run_workflow("workflow_id", "host_id_list", "password_list", "environment_list")
```

## Exporting a Workflow

To export a workflow to a ZIP file:

```python
import geoweaver
geoweaver.export_workflow("workflow_id", "workflow_zip_save_path")
```

## Importing a Workflow

To import a workflow from a ZIP file:

```python
import geoweaver
geoweaver.import_workflow("workflow_zip_file_path")
```