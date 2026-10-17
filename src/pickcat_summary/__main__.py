import asyncio
import os
import sys
from pprint import pprint
from queue import Queue

import dotenv

from pickcat_summary import Account


async def main():
    dotenv.load_dotenv()
    username = os.getenv("PICKCAT_USERNAME")
    password = os.getenv("PICKCAT_PASSWORD")
    topic_queue: Queue[str] = Queue(maxsize=200)
    if username is None or password is None:
        print("未提供Pickcat账号密码")
        sys.exit(-1)
    account = await Account.login(username, password)

    metioneds = await account.get_metioned()
    tids = [item["details"]["topic"]["id"] for item in metioneds["items"]]
    pprint(tids)


if __name__ == "__main__":
    asyncio.run(main())
