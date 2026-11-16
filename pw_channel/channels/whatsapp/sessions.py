import asyncio
import json
import time
import logging
from typing import Dict, Optional, List, Any
import redis.asyncio as redis
from pw_channel.channels.whatsapp.models import Session
from pw_channel.channels.whatsapp.settings import settings

logger = logging.getLogger(__name__)


class RedisSessionManager:
    
    SESSIONS_KEY = "sessions:"
    LOCKS_KEY = "locks:"
    FLOW_MODE_KEY = "flow_mode:"
    LAST_MESSAGE_KEY = "last_message:"
    
    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._local_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self.session_timeout = settings.session_timeout
        self._prefix = settings.redis_key_prefix
        
        logger.info("RedisSessionManager initialized")
    
    async def connect(self):
        if self._redis is None:
            self._redis = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password if settings.redis_password else None,
                decode_responses=True
            )
            
            await self._redis.ping()
            logger.info(f"Connected to Redis at {settings.redis_host}:{settings.redis_port}")
    
    async def disconnect(self):
        if self._redis:
            await self._redis.close()
            logger.info("Redis connection closed")
    
    def _key(self, prefix: str, session_id: str) -> str:
        return f"{self._prefix}{prefix}{session_id}"
    
    async def _get_lock(self, session_id: str) -> asyncio.Lock:
        async with self._global_lock:
            if session_id not in self._local_locks:
                self._local_locks[session_id] = asyncio.Lock()
            return self._local_locks[session_id]
    
    
    def generate_session_id(self, phone_number: str) -> str:
        clean_number = phone_number.replace("+", "")
        return f"wa+{clean_number}"
    
    async def get_or_create_session(self, phone_number: str) -> Session:
        await self.connect()
        session_id = self.generate_session_id(phone_number)
        lock = await self._get_lock(session_id)
        
        async with lock:
            key = self._key(self.SESSIONS_KEY, session_id)
            session_data = await self._redis.get(key)
            
            if session_data:
                session_dict = json.loads(session_data)
                session_dict["last_activity"] = time.time()
                session_dict["message_count"] = session_dict.get("message_count", 0) + 1
                session = Session(**session_dict)
                
                await self._redis.setex(
                    key, 
                    self.session_timeout, 
                    json.dumps(session.model_dump())
                )
                logger.debug(f"Existing session: {session_id}, messages: {session.message_count}")
            else:
                session = Session(
                    session_id=session_id,
                    phone_number=phone_number,
                    is_processing=False,
                    last_activity=time.time(),
                    message_count=1
                )
                await self._redis.setex(
                    key, 
                    self.session_timeout, 
                    json.dumps(session.model_dump())
                )
                logger.info(f"New session created: {session_id}")
            
            return session
    
    async def is_processing(self, session_id: str) -> bool:
        await self.connect()
        key = self._key(self.SESSIONS_KEY, session_id)
        session_data = await self._redis.get(key)
        
        if session_data:
            session_dict = json.loads(session_data)
            return session_dict.get("is_processing", False)
        return False
    
    async def set_processing(self, session_id: str, is_processing: bool):
        await self.connect()
        lock = await self._get_lock(session_id)
        
        async with lock:
            key = self._key(self.SESSIONS_KEY, session_id)
            session_data = await self._redis.get(key)
            
            if session_data:
                session_dict = json.loads(session_data)
                session_dict["is_processing"] = is_processing
                await self._redis.setex(
                    key, 
                    self.session_timeout, 
                    json.dumps(session_dict)
                )
                logger.debug(f"Session {session_id} processing: {is_processing}")
    

    async def get_flow_mode(self, phone_number: str) -> str:
        await self.connect()
        key = self._key(self.FLOW_MODE_KEY, phone_number)
        data = await self._redis.get(key)
        if data:
            return json.loads(data).get("mode", "ai")
        return "ai"

    async def set_flow_mode(self, phone_number: str, mode: str, timeout: int = None):
        await self.connect()
        key = self._key(self.FLOW_MODE_KEY, phone_number)
        ttl = timeout if timeout is not None else settings.embracebot_flow_timeout
        data = {"mode": mode, "set_at": time.time()}
        await self._redis.setex(key, ttl, json.dumps(data))
        logger.info(f"Flow mode for {phone_number} set to '{mode}' (TTL: {ttl}s)")

    async def clear_flow_mode(self, phone_number: str):
        await self.connect()
        key = self._key(self.FLOW_MODE_KEY, phone_number)
        await self._redis.delete(key)
        logger.info(f"Flow mode cleared for {phone_number} (reverted to AI)")


    async def register_message_and_get_repeat_count(self, phone_number: str, fingerprint: str, ttl: int) -> int:
        await self.connect()
        key = self._key(self.LAST_MESSAGE_KEY, phone_number)

        lua = """
        local existing = redis.call('GET', KEYS[1])
        local count = 1
        if existing then
            local sep = string.find(existing, "\\1")
            local prev_fp = string.sub(existing, 1, sep - 1)
            local prev_count = tonumber(string.sub(existing, sep + 1))
            if prev_fp == ARGV[1] then
                count = prev_count + 1
            end
        end
        redis.call('SET', KEYS[1], ARGV[1] .. "\\1" .. tostring(count), 'EX', ARGV[2])
        return count
        """
        return await self._redis.eval(lua, 1, key, fingerprint, ttl)

    
    async def claim(self, key: str, ttl: int) -> tuple[bool, str | None]:
        await self.connect()
        full = f"{settings.redis_key_prefix}{key}"
        if await self._redis.set(full, "", nx=True, ex=ttl):
            return True, None
        return False, await self._redis.get(full)

    async def remember(self, key: str, value: str, ttl: int) -> None:
        await self._redis.set(f"{settings.redis_key_prefix}{key}", value, ex=ttl)

    async def release(self, key: str) -> None:
        await self._redis.delete(f"{settings.redis_key_prefix}{key}")

    async def delete_session(self, session_id: str):
        await self.connect()
        
        phone_number = session_id.replace("wa+", "") if session_id.startswith("wa+") else session_id

        keys_to_delete = [
            self._key(self.SESSIONS_KEY, session_id),
            self._key(self.FLOW_MODE_KEY, phone_number),
            self._key(self.LAST_MESSAGE_KEY, phone_number),
        ]
        
        if keys_to_delete:
            await self._redis.delete(*keys_to_delete)
        
        async with self._global_lock:
            if session_id in self._local_locks:
                del self._local_locks[session_id]
        
        logger.info(f"Session deleted: {session_id}")
    
    async def get_active_session_count(self) -> int:
        await self.connect()
        pattern = self._key(self.SESSIONS_KEY, "*")
        
        count = 0
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
            count += len(keys)
            if cursor == 0:
                break
        
        return count
    
    
    async def get_redis_info(self) -> Dict[str, Any]:
        await self.connect()
        info = await self._redis.info()
        return {
            "redis_version": info.get("redis_version"),
            "connected_clients": info.get("connected_clients"),
            "used_memory_human": info.get("used_memory_human"),
            "total_keys": await self._redis.dbsize()
        }


session_manager = RedisSessionManager()
