"""pytest 全局配置与公共 fixtures。

- dotenv: 由 pytest-dotenv 在启动时加载 pyproject.toml 中 env_files 声明的文件;
  这里再兜底加载一次项目根目录的 .env, 保证直接导入本模块时环境变量也可用。
- 异步: pyproject.toml 中 asyncio_mode = "auto", async fixture 直接写即可。
"""

import os
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

from pickcat_summary import Account

# 兜底加载项目根目录 .env (不覆盖已存在的环境变量)
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)


@pytest.fixture
def mock_transport() -> httpx.MockTransport:
    """拦截所有 HTTP 请求的 mock transport, 测试不依赖真实网络。

    按需在 handler 中扩展各 API 路径的假响应。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/session":
            return httpx.Response(200, json={"token": "fake-token"})
        if path == "/api/v1/notifications":
            return httpx.Response(200, json={"notifications": []})
        if path.startswith("/api/v1/topics/"):
            if path.endswith("/posts"):
                topic_id = path.split("/")[4]
                return httpx.Response(200, json={"topic_id": topic_id, "posts": []})
            topic_id = path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"id": topic_id, "title": "mock topic"})
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.fixture
async def client(mock_transport: httpx.MockTransport):
    """公共 AsyncClient fixture, base_url 优先取环境变量 PICKCAT_BASE_URL。"""
    base_url = os.environ.get("PICKCAT_BASE_URL", "https://cdsq.dao3.fun")
    async with httpx.AsyncClient(
        base_url=base_url, transport=mock_transport
    ) as client:
        yield client


@pytest.fixture
def account(client: httpx.AsyncClient) -> Account:
    """已注入 mock client 的 Account 实例。"""
    return Account(client)
