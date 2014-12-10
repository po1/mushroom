from . import client
from . import world

from .db import db
from .register import get_class
from .register import get_type

# this will be loaded by the server
Database = db
Client = client.MRClient
