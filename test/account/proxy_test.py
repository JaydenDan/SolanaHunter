import asyncio
import logging
import time

from twikit import Client

# 配置日志显示级别
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


async def main():
    try:
        # 配置代理 (格式: socks5://用户名:密码@IP:端口)
        proxy_url = "socks5://lfxwowly:2ve2stnj09xk@45.56.176.128:7706"

        # 初始化客户端
        client = Client(
            language='en-US',
            proxy=proxy_url,
        )
        logging.info("✅ 客户端初始化成功")

        # 先验证代理是否生效
        await check_proxy(client)

        return

        # 执行登录
        await client.login(
            auth_info_1='ellagevondyan',  # 用户名/手机号/邮箱
            auth_info_2='ella.gevondyan@twitter.ru',  # 当auth_info_1是用户名时这里填邮箱
            password='Asd001122@djt'
        )
        logging.info("✅ 登录成功")

        # 获取用户信息
        user = await client.get_user_by_screen_name('elonmusk')
        print(f"用户信息: {user}")

    except Exception as e:
        logging.error(f"❌ 操作失败: {str(e)}")
        raise


async def check_proxy(client: Client):
    """验证代理是否生效"""
    try:
        resp = await client.http.get('https://api.ip.sb/ip')
        current_ip = resp.text.strip()
        logging.info(f"🔍 当前出口 IP: {current_ip}")

        # 验证是否为代理IP (根据实际情况修改预期IP)
        if current_ip != "45.56.176.128":
            raise ValueError(f"代理未生效，当前IP: {current_ip}")
        logging.info("✅ 代理验证通过")

    except Exception as e:
        logging.error("❌ 代理验证失败")
        raise


if __name__ == '__main__':
    # 运行异步主函数
    while 1 == 1:
        asyncio.run(main())
        time.sleep(1)