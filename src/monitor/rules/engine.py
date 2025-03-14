import logging
from datetime import datetime

import discord

from config.config_loader import get_config
from src.notifier.discord.bot import DiscordBot
from src.utils import common_util
from solana.rpc.api import Client
from solders.pubkey import Pubkey
import time


async def notify_process_with_twitter(tweets, mint_set, token_list, remaining_mint):
    for t in tweets:
        # 获取文本中的CA内容, 一般只有一个
        tweet_mint_list = common_util.get_mint_in_tweet(t['text'])
        for tweet_mint in tweet_mint_list:
            logging.info(f'🔍️ 当前搜索到的推特帖子内容为:\n【{t["text"]}】')
            if tweet_mint in mint_set:
                # 根据mint在token_list中查找token完整信息
                matched_item = next(
                    (item for item in token_list
                     if item.get("mint") == tweet_mint),
                    None  # 找不到时返回 None
                )

                if matched_item is None:
                    logging.warning(
                        f'⚠️ 未找到匹配的 token, CA: {tweet_mint}, 可能是一个CA有多个推文, 在前一个推文触发时已将该CA移出列表。')
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
                        # 该代币采用的 Bonding Curve (弹性定价模型) 的合约地址。Bonding Curve 通过数学公式决定代币的价格。
                        "bondingCurveKey": data["bondingCurveKey"],
                        # 盘子代币存量
                        "vTokensInBondingCurve": data["vTokensInBondingCurve"],
                        # 盘子SOL存量
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
                        # 检测时间
                        "detect_time": data["detect_time"],  
                        # 社交媒体数据（异步获取）
                        "social": t
                    }
                    # 处理搜索到帖子的CA
                    # 如果满足规则通知了, 就删除该CA, 否则继续搜索下一条推文
                    await _start_notify(context)
                    if tweet_mint in remaining_mint:
                        remaining_mint.remove(tweet_mint)
                        # 删除已处理的token信息
                        token_list = [item for item in token_list if item.get("mint") != tweet_mint]
            else:
                logging.warning(f"⚠️ 当前推特中的CA【{tweet_mint}】不在CA监控名单中, 请检查程序逻辑！")
        return remaining_mint, token_list

async def notify_process_all_push(token):
    await _start_notify(token)

def get_dev_balance(dev_address):
    # 创建RPC客户端并查询余额
    solana_client = Client(get_config('BLOCKCHAIN_RPC.solana_official_rpc_url'))
    
    # 执行查询
    retry_count = 3
    dev_balance = 0
    while retry_count > 0:
        try:
            balance_response = solana_client.get_balance(Pubkey.from_string(dev_address))
            lamports = balance_response.value
            sol_balance = lamports / 1e9  # 转换为SOL
            dev_balance = round(sol_balance, 5)
            break
        except Exception as e:
            retry_count -= 1
            if retry_count == 0:
                dev_balance = 0
            time.sleep(1)  # 重试间隔1秒
    return dev_balance

async def _start_notify(context):
    """代币通知处理流水线"""
    try:
        # Discord
        bot = DiscordBot()
        dev_balance = get_dev_balance(context['traderPublicKey'])
        context['dev_balance'] = dev_balance
        embed = _create_embed(context)
        # 获取代币地址
        mint_address = context["mint"]

        if context.get("social") is not None: # 有推特判断
            # 如果dev余额>20 SOL, 则通知到20粉丝的频道
            if dev_balance > 20:
                await bot.send_message(channel_id=get_config('DISCORD.channel.dev_balance_20_twitter'), embed=embed, mint_address=mint_address)
            # 判断是否创始人发币
            if _founder_judge(context):
                logging.info(f"🔥 检测到创始人发型代币, 准备通知:  CA【{context['mint']}】, Token_name:【{context['name']}】, Token_symbol:【{context['symbol']}】")
                await bot.send_message(channel_id=get_config('DISCORD.channel.founder_twitter'), embed=embed, mint_address=mint_address)
            else:
                followers_count = context['social']['user']['followers_count']
                if 0 <= followers_count < 1000:
                    logging.info(f"🔥 当前代币发推账户粉丝数 < 一千, 准备通知:  CA【{context['mint']}】, Token_name:【{context['name']}】, Token_symbol:【{context['symbol']}】")
                    await bot.send_message(channel_id=get_config('DISCORD.channel.all_twitter'), embed=embed, mint_address=mint_address)

                elif 1000 <= followers_count < 3000:
                    logging.info(f"🔥 当前代币发推账户粉丝数 > 一千, 准备通知:  CA【{context['mint']}】, Token_name:【{context['name']}】, Token_symbol:【{context['symbol']}】")
                    await bot.send_message(channel_id=get_config('DISCORD.channel.1000~3000_fans'), embed=embed, mint_address=mint_address)

                elif 3000 <= followers_count < 5000:
                    logging.info(f"🔥 当前代币发推账户粉丝数 > 三千, 准备通知: 【{context['mint']}】, Token_name:【{context['name']}】, Token_symbol:【{context['symbol']}】")
                    await bot.send_message(channel_id=get_config('DISCORD.channel.3000~5000_fans'), embed=embed, mint_address=mint_address)

                elif 5000 <= followers_count < 10000:
                    logging.info(f"🔥 当前代币发推账户粉丝数 > 五千, 准备通知: 【{context['mint']}】, Token_name:【{context['name']}】, Token_symbol:【{context['symbol']}】")

                    await bot.send_message(channel_id=get_config('DISCORD.channel.5000~10000_fans'), embed=embed, mint_address=mint_address)
                elif 10000 <= followers_count:
                    logging.info(f"🔥 当前代币发推账户粉丝数 > 一万, 准备通知: 【{context['mint']}】, Token_name:【{context['name']}】, Token_symbol:【{context['symbol']}】")
                    await bot.send_message(channel_id=get_config('DISCORD.channel.10000+_fans'), embed=embed, mint_address=mint_address)
        else: #全推判断
            # 判断开发者钱包余额是否大于100 SOL
            if dev_balance > 10:
                logging.info(f"🔥 当前代币开发者钱包余额 > 10 SOL, 准备通知: 【{context['mint']}】, Token_name:【{context['name']}】, Token_symbol:【{context['symbol']}】")
                await bot.send_message(channel_id=get_config('DISCORD.channel.dev_balance_50'), embed=embed, mint_address=mint_address)
            if float(context.get('solAmount', 1)) == 0 and float(context.get('initialBuy', 1)) > 0:
                logging.info(f"🔥 当前代币上线就发射, 准备通知: 【{context['mint']}】, Token_name:【{context['name']}】, Token_symbol:【{context['symbol']}】")
                await bot.send_message(channel_id=get_config('DISCORD.channel.start_as_launch_without_twitter'), embed=embed, mint_address=mint_address)
            if context.get("solAmount", 0) > 0 and 30 / context.get("solAmount", 0) < 2.14:
                logging.info(f"🔥 当前代币有评分, 准备通知: 【{context['mint']}】, Token_name:【{context['name']}】, Token_symbol:【{context['symbol']}】")
                await bot.send_message(channel_id=get_config('DISCORD.channel.has_score_channel'), embed=embed, mint_address=mint_address)
    except Exception as e:
        logging.error(f"Discord通知处理流水线异常: {context['mint']} | {str(e)}")


def _create_embed(context: dict) -> discord.Embed:
    """生成交易信息Embed（保持你的原始颜色逻辑）"""
    embed = discord.Embed(
        title=f"📊 {context['symbol']} 交易动态 | {context['txType'].upper()}", #  `{context['marketCapSol']/context['initialBuy']} SOL`
        color=discord.Color.green() if context["txType"] == "create" else discord.Color.red(),
        description=f"🈺 代币开盘时间: {context['detect_time'].strftime('%Y-%m-%d %H:%M:%S UTC+8')}\n  "
                    f"[🔍 点击直达OKX](https://www.okx.com/zh-hans/web3/detail/501/{context['mint']}) | [🔍 点击直达GMGN](https://gmgn.ai/sol/token/{context['mint']})\n"
                    f"```fix\n{context['mint']}\n```",
        timestamp=datetime.now()  # 自动添加时间戳
    )

    # 计算SOL差值并添加警告信息
    diff_percentage = (30 / context['solAmount']) * 100 if context['solAmount'] > 0 else 1000  # 如果solAmount为0，则设置为1000, 避免为实存SOL为0的骗局评分

    # 对 diff_percentage 进行分级评分
    # 评分规则：左侧可以等于，右侧不能等于
    risk_score = 0
    if diff_percentage >= 200:  # < 14 SOL
        risk_score = 0
    elif 100 <= diff_percentage < 200:  # 14 ~ 30 SOL
        risk_score = 1
    elif 60 <= diff_percentage < 100:  # 30 ~ 50 SOL
        risk_score = 2
    elif 45 <= diff_percentage < 60:  # 50 ~ 70 SOL
        risk_score = 3
    elif 30 <= diff_percentage < 45:  # 70 ~ 90 SOL
        risk_score = 4
    else:
        risk_score = 5

    # 使用星星表示评分（固定5个星星位置，几分填几个实心星）
    stars = "⭐" * risk_score + "☆" * (5 - risk_score)

    # 添加风险评分到 embed,
    # 绑定曲线会+30vSOL，投入SOL越多，绑定曲线加的vSOL占比越低
    # 此时可考虑入手3分钟或者盈利30%～50%离场，入手100RMB左右即可
    embed.add_field(
        name=f"\n🏷️ 入手评分: {stars}",
        value=f"提示: 1⭐️+此时可考虑入手3~5分钟或者盈利30%(1x⭐️)~50%+(5x⭐️)离场\n",
        inline=False
    )

    embed.set_author(
        name="新币通知",
        icon_url="https://pump.fun/_next/image?url=%2Flogo.png&w=64&q=75"
    )

    # 创建view和按钮的部分将在send_message中完成

    embed.add_field(name="", value="", inline=False)
    embed.add_field(
        name="\n💰 资金流动",
        value=f"DEV认购: `{context['initialBuy']:.2f} {context['symbol']}`\n实存SOL: `{context['solAmount']:.2f} SOL`\nDEV持仓: `{(context['initialBuy'] / 1_000_000_000 * 100) if context['vTokensInBondingCurve'] != 0 else 0:.2f}%`",
        inline=True
    )
    embed.add_field(
        name="\n📈 池子状态",
        value=f"代币市值: `