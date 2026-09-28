import httpx
import logging
from app.config import WEBHOOK_URL

logger = logging.getLogger("morphe.notifier")

async def send_notification(title: str, message: str, status: str = "success") -> bool:
    if not WEBHOOK_URL:
        return False

    url = WEBHOOK_URL.strip()
    color = 0x22c55e if status == "success" else 0xef4444
    emoji = "✅" if status == "success" else "❌"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if "ntfy.sh" in url:
                headers = {
                    "Title": f"{emoji} {title}",
                    "Priority": "high" if status != "success" else "default",
                    "Tags": "morphe,android,apk"
                }
                res = await client.post(url, data=message.encode("utf-8"), headers=headers)
                return res.status_code in (200, 201)

            if "discord.com/api/webhooks" in url:
                payload = {
                    "embeds": [
                        {
                            "title": f"{emoji} {title}",
                            "description": message,
                            "color": color,
                            "footer": {"text": "Morphe Patcher Headless"}
                        }
                    ]
                }
                res = await client.post(url, json=payload)
                return res.status_code in (200, 204)

            payload = {
                "title": f"{emoji} {title}",
                "message": message,
                "status": status,
                "priority": 5 if status == "success" else 8,
            }
            res = await client.post(url, json=payload)
            return res.is_success
    except Exception as e:
        logger.error(f"Failed to send notification to {url}: {e}")
        return False
