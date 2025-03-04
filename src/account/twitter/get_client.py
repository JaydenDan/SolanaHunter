import asyncio
import logging
import os
from typing import Any, Coroutine

import httpcore
import httpx
from socksio import ProtocolError
from twikit.client.client import Client
from twikit import AccountSuspended


async def check_proxy(client: Client, proxy_ip, socks_url):
    """验证代理是否生效（带ProtocolError重试机制）"""
    max_retries = 3
    retry_delay = 1  # 重试间隔秒数

    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.http.get('https://api.ip.sb/ip')
            current_ip = resp.text.strip()

            # 保持原有的IP验证逻辑
            if current_ip not in socks_url:
                logging.error(f"❌ 代理未生效，当前IP: {current_ip}，期望代理IP：{proxy_ip}")
                return False
            return True

        except ProtocolError as pe:  # 捕获特定协议错误
            if attempt < max_retries:
                logging.warning(f"⚠️ 代理协议错误，正在重试 ({attempt}/{max_retries})")
                await asyncio.sleep(retry_delay * attempt)
            else:
                logging.error("❌ 连续三次代理协议错误，跳过IP检查")
                return False

        except Exception as e:  # 其他异常立即抛出
            logging.error(f"❌ 代理验证失败：{str(e)}", exc_info=True)
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
            proxy: str,  # 格式 "ip:port:user:pass"
            max_retries: int = 3,
            retry_delay: int = 5
    ) -> Client | None:
        """直接返回初始化完成的Client对象（可await调用）"""
        # 解析代理信息
        for attempt in range(1, max_retries + 1):
            try:
                proxy_info = proxy.split(':')
                if len(proxy_info) != 4:
                    raise ValueError("代理格式错误，正确格式：ip:port:username:password")

                # 构建代理URL
                socks_url = f'socks5://{proxy_info[2]}:{proxy_info[3]}@{proxy_info[0]}:{proxy_info[1]}'
                client = Client(language='en-US', proxy=socks_url)
                
                # 检查代理IP应用是否正确
                proxy_valid = await check_proxy(client, proxy_info[0], socks_url)
                if not proxy_valid:
                    logging.error(f"❌ 获取客户端失败：代理验证未通过 ({email})")
                    return None
                    
                cookie_file = self._get_cookie_path(email)
                
                # 存在Cookie时加载
                if os.path.exists(cookie_file):
                    client.load_cookies(cookie_file)
                    try:
                        # 验证Cookie有效性
                        await client.get_user_by_screen_name(username)
                    except Exception:
                        logging.warning(f'⚠️ Cookie失效，执行重新登录 ({email})')
                        if os.path.exists(cookie_file):
                            os.remove(cookie_file)

                        await client.login(
                            auth_info_1=username,
                            auth_info_2=email,
                            password=password
                        )
                        logging.info(f'✅ 登录成功 ({email})')
                else:
                    await client.login(
                        auth_info_1=username,
                        auth_info_2=email,
                        password=password
                    )
                    logging.info(f'✅ 登录成功 ({email})')
                
                # 保存Cookie并返回初始化完成的客户端
                client.save_cookies(cookie_file)
                return client

            # 处理httpcore和httpx的连接错误
            except (ProtocolError, httpx.ConnectError, httpcore.ConnectError) as e:
                error_type = "代理协议" if isinstance(e, ProtocolError) else "网络连接"
                if attempt < max_retries:
                    delay = retry_delay * attempt
                    logging.warning(f"🌐 获取客户端失败：{error_type}异常 ({email})，{attempt}/{max_retries} 次重试，等待 {delay} 秒")
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise AccountSuspended(f"❌ 获取客户端失败：{error_type}异常 ({email})，已重试 {max_retries} 次") from e
            except Exception as e:
                if "AttributeError: 'ClientTransaction' object has no attribute 'key'" in str(e):
                    logging.warning(f'🚫 获取客户端失败：账号【{email}】疑似封禁-AttributeError，需要更换账号')
                    raise AccountSuspended("账号疑似封禁") from e
                if "Forbidden" in str(e) or "403" in str(e):
                    logging.warning(f'🚫 获取客户端失败：账号【{email}】账号被禁止访问-403，需要更换账号')
                    raise AccountSuspended("账号被禁止访问") from e
                raise Exception(f"❌ 获取客户端失败：未知错误 ({email}): {str(e)}") from e

