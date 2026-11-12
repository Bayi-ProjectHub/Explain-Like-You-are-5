"""pytest 公共配置：集成测试默认跳过，避免每次跑测试都下载模型。"""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("ELY5_RUN_INTEGRATION") == "1":
        return
    skip_integration = pytest.mark.skip(reason="集成测试需真实模型与网络，设置 ELY5_RUN_INTEGRATION=1 才运行")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
