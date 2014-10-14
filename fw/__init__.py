from . import client
from . import db
from . import world

from .register import get_class
from .register import get_type

# this will be loaded by the server
Database = db
Client = client.MRClient
