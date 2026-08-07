"""
飞书机器人 — 通过飞书消息触发 Agent 执行（合并版）

提供:
- handle_webhook: 飞书事件回调入口
- 异步 Agent 调用: 消息 → Agent 处理 → 回复
"""
import json
import asyncio
import threading
import requests
from backend.config import settings
from backend.core.logger import log


class FeishuBot:
    """飞书机器人: 接收 Webhook 消息 → 调用 Agent → 回复"""

    def __init__(self):
        self.app_id = settings.FEISHU_APP_ID
        self.app_secret = settings.FEISHU_APP_SECRET
        self._token = ""
        self._ws_client = None       # lark-oapi ws.Client(长连接)
        self._ws_thread = None       # 长连接后台线程

    def _get_token(self) -> str:
        """获取飞书 tenant_access_token"""
        if not self.app_id or not self.app_secret:
            return ""
        try:
            resp = requests.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
                timeout=10,
            )
            data = resp.json()
            self._token = data.get("tenant_access_token", "")
        except Exception as e:
            log.warning("飞书获取Token失败: %s", e)
        return self._token

    def handle_text_message(self, sender: str, text: str):
        """收到文本消息的统一入口: 确认收到 → 后台线程跑 agent → 回复。

        供 Webhook 回调模式与长连接(WebSocket)模式共用。
        """
        if not sender or not text:
            return
        # 立即确认收到, 后台线程跑 agent(fire-and-forget, 不阻塞回调/长连接)
        self._reply(sender, "已收到您的消息, 正在处理...")
        self._spawn_agent(sender, text)

    @staticmethod
    def _extract_text(content_str: str) -> str:
        """从飞书消息 content(JSON 字符串)提取文本。"""
        try:
            content = json.loads(content_str)
            return content.get("text", "")
        except (json.JSONDecodeError, TypeError):
            return str(content_str)

    def handle_webhook(self, body: dict) -> dict:
        """
        处理飞书 Webhook 回调

        支持:
        - url_verification: 飞书验证请求
        - im.message.receive_v1: 接收消息
        """
        # 验证挑战
        if body.get("type") == "url_verification":
            return {"challenge": body.get("challenge", "")}

        # 解析消息
        event = body.get("event", {})
        message = event.get("message", {})
        content_str = message.get("content", "{}")
        sender = event.get("sender", {}).get("sender_id", {}).get("open_id", "")
        if not content_str or not sender:
            return {"msg": "ok"}
        self.handle_text_message(sender, self._extract_text(content_str))
        return {"msg": "ok"}

    # ── 长连接模式(WebSocket, 免公网 URL) ──

    def start_long_connection(self) -> bool:
        """启动飞书长连接模式 — 本地主动连飞书网关, 事件经长连接推送, 无需公网 URL。

        用官方 lark-oapi 的 ws.Client, 在后台线程运行。需要 FEISHU_APP_ID/SECRET。
        """
        if not (self.app_id and self.app_secret):
            log.warning("[飞书] 长连接未启动: 缺少 FEISHU_APP_ID / FEISHU_APP_SECRET")
            return False
        if self._ws_thread is not None and self._ws_thread.is_alive():
            return True
        try:
            import lark_oapi as lark
            from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

            def on_message(data: P2ImMessageReceiveV1):
                try:
                    event = data.event
                    sender = (event.sender.sender_id.open_id
                              if event.sender and event.sender.sender_id else "")
                    content_str = event.message.content if event.message else "{}"
                    if not sender or not content_str:
                        return
                    self.handle_text_message(sender, self._extract_text(content_str))
                except Exception as e:  # noqa: BLE001
                    log.warning("[飞书] 长连接消息处理异常: %s", e)

            handler = (lark.EventDispatcherHandler
                       .builder(self.app_id, self.app_secret)
                       .register_p2_im_message_receive_v1(on_message)
                       .build())
            self._ws_client = lark.ws.Client(
                self.app_id, self.app_secret, event_handler=handler, auto_reconnect=True)
            self._ws_thread = threading.Thread(target=self._ws_client.start, daemon=True)
            self._ws_thread.start()
            log.info("[飞书] 长连接模式已启动(免公网), 可在飞书里直接和 agent 对话")
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("[飞书] 长连接启动失败: %s", e)
            return False

    def close_long_connection(self):
        if self._ws_client is not None:
            try:
                self._ws_client.close()
            except Exception:  # noqa: BLE001
                pass
            self._ws_client = None

    def _spawn_agent(self, sender: str, text: str):
        """后台线程处理 agent, 不在 webhook 主路径阻塞。"""
        def runner():
            try:
                asyncio.run(self._process_with_agent(sender, text))
            except Exception as e:  # noqa: BLE001
                self._reply(sender, f"处理失败: {str(e)[:100]}")
        threading.Thread(target=runner, daemon=True).start()

    async def _process_with_agent(self, sender: str, text: str):
        """通过 Agent 处理消息并回复"""
        try:
            from agent.agent_service import agent_service

            final_response = ""
            async for event in agent_service.run(text, f"feishu_{sender}"):
                if event["type"] == "token":
                    final_response += event.get("text", "")
                elif event["type"] == "done":
                    final_response = event.get("final_response", final_response)
                elif event["type"] == "error":
                    final_response = f"错误: {event.get('message', '')}"

            reply_text = final_response[:2000] if final_response else "未能生成回复"
            self._reply(sender, reply_text)

        except ImportError:
            self._reply(sender, "Agent 服务未就绪, 请检查配置")
        except Exception as e:
            self._reply(sender, f"处理异常: {str(e)[:100]}")

    def _reply(self, open_id: str, text: str):
        """回复飞书消息"""
        if not self._token:
            self._get_token()
        if not self._token:
            return
        try:
            requests.post(
                "https://open.feishu.cn/open-apis/im/v1/messages",
                params={"receive_id_type": "open_id"},
                headers={"Authorization": f"Bearer {self._token}",
                         "Content-Type": "application/json"},
                json={"receive_id": open_id, "msg_type": "text",
                      "content": json.dumps({"text": text})},
                timeout=10,
            )
        except Exception as e:
            log.warning("飞书回复失败: %s", e)


feishu_bot = FeishuBot()
