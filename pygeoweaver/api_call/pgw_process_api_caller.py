
import requests

from pygeoweaver.api_call.pgw_base_api_caller import BaseAPI

class GeoweaverProcessAPI(BaseAPI):
    
    def edit_process(self, process_data):
        return self._call_api('/edit/process', method='POST', data=process_data)

    def add_process(self, process_data):
        return self._call_api('/add/process', method='POST', data=process_data)

    def get_process(self, process_id):
        return self._call_api(f'/get/process/{process_id}', method='GET')

    def delete_process(self, process_id):
        return self._call_api(f'/delete/process/{process_id}', method='DELETE')

