from .base import BaseCondition


class SocialActivityCondition(BaseCondition):
    """社交媒体活跃度条件"""

    def __init__(self, min_tweets: int):
        self.min_tweets = min_tweets

    def check(self, context: dict) -> bool:

        return len(context.get('related_tweets', [])) >= self.min_tweets
