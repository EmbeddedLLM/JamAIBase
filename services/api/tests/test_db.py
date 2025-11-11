from sqlmodel import select

from owl.db import async_session, sync_session
from owl.db.models import User
from owl.types import UserAuth
from owl.utils.test import create_user


async def test_async_session():
    with create_user() as user:
        assert user.id == "0"
        async with async_session() as session:
            users = (await session.exec(select(User))).all()
            users = [UserAuth.model_validate(user) for user in users]
            assert len(users) == 1


async def test_sync_session():
    with create_user() as user:
        assert user.id == "0"
        with sync_session() as session:
            users = (session.exec(select(User))).all()
            users = [UserAuth.model_validate(user) for user in users]
            assert len(users) == 1
