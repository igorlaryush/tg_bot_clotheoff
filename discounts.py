import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from google.cloud.firestore import SERVER_TIMESTAMP

import db

logger = logging.getLogger(__name__)

# ---------------- Public helpers ----------------
async def get_active_discount(user_id: int, package_id: str | None = None) -> Optional[Dict[str, Any]]:
    """Return active discount document for user if exists and not expired."""
    if not db.db:
        return None

    doc_ref = db.db.collection("user_discounts").document(str(user_id))
    snap = await doc_ref.get()
    if not snap.exists:
        return None

    data = snap.to_dict()
    if not data or data.get("status") != "active":
        return None

    if package_id:
        target_list = data.get("targetPackageIds") or data.get("targetPackageId")
        if target_list:
            if isinstance(target_list, list):
                if package_id not in target_list:
                    return None
            else:
                if target_list != package_id:
                    return None

    expires_at = data.get("expiresAt") or data.get("expires_at")
    if expires_at and expires_at < datetime.now(timezone.utc):
        # auto-expire
        try:
            await doc_ref.update({"status": "expired"})
        except Exception:
            pass
        return None

    return data

async def price_with_discount(original_price: int, discount: Optional[Dict[str, Any]]) -> int:
    if not discount:
        return original_price

    dtype = discount.get("discountType", "percentage")
    value = discount.get("discountValue", 0)

    if dtype == "percentage":
        return int(original_price * (100 - value) / 100)
    elif dtype == "fixed_amount":
        return max(0, int(original_price - value))
    return original_price

async def save_user_discount(
    user_id: int,
    policy_id: str,
    discount_type: str,
    discount_value: int,
    expires_at: datetime,
    package_ids: list[str],
):
    """Creates or overwrites discount document at user_discounts/{user_id}."""
    if not db.db:
        return False
    try:
        doc_ref = db.db.collection("user_discounts").document(str(user_id))
        data = {
            "userId": str(user_id),
            "policyId": policy_id,
            "discountType": discount_type,
            "discountValue": discount_value,
            "status": "active",
            "createdAt": SERVER_TIMESTAMP,
            "expiresAt": expires_at,
            "reminderSent": False,
            "targetPackageIds": package_ids,
        }
        await doc_ref.set(data)
        logger.info("Discount saved for user %s under policy %s", user_id, policy_id)
        return True
    except Exception as e:
        logger.exception("Failed to save discount for user %s: %s", user_id, e)
        return False

async def mark_reminder_sent(user_id: int):
    if not db.db:
        return
    try:
        await db.db.collection("user_discounts").document(str(user_id)).update({"reminderSent": True})
    except Exception:
        pass 

# Mark discount as used after a successful purchase
async def mark_used(user_id: int):
    if not db.db:
        return
    try:
        await db.db.collection("user_discounts").document(str(user_id)).update({"status": "used"})
    except Exception:
        pass 