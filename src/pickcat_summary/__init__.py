from typing import Any

from httpx import AsyncClient


class Account:
    client: AsyncClient

    def __init__(self, client: AsyncClient):
        self.client = client

    async def login(username: str, password: str) -> Account:
        '''登录'''
        # 登录
        client = AsyncClient(base_url="https://cdsq.dao3.fun")
        (
            await client.post(
                "/api/v1/session", json={"username": username, "password": password}
            )
        )
        return Account(client)

    async def get_metioned(self):
        '''获取At'''
        return (
            await self.client.get("/api/v1/notifications?type=USER_MENTIONED&limit=20")
        ).json()

    async def get_details(self, id: str) -> Any:
        '''获取帖子信息'''
        return (await self.client.get(f"/api/v1/topics/{id}")).json()

    async def get_posts(self,id:str)->Any:
        '''获取回复'''
        return (await self.client.get(f"/api/v1/topics/{id}/posts")).json()


