
from pygeoweaver.api_call.pgw_base_api_caller import BaseAPI


class GeoweaverWorkflowAPI(BaseAPI):
    def add_workflow(self, workflow_data):
        return self._call_api('/add/workflow', method='POST', data=workflow_data)

    def edit_workflow(self, workflow_data):
        return self._call_api('/edit/workflow', method='POST', data=workflow_data)

    def get_workflow(self, workflow_id):
        return self._call_api(f'/get/workflow/{workflow_id}', method='GET')

    def delete_workflow(self, workflow_id):
        return self._call_api(f'/delete/workflow/{workflow_id}', method='DELETE')

