from pygeoweaver.runtime_tags.pgw_process import pygeoweaver_process
from pygeoweaver.runtime_tags.pgw_workflow import pygeoweaver_workflow

@pygeoweaver_process
def process_one():
    print("Executing Process One")
    return "Process One Completed"

@pygeoweaver_process
def process_two():
    print("Executing Process Two")
    return "Process Two Completed"

@pygeoweaver_workflow
def example_workflow():
    result_one = process_one()
    result_two = process_two()
    print("Workflow Results:", result_one, result_two)

if __name__ == "__main__":
    example_workflow()