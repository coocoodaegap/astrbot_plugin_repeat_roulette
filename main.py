from astrbot.api.star import Context, Star, register
from astrbot.api.event.filter import event_message_type, EventMessageType
from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, Plain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
import random
import logging

logger = logging.getLogger("astrbot")

@register("repeat_roulette", "coocoodaegap", "复读轮盘赌", "0.0.3")
class RepeatRoulettePlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}
        self.random_mode = self.config.get("random_mode", False)
        self.sessions = {}  # group_id -> {"last_msg": str, "repeat_users": list}

    @event_message_type(EventMessageType.GROUP_MESSAGE)
    async def on_message(self, event: AiocqhttpMessageEvent):
        msg = event.message_str
        group_id = event.get_group_id()
        if not group_id:
            return

        session_id = group_id

        if session_id not in self.sessions:
            self.sessions[session_id] = {"last_msg": None, "repeat_users": []}

        session = self.sessions[session_id]
        sender_id = event.get_sender_id()

        if event.get_self_id() == sender_id:
            return

        if session["last_msg"] is not None and msg == session["last_msg"]:
            session["repeat_users"].append(sender_id)
        else:
            if len(session["repeat_users"]) > 0:
                duration = self.config.get("ban_duration", 60)

                if self.random_mode:
                    target_user = random.choice(session["repeat_users"])
                else:
                    n = self.config.get("last_n_th", 1)
                    if len(session["repeat_users"]) >= n:
                        target_user = session["repeat_users"][-n]
                    else:
                        target_user = None

                if target_user is not None:
                    
                    ban_success = False
                    try:
                        # 尝试禁言
                        await event.bot.set_group_ban(
                            group_id=int(group_id),
                            user_id=int(target_user),
                            duration=duration,
                        )
                        ban_success = True
                    except Exception as e:
                        err_msg = str(e).lower()
                        if "cannot ban" in err_msg:
                            await event.send(MessageChain([Plain("子弹打歪了...")]))
                        else:
                            logger.error(f"轮盘赌禁言失败: {e}")

                    if ban_success:
                        try:
                            await event.send(
                                MessageChain([
                                    At(qq=target_user),
                                    Plain(f" 子弹打中你了，喜提 {duration}秒 轮盘惩罚~")
                                ])
                            )
                        except Exception as e:
                            logger.error(f"轮盘赌发送消息失败: {e}")

            session["last_msg"] = msg
            session["repeat_users"] = []
