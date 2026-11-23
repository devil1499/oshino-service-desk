import asyncio

from pwdlib import PasswordHash


class PasswordService:
    def __init__(self) -> None:
        self._hasher = PasswordHash.recommended()
        self._semaphore = asyncio.Semaphore(4)

    async def hash(self, password: str) -> str:
        async with asyncio.timeout(10), self._semaphore:
            return await asyncio.to_thread(self._hasher.hash, password)

    async def verify(self, password: str, hashed: str) -> bool:
        async with asyncio.timeout(10), self._semaphore:
            return await asyncio.to_thread(self._hasher.verify, password, hashed)
