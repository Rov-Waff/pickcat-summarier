import asyncio
import os
import sys
from pprint import pprint

import dotenv
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from pickcat_summary import Account, PostDetial, Processed, TopicDetial

SYS_PROMPT = """
你是一个严谨、客观的论坛帖子总结器。根据提供的主题标题、正文和回复，生成简体中文总结。

准确概括主题讨论的问题、发帖者的主要观点或诉求，以及回复中的重要信息、建议和不同意见。区分事实、观点与推测；不得编造原文没有的信息。存在分歧时，分别说明各方观点，不要将其写成共识。忽略寒暄、重复和无关内容，保留重要细节与结论。

用户输入将会是一个帖子的标题 内容 和全部回复
"""


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


async def proc(model: ChatOpenAI, topic: TopicDetial):
    prompt = ""
    prompt += (
        f"标题:{topic.title} \n 作者:{topic.author_name} \n 内容:{topic.content}\n"
    )
    prompt += "====回复====\n"
    for post in topic.posts:
        prompt += f"作者: {post.author_name} \n 内容:{post.content} \n ======="
    resp = await model.ainvoke(
        [{"role": "system", "content": SYS_PROMPT}, {"role": "user", "content": prompt}]
    )
    pprint(resp.content)


async def main():
    dotenv.load_dotenv()
    username = os.getenv("PICKCAT_USERNAME")
    password = os.getenv("PICKCAT_PASSWORD")
    db_url = os.getenv("DB_URL")
    openai_base_url = os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")

    if db_url is None:
        print("未提供DB_URL")
        sys.exit(-1)
    if openai_base_url is None or api_key is None or model is None:
        print("提供OPENAI_")
        sys.exit(-1)

    model = ChatOpenAI(base_url=openai_base_url, api_key=api_key, model=model)

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
        # 拿一个帖子Id
        id_stmt = select(Processed).where(Processed.is_proc == False).limit(1)
        id = (await sess.exec(id_stmt)).first()
        if id is None:
            await asyncio.sleep(10)
            continue

        detail = await get_topic_details(account, id.id)
        await proc(model, detail)
        id.is_proc = True
        sess.add(id)
        await sess.commit()
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
