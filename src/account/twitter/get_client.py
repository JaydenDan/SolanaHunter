import asyncio
import logging
import os

import httpcore
import httpx
from socksio import ProtocolError
from twikit.client.client import Client

from config.config_loader import get_config


async def check_proxy(client: Client, proxy_ip, socks_url):
    """验证代理是否生效(带ProtocolError重试机制)"""
    max_retries = 3
    retry_delay = 1  # 重试间隔秒数

    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.http.get('https://api.ip.sb/ip')
            current_ip = resp.text.strip()

            # 保持原有的IP验证逻辑
            if current_ip not in socks_url:
                logging.error(f"❌ 代理未生效, 当前IP: {current_ip}, 期望代理IP: {proxy_ip}")
                return False
            return True

        except ProtocolError as pe:  # 捕获特定协议错误
            if attempt < max_retries:
                logging.warning(f"⚠️ 代理协议错误, 正在重试 ({attempt}/{max_retries})")
                await asyncio.sleep(retry_delay * attempt)
            else:
                logging.error("❌ 连续三次代理协议错误, 跳过IP检查")
                return False

        except Exception as e:  # 其他异常立即抛出
            logging.error(f"❌ 代理验证失败: {str(e)}", exc_info=True)
            return False
    return False


class TwitterClientManager:

    def __init__(self) -> None:
        self.cookie_path = get_config('TWITTER.cookies_file_path')
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
            totp_secret: str,
            max_retries: int = 3
    ) -> Client | None:
        try:
            client = Client(language='en-US')

            # 解析代理信息
            if proxy:
                proxy_info = proxy.split(':')
                if len(proxy_info) == 4:
                    logging.info(f"Twitter Account{email}启动代理")
                    # 构建代理URL
                    socks_url = f'socks5://{proxy_info[2]}:{proxy_info[3]}@{proxy_info[0]}:{proxy_info[1]}'
                    # 构建http代理（本地代理）
                    http_url = f'http://localhost:7890'
                    client = Client(language='en-US', proxy=socks_url)
                    # 检查代理IP应用是否正确
                    # proxy_valid = await check_proxy(client, proxy_info[0], socks_url)

            cookie_file = self._get_cookie_path(email)

            # 尝试加载和验证Cookie
            need_login = True
            if os.path.exists(cookie_file):
                client.load_cookies(cookie_file)
                try:
                    # 验证Cookie有效性
                    await client.get_user_by_screen_name(username)
                    need_login = False
                    logging.info(f'✅ Cookie验证成功 ({email})')
                except Exception:
                    logging.warning(f'⚠️ Cookie失效, 执行重新登录 ({email})')
                    os.remove(cookie_file)
            else:
                logging.info(f"Twitter Account {email} Cookie未找到，执行登录")

            # 需要登录时执行登录流程
            if need_login:
                retry_count = 0
                while retry_count < max_retries:
                    try:
                        if totp_secret:
                            logging.info(f"Twitter Account {email} 进行 2FA 登录")
                            await client.login(
                                auth_info_1=username,
                                auth_info_2=email, 
                                password=password,
                                totp_secret=totp_secret,
                                enable_ui_metrics=False
                            )
                        else:
                            logging.info(f"Twitter Account {email} 进行普通登录")
                            await client.login(
                                auth_info_1=username,
                                auth_info_2=email, 
                                password=password,
                                enable_ui_metrics=False
                            )
                        logging.info(f'✅ 登录成功 ({email})')
                        break  # 登录成功，跳出重试循环
                    except (httpx.ConnectError, httpcore.ConnectError, ProtocolError, httpcore.ConnectTimeout, httpx.ConnectTimeout, httpx.ReadTimeout, httpcore.ReadTimeout) as e:
                        retry_count += 1
                        wait_time = retry_count
                        # 不同类型错误输出不同日志
                        if isinstance(e, (httpx.ConnectError, httpcore.ConnectError)):
                            logging.warning(f'🌐 网络连接失败({e.__class__.__name__}): {str(e)} - 重试 {retry_count}/{max_retries}, {wait_time}秒后重试')
                        elif isinstance(e, ProtocolError):
                            logging.warning(f'🌐 代理连接失败(ProtocolError): {str(e)} - 重试 {retry_count}/{max_retries}, {wait_time}秒后重试')
                        elif isinstance(e, (httpcore.ConnectTimeout, httpx.ConnectTimeout)):
                            logging.warning(f'🌐 连接超时({e.__class__.__name__}): {str(e)} - 重试 {retry_count}/{max_retries}, {wait_time}秒后重试')
                        elif isinstance(e, (httpx.ReadTimeout, httpcore.ReadTimeout)):
                            logging.warning(f'🌐 读取超时({e.__class__.__name__}): {str(e)} - 重试 {retry_count}/{max_retries}, {wait_time}秒后重试')
                        
                        if retry_count >= max_retries:
                            logging.error(f'❌ 登录失败: 网络错误重试{max_retries}次后仍然失败')
                            raise  # 重试耗尽，抛出最后一次的异常
                        
                        await asyncio.sleep(wait_time)  # 等待后重试
                        continue
                        
                    except Exception as e:
                        logging.error(f'❌ 登录失败 ({email}): {str(e)}')
                        raise

            # 保存Cookie并返回初始化完成的客户端
            client.save_cookies(cookie_file)
            return client

        except Exception as e:
            if "You'll need to wait before trying to log in again. Some blocks are removed automatically." in str(e):
                logging.warning(f'🚫 获取客户端失败：账号【{email}】暂时封锁, 需要更换账号')
                return None
            if "AttributeError: 'ClientTransaction' object has no attribute 'key'" in str(e):
                logging.warning(f'🚫 获取客户端失败：账号【{email}】疑似封禁-AttributeError, 需要更换账号')
                return None
            if "Forbidden" in str(e) or "403" in str(e):
                logging.warning(f'🚫 获取客户端失败：账号【{email}】账号被禁止访问-403, 需要更换账号')
                return None
            logging.error(f"❌ 获取客户端失败: {str(e)}", exc_info=True)
            return None
