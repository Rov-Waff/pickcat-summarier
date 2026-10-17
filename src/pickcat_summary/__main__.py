import asyncio
import logging
import os
import sys

import dotenv
from langchain_core.messages.ai import AIMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from pickcat_summary import Account, PostDetial, Processed, TopicDetial

logger = logging.getLogger(__name__)

SYS_PROMPT = """
你是一个严谨、客观的论坛帖子总结器。根据提供的主题标题、正文和回复，生成简体中文总结。

准确概括主题讨论的问题、发帖者的主要观点或诉求，以及回复中的重要信息、建议和不同意见。区分事实、观点与推测；不得编造原文没有的信息。存在分歧时，分别说明各方观点，不要将其写成共识。忽略寒暄、重复和无关内容，保留重要细节与结论。

用户输入将会是一个帖子的标题 内容 和全部回复

输出格式为Markdown 里面不得包含任何URL链接
"""


async def refresh_queue(acc: Account, sess: AsyncSession):

    metioneds = await acc.get_metioned()
    tids = [item["details"]["topic"]["id"] for item in metioneds["items"]]
    added = 0
    for i in tids:
        stmt = select(Processed).where(Processed.id == i)
        model = (await sess.exec(stmt)).first()
        if model is None:
            model = Processed(id=i, is_proc=False)
            sess.add(model)
            added += 1
    await sess.commit()
    logger.info("队列刷新完成：获取到 %d 个主题，新增 %d 个待处理项", len(tids), added)


async def get_topic_details(acc: Account, id: str) -> TopicDetial:
    logger.info("开始获取主题详情：%s", id)
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
                logger.debug("主题 %s 回复还有下一页", id)
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
                logger.debug("主题 %s 回复还有下一页", id)
            else:
                break

    # 组装
    logger.info("主题 %s 详情获取完成，共 %d 条回复", id, len(post_list))

    return TopicDetial(
        author_name=topic_detail["author"]["username"],
        content=topic_detail["firstPost"]["cookedHtml"],
        title=topic_detail["title"],
        posts=post_list,
    )


async def proc(model: ChatOpenAI, topic: TopicDetial) -> AIMessage:
    logger.info("开始总结主题：%s", topic.title)
    prompt = ""
    prompt += (
        f"标题:{topic.title} \n 作者:{topic.author_name} \n 内容:{topic.content}\n"
    )
    prompt += "====回复====\n"
    for post in topic.posts:
        prompt += f"作者: {post.author_name} \n 内容:{post.content} \n ======="
    resp: AIMessage = await model.ainvoke(
        [{"role": "system", "content": SYS_PROMPT}, {"role": "user", "content": prompt}]
    )

    logger.info("主题总结完成：%s", topic.title)
    logger.debug(resp.content)
    return resp


async def main():
    dotenv.load_dotenv()
    log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("总结任务启动")
    username = os.getenv("PICKCAT_USERNAME")
    password = os.getenv("PICKCAT_PASSWORD")
    db_url = os.getenv("DB_URL")
    openai_base_url = os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")

    if db_url is None:
        logger.error("未提供 DB_URL")
        print("未提供DB_URL")
        sys.exit(-1)
    if openai_base_url is None or api_key is None or model is None:
        logger.error("未完整提供 OpenAI 配置")
        print("提供OPENAI_")
        sys.exit(-1)

    model = ChatOpenAI(base_url=openai_base_url, api_key=api_key, model=model)

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("数据库初始化完成")
    sess = AsyncSession(engine, expire_on_commit=False)
    if username is None or password is None:
        logger.error("未提供 Pickcat 账号密码")
        print("未提供Pickcat账号密码")
        sys.exit(-1)
    account = await Account.login(username, password)
    logger.info("Pickcat 登录成功")

    while True:
        await refresh_queue(account, sess)
        # 拿一个帖子Id
        id_stmt = select(Processed).where(Processed.is_proc == False).limit(1)
        proc_item = (await sess.exec(id_stmt)).first()
        if proc_item is None:
            logger.debug("当前没有待处理主题，10 秒后重试")
            await asyncio.sleep(10)
            continue

        topic_id = proc_item.id  # 提前缓存，避免 commit 后属性过期触发同步懒加载
        try:
            logger.info("开始处理主题：%s", topic_id)
            detail = await get_topic_details(account, topic_id)
            llm_resp = await proc(model, detail)

            # 先发帖，成功后再标记为已处理；发帖失败时 is_proc 保持 False，下一轮会重试
            resp = await account.client.post(
                "/api/v1/posts",
                json={
                    "topicId": topic_id,
                    "markdown": llm_resp.content,
                    "replyToPostNumber": 1,
                },
            )
            resp.raise_for_status()

            proc_item.is_proc = True
            sess.add(proc_item)
            await sess.commit()
            logger.info("主题处理完成：%s", topic_id)
        except Exception:
            logger.exception("处理主题失败：%s", topic_id)
            await sess.rollback()
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
