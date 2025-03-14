import logging
import asyncio
from typing import Optional, Any, Dict, List, Tuple, Union
import time
import aiomysql

from config.logging_config import get_logger
from config import get_config

logger = get_logger('mysql_manager')


class MySQLManager:
    """MySQL数据库管理器，提供对MySQL的异步操作接口"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super(MySQLManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, host: str = None, port: int = None, 
                 user: str = None, password: str = None, 
                 database: str = None, charset: str = None, 
                 pool_size: int = None, connect_timeout: int = None, **kwargs):
        """
        初始化MySQL管理器
        
        Args:
            host: MySQL服务器地址
            port: MySQL服务器端口
            user: 用户名
            password: 密码
            database: 数据库名
            charset: 字符集
            pool_size: 连接池大小
            connect_timeout: 连接超时时间(秒)
            **kwargs: 其他连接参数
        """
        # 避免重复初始化
        if self._initialized:
            return
        
        # 从配置中加载MySQL设置
        mysql_config = get_config('MYSQL', {})
            
        self.host = host or mysql_config.get('host', 'localhost')
        self.port = port or mysql_config.get('port', 3306)
        self.user = user or mysql_config.get('user', 'root')
        self.password = password or mysql_config.get('password', '')
        self.database = database or mysql_config.get('database', '')
        self.charset = charset or mysql_config.get('charset', 'utf8mb4')
        self.pool_size = pool_size or mysql_config.get('pool_size', 5)
        self.connect_timeout = connect_timeout or mysql_config.get('connect_timeout', 10)
        self.mysql_kwargs = kwargs
        
        # 连接池配置
        self.pool_config = {
            'host': self.host,
            'port': self.port,
            'user': self.user,
            'password': self.password,
            'db': self.database,
            'charset': self.charset,
            'maxsize': self.pool_size,
            'connect_timeout': self.connect_timeout,
            'cursorclass': aiomysql.DictCursor,  # 使用字典游标
            'autocommit': True,  # 默认自动提交
            **{k: v for k, v in self.mysql_kwargs.items() if k not in ['cursorclass']}
        }
        
        # 异步连接池
        self._pool = None
        
        self._initialized = True
        logger.info(f"MySQL异步管理器初始化完成: {self.host}:{self.port}/{self.database}")
    
    async def init_pool(self):
        """初始化异步连接池"""
        if self._pool is None:
            try:
                self._pool = await aiomysql.create_pool(**self.pool_config)
                logger.info("MySQL异步连接池初始化完成")
            except Exception as e:
                logger.error(f"MySQL异步连接池初始化失败: {str(e)}")
                raise
    
    async def get_pool(self) -> aiomysql.Pool:
        """获取异步连接池"""
        if self._pool is None:
            await self.init_pool()
        return self._pool
    
    async def close(self):
        """关闭异步连接池"""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            logger.info("MySQL异步连接池已关闭")
    
    # ===================== 异步操作方法 =====================
    
    async def execute_query(self, sql: str, params: Optional[Union[tuple, dict]] = None) -> List[Dict]:
        """
        执行查询SQL并返回结果
        
        Args:
            sql: SQL语句
            params: SQL参数
            
        Returns:
            List[Dict]: 查询结果列表（字典格式）
        """
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(sql, params)
                    results = await cursor.fetchall()
                    return results
                except Exception as e:
                    logger.error(f"执行查询失败: {str(e)}, SQL: {sql}, 参数: {params}")
                    raise
    
    async def execute_many(self, sql: str, params_list: List[Union[tuple, dict]]) -> int:
        """
        批量执行SQL
        
        Args:
            sql: SQL语句
            params_list: SQL参数列表
            
        Returns:
            int: 受影响的行数
        """
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    result = await cursor.executemany(sql, params_list)
                    await conn.commit()
                    return result
                except Exception as e:
                    await conn.rollback()
                    logger.error(f"批量执行SQL失败: {str(e)}, SQL: {sql}, 参数数量: {len(params_list)}")
                    raise
    
    async def execute(self, sql: str, params: Optional[Union[tuple, dict]] = None) -> int:
        """
        执行SQL（增删改）
        
        Args:
            sql: SQL语句
            params: SQL参数
            
        Returns:
            int: 受影响的行数
        """
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    result = await cursor.execute(sql, params)
                    await conn.commit()
                    return result
                except Exception as e:
                    await conn.rollback()
                    logger.error(f"执行SQL失败: {str(e)}, SQL: {sql}, 参数: {params}")
                    raise
    
    async def insert(self, table: str, data: Dict) -> int:
        """
        插入数据
        
        Args:
            table: 表名
            data: 数据字典 {字段名: 值}
            
        Returns:
            int: 插入ID
        """
        fields = ', '.join(f'`{field}`' for field in data.keys())
        placeholders = ', '.join(['%s'] * len(data))
        values = list(data.values())
        
        sql = f"INSERT INTO `{table}` ({fields}) VALUES ({placeholders})"
        
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(sql, values)
                    await conn.commit()
                    return cursor.lastrowid
                except Exception as e:
                    await conn.rollback()
                    logger.error(f"插入数据失败: {str(e)}, 表: {table}, 数据: {data}")
                    raise
    
    async def update(self, table: str, data: Dict, where: str, where_params: Optional[Union[tuple, Any]] = None) -> int:
        """
        更新数据
        
        Args:
            table: 表名
            data: 更新的数据字典 {字段名: 新值}
            where: WHERE条件
            where_params: WHERE条件参数
            
        Returns:
            int: 受影响的行数
        """
        set_clause = ', '.join([f"`{field}` = %s" for field in data.keys()])
        values = list(data.values())
        
        sql = f"UPDATE `{table}` SET {set_clause} WHERE {where}"
        
        if where_params:
            if isinstance(where_params, tuple):
                values.extend(where_params)
            else:
                values.append(where_params)
        
        return await self.execute(sql, values)
    
    async def delete(self, table: str, where: str, where_params: Optional[Union[tuple, Any]] = None) -> int:
        """
        删除数据
        
        Args:
            table: 表名
            where: WHERE条件
            where_params: WHERE条件参数
            
        Returns:
            int: 受影响的行数
        """
        sql = f"DELETE FROM `{table}` WHERE {where}"
        return await self.execute(sql, where_params)
    
    async def transaction(self):
        """
        返回异步事务上下文管理器
        
        Returns:
            AsyncTransactionContextManager: 异步事务上下文管理器
        """
        return AsyncTransactionContextManager(self)


class AsyncTransactionContextManager:
    """异步事务上下文管理器"""
    
    def __init__(self, db_manager: MySQLManager):
        self.db_manager = db_manager
        self.pool = None
        self.conn = None
        self.cursor = None
    
    async def __aenter__(self):
        self.pool = await self.db_manager.get_pool()
        self.conn = await self.pool.acquire()
        await self.conn.begin()  # 开始事务
        self.cursor = await self.conn.cursor()
        return self.cursor
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                # 没有异常，提交事务
                await self.conn.commit()
            else:
                # 有异常，回滚事务
                await self.conn.rollback()
                logger.error(f"异步事务回滚: {exc_type.__name__}: {exc_val}")
        finally:
            if self.cursor:
                await self.cursor.close()
            if self.conn:
                self.pool.release(self.conn)


# 创建默认实例
mysql_manager = MySQLManager()

# 使用示例
if __name__ == "__main__":
    # 异步使用示例
    async def test_async():
        # 简单异步查询
        users = await mysql_manager.execute_query("SELECT * FROM users LIMIT 10")
        for user in users:
            print(user)
        
        # 插入数据
        user_id = await mysql_manager.insert('users', {
            'name': '李四',
            'email': 'lisi@example.com',
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
        })
        print(f"插入的用户ID: {user_id}")
        
        # 使用异步事务
        async with await mysql_manager.transaction() as cursor:
            await cursor.execute("INSERT INTO logs (message) VALUES (%s)", ("测试日志",))
            await cursor.execute("UPDATE statistics SET count = count + 1 WHERE name = %s", ("visit",))
    
    # asyncio.run(test_async()) 