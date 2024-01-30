import os.path

import requests
from pygeoweaver.utils import (
    download_geoweaver_jar,
)


def import_workflow(workflow_zip_file_path):
    """
    Usage: <main class> import workflow <workflow_zip_file_path>
    import a workflow from file
          <workflow_zip_file_path>
            Geoweaver workflow zip file path
    """
    from pygeoweaver import GEOWEAVER_DEFAULT_ENDPOINT_URL
    if not workflow_zip_file_path:
        raise RuntimeError("Workflow zip file path is missing")
    download_geoweaver_jar()
    file_upload_servlet = f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/FileUploadServlet"
    preload_url = f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/preload/workflow"
    load_url = f"{GEOWEAVER_DEFAULT_ENDPOINT_URL}/web/load/workflow"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    file_name = os.path.basename(workflow_zip_file_path)
    _id, _ = os.path.splitext(file_name)
    files = {'file': (file_name, open(workflow_zip_file_path, 'rb'))}
    requests.post(url=file_upload_servlet, files=files)  # upload
    requests.post(url=preload_url, headers=headers, data={'id': _id, 'filename': file_name})  # preload
    requests.post(url=load_url, headers=headers, data={'id': _id, 'filename': file_name})  # load
    return 'Import success.'


def import_workflow_from_github(git_repo_url):
    pass
