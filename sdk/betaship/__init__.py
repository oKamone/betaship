"""
Betaship SDK — 内部クライアントライブラリ

新サービスの接続手順:
  1. 環境変数: BETASHIP_API_URL=https://betaship-api-xxx.run.app
  2. コード（Flask 同期）:
       from betaship import BetashipClient, InsufficientCreditsError
       _bs = BetashipClient("myservice")
       reply = _bs.complete(bearer, messages, system=SYSTEM, model="claude-haiku-4-5-20251001", max_tokens=400)

  2. コード（FastAPI 非同期）:
       from betaship import AsyncBetashipClient, InsufficientCreditsError
       _bs = AsyncBetashipClient("myservice")
       reply = await _bs.complete(bearer, messages, system=SYSTEM, model="claude-haiku-4-5-20251001", max_tokens=300)

動作:
  - bearer + BETASHIP_API_URL あり → Betaship 経由（クレジット消費・ログ記録）
  - どちらか欠如 or Betaship 通信失敗 → 直接 Claude にフォールバック
  - 402 応答 → InsufficientCreditsError を raise（フォールバックしない）
"""
from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)

__all__ = ["BetashipClient", "AsyncBetashipClient", "InsufficientCreditsError"]


class InsufficientCreditsError(Exception):
    """Betaship が 402 を返したとき（クレジット残高不足）"""


class BetashipClient:
    """同期クライアント — Flask / requests 環境向け"""

    def __init__(self, service: str, *, fallback: bool = True):
        """
        service : product_config の product_id（例: "moshimo", "await"）
        fallback: Betaship 通信失敗時に直接 Claude へフォールバックするか
        """
        self.service = service
        self.fallback = fallback
        self._api_url = os.environ.get("BETASHIP_API_URL", "").rstrip("/")
        self._claude = None  # lazy init

    def complete(
        self,
        bearer: str | None,
        messages: list,
        *,
        system: str = "",
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 1024,
        tool: str = "default",
    ) -> str:
        """Claude を呼び出してテキストを返す。"""
        if bearer and self._api_url:
            try:
                return self._via_betaship(
                    bearer, messages,
                    system=system, model=model, max_tokens=max_tokens, tool=tool,
                )
            except InsufficientCreditsError:
                raise
            except Exception as exc:
                if not self.fallback:
                    raise
                logger.warning("[betaship:%s] %s — fallback to direct Claude", self.service, exc)

        return self._direct(messages, system=system, model=model, max_tokens=max_tokens)

    def _via_betaship(
        self, bearer: str, messages: list,
        *, system: str, model: str, max_tokens: int, tool: str,
    ) -> str:
        import requests as _req
        r = _req.post(
            f"{self._api_url}/api/ai",
            json={
                "service": self.service, "tool": tool,
                "messages": messages, "system": system,
                "model": model, "max_tokens": max_tokens,
            },
            headers={"Authorization": f"Bearer {bearer}"},
            timeout=40,
        )
        if r.status_code == 402:
            raise InsufficientCreditsError("insufficient_credits")
        r.raise_for_status()
        return r.json()["content"]

    def _direct(
        self, messages: list,
        *, system: str, model: str, max_tokens: int,
    ) -> str:
        if self._claude is None:
            import anthropic
            self._claude = anthropic.Anthropic()
        kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": messages}
        if system:
            kwargs["system"] = system
        return self._claude.messages.create(**kwargs).content[0].text


class AsyncBetashipClient:
    """非同期クライアント — FastAPI / httpx 環境向け"""

    def __init__(self, service: str, *, fallback: bool = True):
        self.service = service
        self.fallback = fallback
        self._api_url = os.environ.get("BETASHIP_API_URL", "").rstrip("/")
        self._claude = None

    async def complete(
        self,
        bearer: str | None,
        messages: list,
        *,
        system: str = "",
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 1024,
        tool: str = "default",
    ) -> str:
        """Claude を呼び出してテキストを返す（非同期）。"""
        if bearer and self._api_url:
            try:
                return await self._via_betaship(
                    bearer, messages,
                    system=system, model=model, max_tokens=max_tokens, tool=tool,
                )
            except InsufficientCreditsError:
                raise
            except Exception as exc:
                if not self.fallback:
                    raise
                logger.warning("[betaship:%s] %s — fallback to direct Claude", self.service, exc)

        return self._direct(messages, system=system, model=model, max_tokens=max_tokens)

    async def _via_betaship(
        self, bearer: str, messages: list,
        *, system: str, model: str, max_tokens: int, tool: str,
    ) -> str:
        import httpx
        async with httpx.AsyncClient(timeout=40) as hc:
            r = await hc.post(
                f"{self._api_url}/api/ai",
                json={
                    "service": self.service, "tool": tool,
                    "messages": messages, "system": system,
                    "model": model, "max_tokens": max_tokens,
                },
                headers={"Authorization": f"Bearer {bearer}"},
            )
        if r.status_code == 402:
            raise InsufficientCreditsError("insufficient_credits")
        r.raise_for_status()
        return r.json()["content"]

    def _direct(
        self, messages: list,
        *, system: str, model: str, max_tokens: int,
    ) -> str:
        if self._claude is None:
            import anthropic
            self._claude = anthropic.Anthropic()
        kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": messages}
        if system:
            kwargs["system"] = system
        return self._claude.messages.create(**kwargs).content[0].text
