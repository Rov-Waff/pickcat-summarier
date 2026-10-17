import asyncio
import os
import sys

import dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from pickcat_summary import Account, Processed


async def refresh_queue(acc: Account, sess: AsyncSession):

    metioneds = await acc.get_metioned()
    tids = [item["details"]["topic"]["id"] for item in metioneds["items"]]
    for i in tids:
        stmt = select(Processed).where(Processed.id == i)
        model = (await sess.exec(stmt)).first()
        if model is None:
            model = Processed(id=i, is_proc=False)
            sess.add(model)
            await sess.commit()


async def get_topic_details(): ...


async def main():
    dotenv.load_dotenv()
    username = os.getenv("PICKCAT_USERNAME")
    password = os.getenv("PICKCAT_PASSWORD")
    db_url = os.getenv("DB_URL")

    if db_url is None:
        sys.exit(-1)
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    sess = AsyncSession(engine)
    if username is None or password is None:
        print("未提供Pickcat账号密码")
        sys.exit(-1)
    account = await Account.login(username, password)

    while True:
        await refresh_queue(account, sess)
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
