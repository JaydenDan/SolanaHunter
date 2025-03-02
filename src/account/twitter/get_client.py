import asyncio
import logging
import os

from socksio import ProtocolError
from twikit.client.client import Client


async def check_proxy(client: Client, proxy_ip, socks_url):
    """验证代理是否生效（带ProtocolError重试机制）"""
    max_retries = 3
    retry_delay = 1  # 重试间隔秒数

    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.http.get('https://api.ip.sb/ip')
            current_ip = resp.text.strip()
            logging.info(f"🔍 当前出口 IP: {current_ip}")

            # 保持原有的IP验证逻辑
            if current_ip not in socks_url:
                logging.error(f"❌ 代理未生效，当前IP: {current_ip}，期望代理IP：{proxy_ip}")
                return False

            logging.info(f"✅ 代理验证通过：{current_ip} = {proxy_ip}")
            return True

        except ProtocolError as pe:  # 捕获特定协议错误
            if attempt < max_retries:
                logging.warning(f"⚠️ 代理协议错误，正在重试 ({attempt}/{max_retries})")
                await asyncio.sleep(retry_delay * attempt)
            else:
                logging.error("❌ 连续三次代理协议错误，跳过IP检查")
                return False

        except Exception as e:  # 其他异常立即抛出
            logging.error(f"❌ 非协议错误导致验证失败：【{e}】", exc_info=True)
            return False
    return False


class TwitterClientManager:

    def __init__(self, cookie_path: str = 'cookies') -> None:
        self.client = Client()
        self.cookie_path = cookie_path
        os.makedirs(self.cookie_path, exist_ok=True)

    def _get_cookie_path(self, email: str) -> str:
        """生成标准化Cookie文件路径"""
        return os.path.join(self.cookie_path, f'cookie_{email.replace("@", "_")}.json')

    async def get_client(
            self,
            email: str,
            username: str,
            password: str,
            proxy: str  # 格式 "ip:port:user:pass"
    ) -> Client:
        """直接返回初始化完成的Client对象（可await调用）"""
        # 解析代理信息
        proxy_info = proxy.split(':')
        if len(proxy_info) != 4:
            raise ValueError("代理格式错误，正确格式：ip:port:username:password")

        # 构建代理URL
        socks_url = f'socks5://{proxy_info[2]}:{proxy_info[3]}@{proxy_info[0]}:{proxy_info[1]}'
        client = Client(language='en-US', proxy=socks_url)
        # 检查代理IP应用是否正确
        await check_proxy(client, proxy_info[0], socks_url)
        cookie_file = self._get_cookie_path(email)
        try:
            # 存在Cookie时加载
            if os.path.exists(cookie_file):
                logging.info(f'📄 加载本地Cookie: {cookie_file}')
                client.load_cookies(cookie_file)

                try:
                    # 验证Cookie有效性
                    await client.get_user_by_screen_name(username)
                    logging.info('✅ Cookie有效')
                except Exception as e:
                    logging.warning(f'⚠️ Cookie失效: {str(e)}，执行重新登录')
                    os.remove(cookie_file)
                    await client.login(
                        auth_info_1=username,
                        auth_info_2=email,
                        password=password
                    )
                    logging.info(f'✅ Cookie失效账户登录成功')
            else:
                # 全新登录
                logging.info('🆕 无本地Cookie，执行全新登录')
                await client.login(
                    auth_info_1=username,
                    auth_info_2=email,
                    password=password
                )
                logging.info(f'✅ 无Cookie账户登录成功')
            # 返回初始化完成的客户端
            return client
        finally:
            # 无论如何都保存最新Cookie
            client.save_cookies(cookie_file)
            logging.info(f'💾 保存Cookie至: {cookie_file}')
            return client

