# src/api/v1/shutdown.py
from fastapi import APIRouter, Query, HTTPException, Request, status
from typing import Optional
import logging
from config import settings

router = APIRouter(tags=["System Control"])
logger = logging.getLogger("API_")


@router.get("/safe-shutdown")
async def trigger_safe_shutdown(
    request: Request,  # 新增 Request 对象
    api_key: Optional[str] = Query(None, alias="key")
):
    # 验证 API 密钥
    if api_key != settings.API['key']:
        logger.warning(f"非法关闭尝试，使用的密钥: {api_key}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )

    # 从应用状态获取 monitor 实例
    monitor = request.app.state.monitor

    try:
        # 直接调用 core 的 stop 方法
        await monitor.stop()
        return {
            "status": "shutdown_success",
            "message": "✅ 系统已安全关闭"
        }
    except Exception as e:
        logger.error(f"关闭失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
