import asyncio
import os
import sys

import dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from pickcat_summary import Account, PostDetial, Processed, TopicDetial


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


async def get_topic_details(acc: Account, id: str) -> TopicDetial:
    topic_detail = await acc.get_details(id)

    # 获取回复
    post_list: list[PostDetial] = []
    cursor: str | None = None

    while True:
        if cursor is None:
            res = (await acc.client.get(f"/api/v1/topics/{id}/posts")).json()

            for item in res["items"]:
                if item["deleted"]:  # 特判一下已删除用户
                    continue
                post_list.append(
                    PostDetial(
                        author_name=item["author"]["username"],
                        content=item["cookedHtml"],
                    )
                )
            if res["pageInfo"]["hasNextPage"]:
                cursor = res["pageInfo"]["nextCursor"]
            else:
                break
        else:
            res = (
                await acc.client.get(
                    f"/api/v1/topics/{id}/posts", params={"cursor": cursor}
                )
            ).json()
            for item in res["items"]:
                post_list.append(
                    PostDetial(
                        author_name=item["author"]["username"],
                        content=item["cookedHtml"],
                    )
                )
            if res["pageInfo"]["hasNextPage"]:
                cursor = res["pageInfo"]["nextCursor"]
            else:
                break

    # 组装

    return TopicDetial(
        author_name=topic_detail["author"]["username"],
        content=topic_detail["firstPost"]["cookedHtml"],
        title=topic_detail["title"],
        posts=post_list,
    )


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
        await get_topic_details(account, "01a0eb91-5d11-7fb0-b998-179add93620f")
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
