import logging
from typing import Optional

try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False

logger = logging.getLogger(__name__)


def initialize_firebase(service_account_json_path: Optional[str] = None) -> bool:
    """
    Initialize Firebase Admin SDK.
    
    Args:
        service_account_json_path: Path to Firebase service account JSON file.
                                  If not provided, uses GOOGLE_APPLICATION_CREDENTIALS env var.
    
    Returns:
        bool: True if Firebase was initialized successfully
    """
    if not FIREBASE_AVAILABLE:
        logger.warning("[FIREBASE] firebase-admin not installed; push notifications disabled")
        return False
    
    if firebase_admin._apps:
        logger.info("[FIREBASE] Firebase already initialized")
        return True
    
    try:
        if service_account_json_path:
            cred = credentials.Certificate(service_account_json_path)
            firebase_admin.initialize_app(cred)
        else:
            # Uses GOOGLE_APPLICATION_CREDENTIALS environment variable
            firebase_admin.initialize_app()
        
        logger.info("[FIREBASE] Firebase Admin SDK initialized")
        return True
    except Exception as exc:
        logger.error(f"[FIREBASE] Failed to initialize Firebase: {exc}")
        return False


async def send_push_notification(
    fcm_token: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
    priority: str = "high",
) -> bool:
    """
    Send a push notification via Firebase Cloud Messaging.
    
    Args:
        fcm_token: Device's FCM token
        title: Notification title
        body: Notification body/message
        data: Optional dict with additional data to send
        priority: 'high' or 'normal' (high = wake up device)
        
    Returns:
        bool: True if notification was sent successfully
    """
    if not FIREBASE_AVAILABLE:
        logger.debug("[FIREBASE] firebase-admin not available; skipping notification")
        return False
    
    if not fcm_token:
        logger.warning("[FIREBASE] No FCM token provided")
        return False
    
    try:
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            android=messaging.AndroidConfig(
                priority=priority,
                notification=messaging.AndroidNotification(
                    title=title,
                    body=body,
                    click_action="FLUTTER_NOTIFICATION_CLICK",
                ),
            ),
        )
        
        response = messaging.send(message, dry_run=False)
        logger.info(f"[FIREBASE] Notification sent to {fcm_token[:20]}... Message ID: {response}")
        return True
        
    except Exception as exc:
        logger.error(f"[FIREBASE] Failed to send notification: {exc}")
        return False


async def send_multicast_notification(
    fcm_tokens: list[str],
    title: str,
    body: str,
    data: Optional[dict] = None,
    priority: str = "high",
) -> dict:
    """
    Send a notification to multiple devices.
    
    Args:
        fcm_tokens: List of FCM tokens
        title: Notification title
        body: Notification body
        data: Optional additional data
        priority: Notification priority
        
    Returns:
        dict: {success_count, failure_count, results}
    """
    if not FIREBASE_AVAILABLE or not fcm_tokens:
        return {"success_count": 0, "failure_count": len(fcm_tokens), "results": []}
    
    try:
        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            android=messaging.AndroidConfig(
                priority=priority,
                notification=messaging.AndroidNotification(
                    title=title,
                    body=body,
                    click_action="FLUTTER_NOTIFICATION_CLICK",
                ),
            ),
            tokens=fcm_tokens,
        )
        
        response = messaging.send_multicast(message)
        logger.info(
            f"[FIREBASE] Multicast sent to {len(fcm_tokens)} devices: "
            f"{response.success_count} successful, {response.failure_count} failed"
        )
        
        return {
            "success_count": response.success_count,
            "failure_count": response.failure_count,
            "results": [
                {
                    "success": resp.code == "success",
                    "message_id": resp.message_id if resp.code == "success" else None,
                    "error": str(resp.exception) if resp.exception else None,
                }
                for resp in response.responses
            ],
        }
        
    except Exception as exc:
        logger.error(f"[FIREBASE] Multicast send failed: {exc}")
        return {"success_count": 0, "failure_count": len(fcm_tokens), "results": []}
