import os

def get_root_dir():
    print(os.path.basename(__file__))
    head, tail = os.path.split(__file__)
    return head