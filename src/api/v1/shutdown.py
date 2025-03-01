import asyncio

from fastapi import APIRouter, HTTPException
from typing import Optional, Union
import logging

router = APIRouter()
logger = logging.getLogger(__name__)
shutdown_event: Union[asyncio.Event, None] = None  # 显式类型声明


@router.post("/safe_shutdown")
async def shutdown(api_key: Optional[str] = None):
    """
    安全关闭系统（需要提供正确的api_key）
    """
    # 验证API Key（示例使用"safe_exit"，正式环境应配置在settings）
    if api_key != "asd001122":
        raise HTTPException(status_code=403, detail="Invalid API key")

    if shutdown_event and not shutdown_event.is_set():
        shutdown_event.set()
        logger.warning("🛑 接收到API关闭请求，准备安全关闭系统...")
        return {"status": "shutdown_initiated"}

    return {"status": "already_shutting_down"}