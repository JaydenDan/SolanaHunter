import logging


class TwitterConditionV1:

    def __init__(self,
                 token_name: str,
                 token_symbol: str,
                 user_name: str,
                 screen_name: str,
                 description: str,
                 verified: bool,
                 is_blue_verified: bool):
        # 初始化参数
        self.token_name = token_name
        self.token_symbol = token_symbol
        self.user_name = user_name
        self.screen_name = screen_name
        self.description = description
        self.verified = verified
        self.is_blue_verified = is_blue_verified

    # 判断函数 如果token_name、token_symbol在username、screen_name、description出现至少一次说明是发币方，返回True，一个一个对比，输出不同的日志
    def judge(self):
        if self.token_name in self.user_name or self.token_name in self.screen_name or self.token_name in self.description:
            logging.info(f"🏆 匹配成功，当前CA的名称 {self.token_name} 在 {self.screen_name} 找到")
            return True
        if self.token_symbol in self.user_name or self.token_symbol in self.screen_name or self.token_symbol in self.description:
            logging.info(f"🏆 匹配成功，当前CA的符号 {self.token_symbol} 在 {self.screen_name} 找到")
            return True
        logging.info(f"🚫 匹配失败，当前CA的名称 {self.token_name} 发帖人 {self.screen_name} 不是项目方")
        return False


    #

