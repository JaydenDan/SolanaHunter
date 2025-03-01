import json
import logging
from typing import Optional, Dict, Union, List
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_dingtalk.robot_1_0.client import Client as RobotClient
from alibabacloud_dingtalk.robot_1_0 import models as robot_models
from alibabacloud_tea_util import models as util_models
from .token_manager import DingTalkTokenManager
from config import settings


def _build_message(
        content: Union[str, Dict],
        msg_type: str,
        at_users: List[str],
        at_all: bool
) -> tuple:
    """构建消息体"""
    at_info = {"atUserIds": at_users or [], "isAtAll": at_all}

    if msg_type == "text":
        return (
            "sampleText",
            {
                "content": content if isinstance(content, str) else content["content"],
                **at_info
            }
        )
    elif msg_type == "markdown":
        return (
            "markdown",
            {
                "title": content["title"],
                "text": content["text"],
                **at_info
            }
        )
    else:
        raise ValueError(f"不支持的的消息类型: {msg_type}")


class DingTalkClient:
    """钉钉机器人客户端"""

    def __init__(self, app_key: str, app_secret: str):
        self.token_manager = DingTalkTokenManager(app_key, app_secret)

        # 初始化OpenAPI配置
        self.config = open_api_models.Config()
        self.config.protocol = "https"
        self.config.region_id = "central"

    async def _get_headers(self) -> robot_models.OrgGroupSendHeaders:
        """生成请求头"""
        org_group_send_headers = robot_models.OrgGroupSendHeaders()
        org_group_send_headers.x_acs_dingtalk_access_token = await self.token_manager.get_token()
        return org_group_send_headers

    async def send_message(
            self,
            content: str,
            msg_type: str = "text",
            at_users: Optional[List[str]] = None,
            at_all: bool = False
    ) -> bool:
        """
        发送群消息
        :param content: 消息内容（文本或Markdown字典）
        :param msg_type: 消息类型 text/markdown
        :param at_users: 被@的用户ID列表
        :param at_all: 是否@所有人
        """
        client = RobotClient(self.config)
        # 构建消息参数
        # msg_key, msg_param = _build_message(content, msg_type, at_users, at_all)

        req = robot_models.OrgGroupSendRequest(
            msg_key=msg_type,
            msg_param=json.dumps(content),
            token=settings.DINGTALK['token']
        )
        try:
            client.org_group_send_with_options(
                req,
                headers= await self._get_headers(),
                runtime=util_models.RuntimeOptions()
            )
            return True
        except Exception as e:
            logging.error(f"❌ 消息发送失败: {e}")
            return False

