from astrbot.api.star import Context, Star, register
from astrbot.api.event.filter import event_message_type, EventMessageType
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

@register("repeat_roulette", "coocoodaegap", "复读轮盘赌", "0.0.1")
class RepeatRoulettePlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}
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

        # 跳过 Bot 自己
        if event.get_self_id() == sender_id:
            return

        if session["last_msg"] is not None and msg == session["last_msg"]:
            session["repeat_users"].append(sender_id)
        else:
            if len(session["repeat_users"]) > 0:
                n = self.config.get("n", 1)
                duration = self.config.get("ban_duration", 60)

                if len(session["repeat_users"]) >= n:
                    target_user = session["repeat_users"][-n]
                    try:
                        await event.bot.set_group_ban(
                            group_id=int(group_id),
                            user_id=int(target_user),
                            duration=duration,
                        )
                    except Exception:
                        pass

            session["last_msg"] = msg
            session["repeat_users"] = []
