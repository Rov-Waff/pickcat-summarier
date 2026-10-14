"""使用公共 fixtures 的异步测试示例 (auto 模式, 无需 asyncio marker)。"""

import asyncio

import httpx


async def test_async_auto_mode():
    """验证 async def 测试可直接运行。"""
    await asyncio.sleep(0)
    assert True


async def test_client_is_mocked(client: httpx.AsyncClient):
    """公共 client fixture 走 mock transport, 不发起真实网络请求。"""
    resp = await client.get("/api/v1/notifications", params={"type": "USER_MENTIONED"})
    assert resp.status_code == 200
    assert resp.json() == {"notifications": []}


async def test_account_get_details(account):
    data = await account.get_details("123")
    assert data == {"id": "123", "title": "mock topic"}


async def test_account_get_posts(account):
    data = await account.get_posts("123")
    assert data == {"topic_id": "123", "posts": []}
