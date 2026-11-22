"""Database model persistence and constraints tests."""

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import create_db_engine
from app.models import Conversation, Dataset, Message, User


def test_models_persist_and_cascade_on_user_delete(tmp_path: Path) -> None:
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'models.db').as_posix()}")
    Base.metadata.create_all(engine)

    try:
        with Session(engine) as session:
            user = User(email="analyst@example.com", password_hash="hashed-password")
            dataset = Dataset(
                user=user,
                name="sales.csv",
                file_path=str(tmp_path / "sales.csv"),
                schema_json={"columns": [{"name": "sales", "type": "number"}]},
                row_count=10,
                status="ready",
            )
            conversation = Conversation(user=user, dataset=dataset)
            message = Message(
                conversation=conversation,
                role="user",
                content="Show sales by region",
            )
            session.add_all([user, dataset, conversation, message])
            session.commit()

            assert dataset.user_id == user.id
            assert conversation.dataset_id == dataset.id
            assert message.conversation_id == conversation.id
            assert dataset.schema_json["columns"][0]["name"] == "sales"

            session.delete(user)
            session.commit()

            for model in (User, Dataset, Conversation, Message):
                count = session.scalar(select(func.count()).select_from(model))
                assert count == 0
    finally:
        engine.dispose()
