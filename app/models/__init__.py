"""SQLAlchemy models.

Importing this package registers all model classes with ``Base.metadata`` so
Alembic can discover every table.
"""

from app.models.ai_usage import AIUsage
from app.models.conversation import Conversation
from app.models.dataset import Dataset
from app.models.message import Message
from app.models.user import User

__all__ = ["AIUsage", "Conversation", "Dataset", "Message", "User"]
