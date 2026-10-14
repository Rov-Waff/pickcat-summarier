"""验证 dotenv 配置生效。"""

import os


def test_dotenv_loaded():
    """pyproject.toml env_files 中声明的 .env 应被自动加载进环境变量。"""
    assert os.environ.get("PICKCAT_BASE_URL") == "https://cdsq.dao3.fun"


def test_credentials_placeholder():
    """凭据类变量存在即可, 不要把真实密钥写进仓库。"""
    assert "PICKCAT_USERNAME" in os.environ
    assert "PICKCAT_PASSWORD" in os.environ
