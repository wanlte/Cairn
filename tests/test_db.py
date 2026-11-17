from sqlalchemy import select

from apps.api.db.models.user import User


async def test_user_roundtrip(db_session):
    user = User(email="a@b.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()
    assert user.id is not None
    result = await db_session.execute(select(User).where(User.email == "a@b.com"))
    fetched = result.scalar_one()
    assert fetched.id == user.id
