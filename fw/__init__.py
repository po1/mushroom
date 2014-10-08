from .client import MRClient
from .db import MRDB

def get_class(name):
    return globals()[name]

