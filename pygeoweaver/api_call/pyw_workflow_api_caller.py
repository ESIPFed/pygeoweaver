
from typing import Any, Dict
from pygeoweaver.api_call.pgw_base_api_caller import BaseAPI


class GeoweaverWorkflowAPI(BaseAPI):
    def add_workflow(self, workflow_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Adds a new workflow by sending a POST request to the API.

        Parameters:
        - workflow_data (Dict[str, Any]): The data of the workflow to add. This should be a dictionary representing the workflow.

        Returns:
        - Dict[str, Any]: The JSON response from the server, parsed into a dictionary.
        """
        return self._call_api('/add/workflow', method='POST', data=workflow_data)

    def edit_workflow(self, workflow_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Edits an existing workflow by sending a POST request to the API.

        Parameters:
        - workflow_data (Dict[str, Any]): The data of the workflow to edit. This should be a dictionary representing the workflow with updates.

        Returns:
        - Dict[str, Any]: The JSON response from the server, parsed into a dictionary.
        """
        return self._call_api('/edit/workflow', method='POST', data=workflow_data)

    def get_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """
        Retrieves a workflow by its ID by sending a GET request to the API.

        Parameters:
        - workflow_id (str): The ID of the workflow to retrieve.

        Returns:
        - Dict[str, Any]: The JSON response from the server, parsed into a dictionary.
        """
        return self._call_api(f'/get/workflow/{workflow_id}', method='GET')

    def delete_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """
        Deletes a workflow by its ID by sending a DELETE request to the API.

        Parameters:
        - workflow_id (str): The ID of the workflow to delete.

        Returns:
        - Dict[str, Any]: The JSON response from the server, parsed into a dictionary.
        """
        return self._call_api(f'/delete/workflow/{workflow_id}', method='DELETE')
