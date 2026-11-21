from pygeoweaver.constants import GEOWEAVER_PORT
from pygeoweaver.server import start, stop
import pytest
from pygeoweaver.api_call.pgw_base_api_caller import BaseAPI
from pygeoweaver.api_call.pgw_process_api_caller import GeoweaverProcessAPI  # Adjust the import path as needed

# Define the base URL for the API
BASE_URL = f"http://localhost:{GEOWEAVER_PORT}"  # Update with your actual base URL

@pytest.fixture(scope="session")
def start_geoweaver():
    # Start the Geoweaver server
    start(exit_on_finish=False)
    # create api object
    geoweaver_api = GeoweaverProcessAPI(base_url=BASE_URL)
    # Example process data
    process_data = {
        "name": "Test Process",
        "description": "A test process for pytest",
        "parameters": {"param1": "value1"}
    }
    response = geoweaver_api.add_process(process_data)
    print("add process response: ", response)
    assert response["name"] == "Test Process"
    process_id = response["id"]
    
    yield process_id, process_data, geoweaver_api
    
    # Stop the Geoweaver server
    stop(exit_on_finish=False)
    # Cleanup: Ensure process is deleted after test
    geoweaver_api.delete_process(process_id)
    # Verify the process is deleted
    response = geoweaver_api.get_process(process_id)
    print("delete process response: ", response)
    assert response is None


def test_edit_process(start_geoweaver):
    process_id, process_data, geoweaver_api = start_geoweaver
    updated_data = {
        "name": "Updated Test Process",
        "description": "An updated test process",
        "parameters": {"param1": "new_value"}
    }
    response = geoweaver_api.edit_process({**updated_data, "id": process_id})
    print("edit process response: ", response)
    assert response["id"] == process_id

def test_get_process(start_geoweaver):
    process_id, _, geoweaver_api = start_geoweaver
    updated_data = {
        "type": 'process',
        "id": process_id
    }
    response = geoweaver_api.get_process(updated_data)
    print("get process response: ", response)
    assert response["id"] == process_id
    

def test_delete_process(start_geoweaver):
    process_id, _, geoweaver_api = start_geoweaver
    response = geoweaver_api.delete_process(process_id)
    assert response["id"] == process_id

    # Verify the process is deleted
    response = geoweaver_api.get_process(process_id)
    assert response["id"] == process_id
