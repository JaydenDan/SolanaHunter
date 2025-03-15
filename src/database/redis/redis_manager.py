import logging
import asyncio
from typing import Optional, Any, Dict, List
from redis.asyncio import Redis, ConnectionPool

from config.logging_config import get_logger
from config import get_config

logger = get_logger('redis_manager')


class RedisManager:
    """Redis数据库管理器，提供对Redis的异步操作接口"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super(RedisManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, host: str = None, port: int = None, 
                 db: int = None, password: Optional[str] = None, 
                 decode_responses: bool = None, max_connections: int = None,
                 connection_timeout: int = None, **kwargs):
        """
        初始化Redis管理器
        
        Args:
            host: Redis服务器地址
            port: Redis服务器端口
            db: 数据库索引
            password: Redis密码
            decode_responses: 是否自动解码响应
            max_connections: 最大连接数
            connection_timeout: 连接超时时间(秒)
            **kwargs: 其他redis连接参数
        """
        # 避免重复初始化
        if self._initialized:
            return
        
        # 从配置中加载Redis设置
        redis_config = get_config('REDIS', {})
            
        self.host = host or redis_config.get('host', 'localhost')
        self.port = port or redis_config.get('port', 6379)
        self.db = db or redis_config.get('db', 0)
        self.password = password or redis_config.get('password', None)
        self.decode_responses = decode_responses if decode_responses is not None else redis_config.get('decode_responses', True)
        self.connection_timeout = connection_timeout or redis_config.get('connection_timeout', 5)
        self.max_connections = max_connections or redis_config.get('max_connections', 10)
        self.redis_kwargs = kwargs
        
        # 异步客户端连接池
        self._pool = None
        self._client = None
        
        self._initialized = True
        logger.info(f"Redis异步管理器初始化完成: {self.host}:{self.port}/{self.db}")
    
    async def init_pool(self):
        """初始化异步连接池"""
        if self._pool is None:
            try:
                self._pool = ConnectionPool(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    password=self.password,
                    decode_responses=self.decode_responses,
                    max_connections=self.max_connections,
                    socket_timeout=self.connection_timeout,
                    **self.redis_kwargs
                )
                logger.info("Redis异步连接池初始化完成")
            except Exception as e:
                logger.error(f"Redis异步连接池初始化失败: {str(e)}")
                raise
    
    async def get_client(self) -> Redis:
        """获取异步Redis客户端"""
        if self._pool is None:
            await self.init_pool()
        
        if self._client is None:
            self._client = Redis(connection_pool=self._pool)
        
        return self._client
    
    async def close(self):
        """关闭异步连接池"""
        if self._pool:
            await self._pool.disconnect()
            logger.info("Redis异步连接池已关闭")
    
    # ===================== 异步操作方法 =====================
    
    async def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """
        设置键值对
        
        Args:
            key: 键名
            value: 值
            ex: 过期时间(秒)
            
        Returns:
            bool: 操作是否成功
        """
        try:
            client = await self.get_client()
            return await client.set(key, value, ex=ex)
        except Exception as e:
            logger.error(f"Redis set操作失败: {str(e)}")
            return False
    
    async def get(self, key: str) -> Any:
        """
        获取键值
        
        Args:
            key: 键名
            
        Returns:
            Any: 值，不存在则返回None
        """
        try:
            client = await self.get_client()
            return await client.get(key)
        except Exception as e:
            logger.error(f"Redis get操作失败: {str(e)}")
            return None
    
    async def delete(self, key: str) -> int:
        """
        删除键
        
        Args:
            key: 键名
            
        Returns:
            int: 删除的键数量
        """
        try:
            client = await self.get_client()
            return await client.delete(key)
        except Exception as e:
            logger.error(f"Redis delete操作失败: {str(e)}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """
        检查键是否存在
        
        Args:
            key: 键名
            
        Returns:
            bool: 是否存在
        """
        try:
            client = await self.get_client()
            return bool(await client.exists(key))
        except Exception as e:
            logger.error(f"Redis exists操作失败: {str(e)}")
            return False
    
    async def expire(self, key: str, seconds: int) -> bool:
        """
        设置键过期时间
        
        Args:
            key: 键名
            seconds: 过期时间(秒)
            
        Returns:
            bool: 操作是否成功
        """
        try:
            client = await self.get_client()
            return bool(await client.expire(key, seconds))
        except Exception as e:
            logger.error(f"Redis expire操作失败: {str(e)}")
            return False
    
    async def hset(self, name: str, key: str, value: Any) -> int:
        """
        设置哈希表字段值
        
        Args:
            name: 哈希表名
            key: 字段名
            value: 值
            
        Returns:
            int: 新增的字段数(如果已存在则返回0)
        """
        try:
            client = await self.get_client()
            return await client.hset(name, key, value)
        except Exception as e:
            logger.error(f"Redis hset操作失败: {str(e)}")
            return 0
    
    async def hget(self, name: str, key: str) -> Any:
        """
        获取哈希表字段值
        
        Args:
            name: 哈希表名
            key: 字段名
            
        Returns:
            Any: 字段值，不存在则返回None
        """
        try:
            client = await self.get_client()
            return await client.hget(name, key)
        except Exception as e:
            logger.error(f"Redis hget操作失败: {str(e)}")
            return None
    
    async def hgetall(self, name: str) -> Dict:
        """
        获取哈希表所有字段和值
        
        Args:
            name: 哈希表名
            
        Returns:
            Dict: 哈希表字段和值的字典
        """
        try:
            client = await self.get_client()
            return await client.hgetall(name)
        except Exception as e:
            logger.error(f"Redis hgetall操作失败: {str(e)}")
            return {}
    
    async def hdel(self, name: str, *keys) -> int:
        """
        删除哈希表字段
        
        Args:
            name: 哈希表名
            *keys: 要删除的字段名
            
        Returns:
            int: 删除的字段数量
        """
        try:
            client = await self.get_client()
            return await client.hdel(name, *keys)
        except Exception as e:
            logger.error(f"Redis hdel操作失败: {str(e)}")
            return 0
    
    async def lpush(self, name: str, *values) -> int:
        """
        列表左侧添加元素
        
        Args:
            name: 列表名
            *values: 要添加的值
            
        Returns:
            int: 添加后列表长度
        """
        try:
            client = await self.get_client()
            return await client.lpush(name, *values)
        except Exception as e:
            logger.error(f"Redis lpush操作失败: {str(e)}")
            return 0
    
    async def rpush(self, name: str, *values) -> int:
        """
        列表右侧添加元素
        
        Args:
            name: 列表名
            *values: 要添加的值
            
        Returns:
            int: 添加后列表长度
        """
        try:
            client = await self.get_client()
            return await client.rpush(name, *values)
        except Exception as e:
            logger.error(f"Redis rpush操作失败: {str(e)}")
            return 0
    
    async def lpop(self, name: str) -> Any:
        """
        列表左侧弹出元素
        
        Args:
            name: 列表名
            
        Returns:
            Any: 弹出的元素，列表为空则返回None
        """
        try:
            client = await self.get_client()
            return await client.lpop(name)
        except Exception as e:
            logger.error(f"Redis lpop操作失败: {str(e)}")
            return None
    
    async def rpop(self, name: str) -> Any:
        """
        列表右侧弹出元素
        
        Args:
            name: 列表名
            
        Returns:
            Any: 弹出的元素，列表为空则返回None
        """
        try:
            client = await self.get_client()
            return await client.rpop(name)
        except Exception as e:
            logger.error(f"Redis rpop操作失败: {str(e)}")
            return None
    
    async def lrange(self, name: str, start: int, end: int) -> List:
        """
        获取列表指定范围内的元素
        
        Args:
            name: 列表名
            start: 起始索引
            end: 结束索引
            
        Returns:
            List: 元素列表
        """
        try:
            client = await self.get_client()
            return await client.lrange(name, start, end)
        except Exception as e:
            logger.error(f"Redis lrange操作失败: {str(e)}")
            return []
    
    async def sadd(self, name: str, *values) -> int:
        """
        集合添加元素
        
        Args:
            name: 集合名
            *values: 要添加的值
            
        Returns:
            int: 添加的元素数量
        """
        try:
            client = await self.get_client()
            return await client.sadd(name, *values)
        except Exception as e:
            logger.error(f"Redis sadd操作失败: {str(e)}")
            return 0
    
    async def smembers(self, name: str) -> set:
        """
        获取集合所有成员
        
        Args:
            name: 集合名
            
        Returns:
            set: 集合成员
        """
        try:
            client = await self.get_client()
            return await client.smembers(name)
        except Exception as e:
            logger.error(f"Redis smembers操作失败: {str(e)}")
            return set()
    
    async def srem(self, name: str, *values) -> int:
        """
        集合移除元素
        
        Args:
            name: 集合名
            *values: 要移除的值
            
        Returns:
            int: 移除的元素数量
        """
        try:
            client = await self.get_client()
            return await client.srem(name, *values)
        except Exception as e:
            logger.error(f"Redis srem操作失败: {str(e)}")
            return 0


# 创建默认实例
redis_manager = RedisManager()

# 使用示例
if __name__ == "__main__":
    # 异步使用示例
    async def test_async():
        await redis_manager.set("test_key", "test_value")
        result = await redis_manager.get("test_key")
        print(f"异步获取结果: {result}")
        
        # 哈希表操作
        await redis_manager.hset("user:1", "name", "张三")
        await redis_manager.hset("user:1", "age", "25")
        user = await redis_manager.hgetall("user:1")
        print(f"用户信息: {user}")
        
        # 列表操作
        await redis_manager.lpush("queue", "任务1", "任务2")
        task = await redis_manager.rpop("queue")
        print(f"弹出任务: {task}")
        
    asyncio.run(test_async()) 