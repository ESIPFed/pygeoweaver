# Terminal Examples for PyGeoWeaver

## Starting GeoWeaver

To start GeoWeaver from the terminal, use the following command:

```shell
gw start
```

## Stopping GeoWeaver

To stop GeoWeaver, execute:

```shell
gw stop
```

## Listing Existing Objects

To list all hosts, processes, and workflows:

```shell
gw list -t hosts
```

```shell
gw list -t processes
```

```shell
gw list -t workflows
```

## Running a Workflow

To run a specific workflow, use:

```shell
gw run -c "workflow_id"
```

## Exporting a Workflow

To export a workflow to a ZIP file:

```shell
gw export -f zip -c "workflow_id"
```

## Importing a Workflow

To import a workflow from a ZIP file:

```shell
gw import -s "workflow_zip_file_path"
```

## Resetting Password

To reset the password for localhost:

```shell
resetpassword -p "new_password"
```

## Cleaning H2 Database

To clean the H2 database:

```shell
cleanh2db
```