"""one vault for everything you read: web, papers, video, files and code, searchable together and answerable by a local or hosted model

Modules:

- `vishalakshi.skill`: one vault for everything you have read: web pages, papers, video, files, code and your own notes in one SQLite file, searchable together and answerable by a local or hosted model"""

__version__ = "0.1.7"
from .core import *
from .jobs import *
from .acquire import *
from .ask import *
from .quality import *
from .code import *
from .extract import *
from .pii import *
