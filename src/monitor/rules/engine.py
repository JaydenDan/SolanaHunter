import logging
from datetime import datetime

import discord

from config import settings
from src.notifier.discord.bot import DiscordBot
from src.utils import common_util


async def notify_process(tweets, cas_set, token_list, remaining_ca):
    for t in tweets:
        # 获取文本中的CA内容，一般只有一个
        tcas = common_util.get_ca_in_tweet(t['text'])
        for tca in tcas:
            logging.info(f'🔍️ 当前搜索到的推特帖子内容为【{t["text"]}】')
            if tca in cas_set:
                # 根据mint在token_list中查找token完整信息
                matched_item = next(
                    (item for item in token_list
                     if item.get("mint") == tca),
                    None  # 找不到时返回 None
                )

                if matched_item is None:
                    logging.warning(
                        f'⚠️ 未找到匹配的 token，CA: {tca}，可能是一个CA有多个推文，在前一个推文触发时已将该CA移出列表。')
                    continue  # 跳过或执行其他逻辑
                data = matched_item['token']
                logging.info(f'CA反搜索到的数据【{data}】')
                if data:
                    context = {
                        # 交易签名（唯一标识）
                        "signature": data["signature"],
                        # 代币合约地址
                        "mint": data["mint"],
                        # 交易者公钥
                        "traderPublicKey": data["traderPublicKey"],
                        # 交易类型（create/swap等）
                        "txType": data["txType"],
                        # 初始购买金额（SOL）
                        "initialBuy": data["initialBuy"],
                        # 当前交易SOL金额
                        "solAmount": data["solAmount"],
                        # 绑定曲线公钥
                        "bondingCurveKey": data["bondingCurveKey"],
                        # 绑定曲线中的代币总量
                        "vTokensInBondingCurve": data["vTokensInBondingCurve"],
                        # 绑定曲线中的SOL总量
                        "vSolInBondingCurve": data["vSolInBondingCurve"],
                        # 市值（SOL计价）
                        "marketCapSol": data["marketCapSol"],
                        # 代币名称
                        "name": data["name"],
                        # 代币符号
                        "symbol": data["symbol"],
                        # 代币元数据URI
                        "uri": data["uri"],
                        # 所属交易池
                        "pool": data["pool"],
                        # 社交媒体数据（异步获取）
                        "social": t
                    }
                    # 处理搜索到帖子的CA
                    # 如果满足规则通知了，就删除该CA，否则继续搜索下一条推文
                    await _start_notify(context)
                    if tca in remaining_ca:
                        remaining_ca.remove(tca)
                        # 删除已处理的token信息
                        token_list = [item for item in token_list if item.get("mint") != tca]
            else:
                logging.warning(f"⚠️ 当前推特中的CA【{tca}】不在CA监控名单中，请检查程序逻辑！")
        return remaining_ca, token_list


async def _start_notify(context):
    """代币通知处理流水线"""
    try:
        logging.info(f'🏃 开始处理代币通知：【{context["mint"]}】, Token_name:【{context["name"]}】, Token_symbol:【{context["symbol"]}】')
        # Discord
        bot = DiscordBot()
        embed = _create_embed(context)

        # 判断是否创始人发币
        if _founder_judge(context):
            logging.info(f"🔥 检测到创始人发型代币，准备通知： CA【{context['mint']}】, Token_name:【{context['name']}】, Token_symbol:【{context['symbol']}】")
            await bot.send_message(channel_id=settings.DISCORD['channel']['founder_twitter'], embed=embed)
        else:
            followers_count = context['social']['user']['followers_count']
            if 0 <= followers_count < 1000:
                logging.info(f"🔥 当前代币发推账户粉丝数 < 一千，准备通知： CA【{context['mint']}】, Token_name:【{context['name']}】, Token_symbol:【{context['symbol']}】")
                await bot.send_message(channel_id=settings.DISCORD['channel']['all_twitter'], embed=embed)

            elif 1000 <= followers_count < 3000:
                logging.info(f"🔥 当前代币发推账户粉丝数 > 一千，准备通知： CA【{context['mint']}】, Token_name:【{context['name']}】, Token_symbol:【{context['symbol']}】")
                await bot.send_message(channel_id=settings.DISCORD['channel']['1000~3000_fans'], embed=embed)

            elif 3000 <= followers_count < 5000:
                logging.info(f"🔥 当前代币发推账户粉丝数 > 三千，准备通知：【{context['mint']}】, Token_name:【{context['name']}】, Token_symbol:【{context['symbol']}】")
                await bot.send_message(channel_id=settings.DISCORD['channel']['3000~5000_fans'], embed=embed)

            elif 5000 <= followers_count < 10000:
                logging.info(f"🔥 当前代币发推账户粉丝数 > 五千，准备通知：【{context['mint']}】, Token_name:【{context['name']}】, Token_symbol:【{context['symbol']}】")

                await bot.send_message(channel_id=settings.DISCORD['channel']['5000~10000_fans'], embed=embed)
            elif 10000 <= followers_count:
                logging.info(f"🔥 当前代币发推账户粉丝数 > 一万，准备通知：【{context['mint']}】, Token_name:【{context['name']}】, Token_symbol:【{context['symbol']}】")
                await bot.send_message(channel_id=settings.DISCORD['channel']['10000+_fans'], embed=embed)

    except Exception as e:
        logging.error(f"处理流水线异常: {context['address']} | {str(e)}")


def _create_embed(context: dict) -> discord.Embed:
    """生成交易信息Embed（保持你的原始颜色逻辑）"""
    embed = discord.Embed(
        title=f"📊 {context['symbol']} 交易动态 | {context['txType'].upper()}",
        color=discord.Color.green() if context["txType"] == "create" else discord.Color.red(),
        description=f"[🔍 点击直达OKX](https://www.okx.com/zh-hans/web3/detail/501/{context['mint']})\n"
                    f"```fix\n{context['mint']}\n```\n",
        timestamp=datetime.now()  # 自动添加时间戳
    )

    embed.set_author(
        name="新币通知",
        icon_url="https://pump.fun/_next/image?url=%2Flogo.png&w=64&q=75"
    )

    embed.add_field(name="", value="", inline=False)
    embed.add_field(
        name="\n💰 资金流动",
        value=f"初始：`{context['initialBuy']:.2f} SOL`\n当前：`{context['solAmount']:.2f} SOL`",
        inline=True
    )
    embed.add_field(
        name="\n📈 池子状态",
        value=f"市值：`{context['marketCapSol']:.2f} SOL`\n流通：{context['vTokensInBondingCurve']}",
        inline=True
    )

    # 用户信息
    social = context["social"]

    # 互动数据
    metrics = [
        f"❤️ {social['metrics']['likes']}",
        f"🔄 {social['metrics']['retweets']}",
        f"💬 {social['metrics']['replies']}",
        f"👁️ {social['metrics']['view_count']}"
    ]

    interactive = " | ".join(metrics)

    embed.add_field(name="", value="", inline=False)
    embed.add_field(
        name="\n🐦 关联推文",
        value=f"[🔍 点击直达推文🔗](https://x.com/{social['user']['screen_name']}/status/{social['id']})\n"
              f"{social['text'][:60]}...\n",
        inline=False,
    )

    embed.add_field(name="", value="", inline=True)
    embed.add_field(
        name="",
        value=f"📊 {interactive}",
        inline=True
    )

    is_blue_verified = "✅" if social['user']['is_blue_verified'] else "❌"
    embed.add_field(
        name="👤 发布者",
        value=f"用户名称：[@{social['user']['name']}](https://x.com/{social['user']['screen_name']})\n"
              f"Description：{social['user']['description']}\n"
              f"蓝标认证：{is_blue_verified}",
        inline=False
    )

    out_link = " 🈚️ "
    if social['user']['display_url']:
        out_link = f"[{social['user']['display_url']}]({social['user']['expanded_url']})"

    metrics_account = [
        f"🌐 外站 {out_link}",
        f"👀 关注 {social['user']['following_count']}",
        f"👥 粉丝 {social['user']['followers_count']}",
        f"🌟 点赞 {social['user']['favourites_count']}"
    ]

    interactive_account = " | ".join(metrics_account)
    embed.add_field(
        name="",
        value=f"{interactive_account}",
        inline=True
    )

    # 时间戳
    embed.add_field(name="", value="", inline=False)
    embed.set_footer(
        text=f"帖子发布于 {social['created_at'].strftime('%Y-%m-%d %H:%M:%S UTC+8')}",
        icon_url="https://pbs.twimg.com/profile_images/1683899100922511378/5lY42eHs_bigger.jpg"
    )

    return embed


def _founder_judge(context):
    """创始人判断 + 带官网"""
    if ((context['name'] in context['social']['user']['name'] or context['name'] in context['social']['user']['screen_name'] or context['name'] in context['social']['user']['description'])
            and context['social']['user']['display_url'] and 't.me' not in context['social']['user']['expanded_url']):
        logging.info(f"🏆 匹配成功，当前CA的名称 {context['name']} 在 {context['social']['user']['screen_name']} 找到")
        return True
    if ((context['symbol'] in context['social']['user']['name'] or context['symbol'] in context['social']['user']['screen_name'] or context['symbol'] in context['social']['user']['description'])
            and context['social']['user']['display_url'] and 't.me' not in context['social']['user']['expanded_url']):
        logging.info(f"🏆 匹配成功，当前CA的符号 {context['symbol']} 在 {context['social']['user']['screen_name']} 找到")
        return True
    logging.info(f"🚫 匹配失败，当前CA的名称 {context['name']} 发帖人 {context['social']['user']['screen_name']} 不是项目方")
    return False
