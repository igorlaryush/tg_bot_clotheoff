import logging
import binascii
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import httpx
import yaml
from nacl.bindings import crypto_sign, crypto_sign_BYTES
from nacl.signing import VerifyKey
from nacl.encoding import HexEncoder
from nacl.exceptions import BadSignatureError

import config
import db

logger = logging.getLogger(__name__)

# Загружаем пакеты из YAML файла
def load_payment_packages() -> Dict[str, Any]:
    """Загружает конфигурацию пакетов из YAML файла."""
    try:
        with open('payment_packages.yaml', 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data.get('packages', {})
    except Exception as e:
        logger.error(f"Ошибка загрузки пакетов платежей: {e}")
        return {}

PAYMENT_PACKAGES = load_payment_packages()

class StreamPayAPI:
    """Класс для работы с StreamPay API."""
    
    def __init__(self):
        self.api_base_url = config.STREAMPAY_API_URL
        self.store_id = config.STREAMPAY_STORE_ID
        
        # Проверяем и инициализируем приватный ключ
        if not config.STREAMPAY_PRIVATE_KEY:
            raise ValueError("STREAMPAY_PRIVATE_KEY is not set")
        
        try:
            private_key_hex = config.STREAMPAY_PRIVATE_KEY.strip()
            if len(private_key_hex) != 128:
                raise ValueError(f"Private key must be 128 hex characters (32 bytes), got {len(private_key_hex)}")
            self.private_key = binascii.unhexlify(private_key_hex)
        except (ValueError, binascii.Error) as e:
            raise ValueError(f"Invalid private key format: {e}")
        
        # Проверяем и инициализируем публичный ключ
        if not config.STREAMPAY_PUBLIC_KEY:
            raise ValueError("STREAMPAY_PUBLIC_KEY is not set")
            
        try:
            public_key_hex = config.STREAMPAY_PUBLIC_KEY.strip()
            if len(public_key_hex) != 64:
                raise ValueError(f"Public key must be 128 hex characters (64 bytes), got {len(public_key_hex)}")
            self.public_key = VerifyKey(public_key_hex, encoder=HexEncoder)
        except (ValueError, binascii.Error) as e:
            raise ValueError(f"Invalid public key format: {e}")
        
        logger.info("StreamPay API initialized successfully")
    
    def _generate_signature(self, content: str) -> str:
        """Генерирует подпись для запроса."""
        to_sign = content.encode('utf-8') + bytes(datetime.utcnow().strftime('%Y%m%d:%H%M'), 'ascii')
        signature = binascii.hexlify(crypto_sign(to_sign, self.private_key)[:crypto_sign_BYTES])
        return signature
    
    async def create_invoice(self, user_id: int, package_id: str, external_id: str) -> Optional[Dict[str, Any]]:
        """Создает инвойс для оплаты пакета."""
        if package_id not in PAYMENT_PACKAGES:
            logger.error(f"Неизвестный пакет: {package_id}")
            return None
        
        package = PAYMENT_PACKAGES[package_id]
        
        req_data = json.dumps({
            "store_id": self.store_id,
            "customer": str(user_id),
            "external_id": external_id,
            "description": f"Покупка пакета обработки фото - {package['name']['ru']}",
            "system_currency": "USDT",
            "payment_type": 1,
            'currency': "RUB", # Рубли
            "amount": package['price'],
            "success_url": f"{config.BASE_URL}/payment/success",
            "fail_url": f"{config.BASE_URL}/payment/fail",
            "cancel_url": f"{config.BASE_URL}/payment/cancel",
        })
        
        signature = self._generate_signature(req_data)
        
        headers = {
            'Content-Type': 'application/json',
            'Signature': signature
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f'{self.api_base_url}/api/payment/create',
                    content=req_data,
                    headers=headers
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"Инвойс создан для пользователя {user_id}, пакет {package_id}")
                    return result.get('data')
                else:
                    logger.error(f"Ошибка создания инвойса: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Ошибка при создании инвойса: {e}")
            return None
    
    def verify_callback_signature(self, query_params: str, signature_hex: str) -> bool:
        """Проверяет подпись callback запроса."""
        try:
            signature = binascii.unhexlify(signature_hex)
            now = datetime.utcnow()
            
            # Проверяем подпись для текущей и предыдущей минуты
            for i in range(2):
                check_time = now - timedelta(minutes=i)
                timestamp = check_time.strftime('%Y%m%d:%H%M')
                to_verify = query_params.encode('utf-8') + timestamp.encode('ascii')
                
                try:
                    self.public_key.verify(to_verify, signature)
                    return True
                except BadSignatureError:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка проверки подписи: {e}")
            return False

# Глобальный экземпляр API
streampay_api = None
# Инициализируем API только если все настройки доступны
if config.STREAMPAY_ENABLED:
    try:
        streampay_api = StreamPayAPI()
        logger.info("StreamPay API instance created successfully")
    except Exception as e:
        logger.error(f"Failed to initialize StreamPay API: {e}")
        streampay_api = None
else:
    logger.info("StreamPay API not initialized - missing configuration")

async def create_payment_order(user_id: int, package_id: str) -> Optional[Dict[str, Any]]:
    """Создает заказ на оплату и сохраняет его в БД."""
    if not streampay_api:
        logger.error("StreamPay API not available - cannot create payment order")
        return None

    external_id = f"order_{user_id}_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}"
    
    # Создаем инвойс через API
    invoice_data = await streampay_api.create_invoice(user_id, package_id, external_id)
    
    if not invoice_data:
        return None
    
    # Сохраняем заказ в БД
    order_data = {
        "external_id": external_id,
        "user_id": user_id,
        "package_id": package_id,
        "invoice_id": invoice_data.get('invoice'),
        "amount": PAYMENT_PACKAGES[package_id]['price'],
        "currency": PAYMENT_PACKAGES[package_id]['currency'],
        "photos_count": PAYMENT_PACKAGES[package_id]['photos'],
        "status": "pending",
        "created_at": datetime.utcnow(),
        "pay_url": invoice_data.get('pay_url')
    }
    
    success = await db.create_payment_order(order_data)
    if success:
        return order_data
    else:
        logger.error(f"Не удалось сохранить заказ в БД: {external_id}")
        return None

async def process_payment_callback(callback_data: Dict[str, str]) -> bool:
    """Обрабатывает callback от StreamPay."""
    external_id = callback_data.get('external_id')
    status = callback_data.get('status')
    invoice_id = callback_data.get('invoice')
    
    if not external_id or not status:
        logger.error("Отсутствуют обязательные поля в callback")
        return False
    
    # Получаем заказ из БД
    order = await db.get_payment_order_by_external_id(external_id)
    if not order:
        logger.error(f"Заказ не найден: {external_id}")
        return False
    
    # Обновляем статус заказа
    update_data = {
        "status": status,
        "updated_at": datetime.utcnow()
    }
    
    if status == "success":
        # Начисляем фото пользователю
        photos_to_add = order['photos_count']
        success = await db.add_user_photos(order['user_id'], photos_to_add)
        
        if success:
            update_data["processed"] = True
            logger.info(f"Пользователю {order['user_id']} начислено {photos_to_add} фото")
        else:
            logger.error(f"Ошибка начисления фото пользователю {order['user_id']}")
            return False
    
    # Обновляем заказ в БД
    success = await db.update_payment_order(external_id, update_data)
    
    if success:
        logger.info(f"Заказ {external_id} обновлен со статусом {status}")
        return True
    else:
        logger.error(f"Ошибка обновления заказа {external_id}")
        return False

def get_package_info(package_id: str, lang: str = 'ru') -> Optional[Dict[str, Any]]:
    """Возвращает информацию о пакете."""
    if package_id not in PAYMENT_PACKAGES:
        return None
    
    package = PAYMENT_PACKAGES[package_id]
    return {
        'id': package_id,
        'name': package['name'].get(lang, package['name']['en']),
        'description': package['description'].get(lang, package['description']['en']),
        'photos': package['photos'],
        'price': package['price'],
        'stars_price': package.get('stars_price'),
        'currency': package['currency'],
        'popular': package.get('popular', False)
    }

def get_all_packages(lang: str = 'ru') -> Dict[str, Dict[str, Any]]:
    """Возвращает все доступные пакеты."""
    result = {}
    for package_id in PAYMENT_PACKAGES:
        result[package_id] = get_package_info(package_id, lang)
    return result 