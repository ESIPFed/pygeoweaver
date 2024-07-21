from pygeoweaver.server import start, stop
import pytest
from pygeoweaver.api_call.pgw_base_api_caller import BaseAPI
from pygeoweaver.api_call.pgw_process_api_caller import GeoweaverProcessAPI  # Adjust the import path as needed

# Define the base URL for the API
BASE_URL = "http://localhost:8070"  # Update with your actual base URL

@pytest.fixture(scope="session")
def start_geoweaver():
    # Start the Geoweaver server
    start(exit_on_finish=False)

    yield
    
    # Stop the Geoweaver server
    stop(exit_on_finish=False)

@pytest.fixture
def geoweaver_api():
    return GeoweaverProcessAPI(base_url=BASE_URL)

@pytest.fixture
def create_process(geoweaver_api):
    
    # Example process data
    process_data = {
        "name": "Test Process",
        "description": "A test process for pytest",
        "parameters": {"param1": "value1"}
    }
    response = geoweaver_api.add_process(process_data)
    print(response)
    assert response.status_code == 201, "Failed to create process"
    process_id = response.json().get("id")
    yield process_id, process_data
    # Cleanup: Ensure process is deleted after test
    geoweaver_api.delete_process(process_id)
    # Verify the process is deleted
    response = geoweaver_api.get_process(process_id)
    assert response.status_code == 404, "Process should be deleted"

def test_edit_process(geoweaver_api, create_process):
    process_id, process_data = create_process
    updated_data = {
        "name": "Updated Test Process",
        "description": "An updated test process",
        "parameters": {"param1": "new_value"}
    }
    response = geoweaver_api.edit_process({**updated_data, "id": process_id})
    assert response.status_code == 200, "Failed to edit process"
    assert response.json().get("id") == process_id

def test_get_process(geoweaver_api, create_process):
    process_id, _ = create_process
    response = geoweaver_api.get_process(process_id)
    assert response.status_code == 200, "Failed to get process"
    process = response.json()
    assert process.get("id") == process_id

def test_delete_process(geoweaver_api, create_process):
    process_id, _ = create_process
    response = geoweaver_api.delete_process(process_id)
    assert response.status_code == 200, "Failed to delete process"

    # Verify the process is deleted
    response = geoweaver_api.get_process(process_id)
    assert response.status_code == 404, "Process should be deleted"
