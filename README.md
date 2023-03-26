## PyGeoWeaver

### Description

This package is a Python wrapper of the GeoWeaver app which was written in Java. This package is designed for Jupyter users to be able to directly use Geoweaver in Jupyter notebook or JupyterLab (JupyterHub).

### Installation

`pip install pygeoweaver`

### Usage

1. To show Geoweaver graphic user interface, please create a new cell and type:

```
import geoweaver
geoweaver.start()
```

The command will first check if Geoweaver has been downloaded and installed. If no, it will automatically download and install Geoweaver in the local environment. Then it will open Geoweaver in the cell output in a iframe. Users can use all the functions provided in Geoweaver.

2. To stop Geoweaver, please run:

```
geoweaver.stop()
```

3. To list the existing objects, please run:

```
geoweaver.list("host")
geoweaver.list("process")
geoweaver.list("workflow")
```

4. To run a workflow, please run:
```
geoweaver.run_workflow()
```

5. To export a workflow:

```
geoweaver.export_workflow("workflow_id", "workflow_zip_save_path")
```

6. To import a workflow:

```
geoweaver.import_workflow("workflow_zip_file_path")
```

or

```
geoweaver.import_workflow("workflow_folder_path")
```

7. To get history of a workflow run:

```
geoweaver.history_workflow()
```

8. To get history of a process run:

```
geoweaver.history_process()
```

9. 
