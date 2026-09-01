import asyncio
import logging

from astrbot.api.event import MessageChain
from astrbot.api.event.filter import EventMessageType, event_message_type
from astrbot.api.message_components import At, Plain
from astrbot.api.star import Context, Star, register
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .roulette_engine import RouletteEngine, RouletteOutcome, RouletteSession


logger = logging.getLogger("astrbot")


@register("repeat_roulette", "coocoodaegap", "复读轮盘赌", "0.1.0")
class RepeatRoulettePlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self.engine = RouletteEngine(
            min_repeat_count=self.config.get("min_repeat_count", 2),
            base_bullet_chance=self.config.get("base_bullet_chance", 20),
            chance_per_repeat=self.config.get("chance_per_repeat", 15),
            max_bullet_chance=self.config.get("max_bullet_chance", 80),
            random_mode=self.config.get("random_mode", True),
            last_n_th=self.config.get("last_n_th", 1),
            round_timeout_seconds=self.config.get("round_timeout_seconds", 180),
        )
        self.sessions: dict[str, RouletteSession] = {}
        self.session_locks: dict[str, asyncio.Lock] = {}

    @event_message_type(EventMessageType.GROUP_MESSAGE)
    async def on_message(self, event: AiocqhttpMessageEvent):
        group_id = event.get_group_id()
        sender_id = event.get_sender_id()
        if not group_id or event.get_self_id() == sender_id:
            return

        # A group can host multiple bots. Keep their rounds independent.
        session_id = f"{event.get_self_id()}:{group_id}"
        lock = self.session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            session = self.sessions.setdefault(session_id, RouletteSession())
            outcome = self.engine.advance(
                session,
                message=event.message_str,
                sender_id=str(sender_id),
                now=asyncio.get_running_loop().time(),
            )

        if outcome is not None:
            await self._settle_outcome(event, group_id, outcome)

    async def _settle_outcome(
        self,
        event: AiocqhttpMessageEvent,
        group_id: str,
        outcome: RouletteOutcome,
    ) -> None:
        """Announce a completed round and apply punishment only for a live round."""

        target_user = outcome.target_user_id
        if not outcome.fired:
            await self._send_result(
                event,
                MessageChain([
                    At(qq=target_user),
                    Plain(
                        f" 扣下扳机——空包！本轮 {outcome.repeat_count} 次复读，"
                        f"实弹率 {outcome.bullet_chance}%。"
                    ),
                ]),
            )
            return

        duration = self.config.get("ban_duration", 60)
        try:
            await event.bot.set_group_ban(
                group_id=int(group_id),
                user_id=int(target_user),
                duration=int(duration),
            )
        except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
            logger.warning("轮盘赌实弹未能发射: %s", exc)
            await self._send_result(
                event,
                MessageChain([
                    At(qq=target_user),
                    Plain(" 扳机扣下了，但枪卡壳了……这次算你走运。"),
                ]),
            )
            return

        await self._send_result(
            event,
            MessageChain([
                At(qq=target_user),
                Plain(
                    f" 砰！本轮 {outcome.repeat_count} 次复读，"
                    f"实弹率 {outcome.bullet_chance}%，喜提 {duration} 秒轮盘惩罚。"
                ),
            ]),
        )

    @staticmethod
    async def _send_result(
        event: AiocqhttpMessageEvent, message: MessageChain
    ) -> None:
        try:
            await event.send(message)
        except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
            logger.warning("轮盘赌播报发送失败: %s", exc)
