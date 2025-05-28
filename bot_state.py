import asyncio

# Очередь для результатов от Clothoff
results_queue = asyncio.Queue()

# Очередь для уведомлений о платежах
notifications_queue = asyncio.Queue()

# Словарь для отслеживания запросов: {id_gen: {"chat_id": ..., "user_id": ...}}
pending_requests = {}
