import logging
import asyncio
import uvicorn
from asgiref.wsgi import WsgiToAsgi

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    Application,
)

# Импортируем наши модули
import config
import db
import bot_state
import telegram_handlers
import webhooks
import queue_processor

# Логгер настраивается в config.py при импорте
logger = logging.getLogger(__name__)

async def main():
    """Initializes the bot, sets up handlers, webhooks, and runs the server."""

    # --- Initialize Firestore ---
    try:
        await db.init_db()
        if not db.db: # Дополнительная проверка после инициализации
             raise ConnectionError("Firestore client object is still None after init_db()")
    except Exception as db_err:
        logger.critical(f"Failed to initialize Firestore: {db_err}. Bot cannot start without DB.")
        return # Останавливаем запуск

    # --- Build PTB Application ---
    logger.info("Initializing PTB Application...")
    try:
        ptb_app = (
            ApplicationBuilder()
            .token(config.TELEGRAM_BOT_TOKEN)
            # .read_timeout(30) # Можно настроить таймауты
            # .write_timeout(30)
            .build()
        )
    except Exception as build_err:
        logger.critical(f"Failed to build PTB Application: {build_err}")
        return

    # --- Register Handlers ---
    ptb_app.add_handler(CommandHandler("start", telegram_handlers.start))
    ptb_app.add_handler(CommandHandler("help", telegram_handlers.help_command))
    ptb_app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, telegram_handlers.handle_photo))
    # Добавьте другие обработчики здесь, если нужно

    # --- Initialize PTB Application (starts internal processes) ---
    try:
        await ptb_app.initialize()
        logger.info("PTB Application initialized.")
    except Exception as init_err:
        logger.critical(f"Failed to initialize PTB Application: {init_err}")
        return

    # --- Set Bot Commands ---
    # Устанавливаем команды один раз при запуске
    await telegram_handlers.setup_bot_commands(ptb_app)

    # --- Set Telegram Webhook ---
    if not config.TELEGRAM_RECEIVER_URL:
        logger.error("TELEGRAM_RECEIVER_URL is not configured. Cannot set webhook.")
        return

    logger.info(f"Setting Telegram webhook to: {config.TELEGRAM_RECEIVER_URL}")
    try:
        await ptb_app.bot.set_webhook(
            url=config.TELEGRAM_RECEIVER_URL,
            allowed_updates=Update.ALL_TYPES, # Или укажите конкретные типы: [Update.MESSAGE, Update.CALLBACK_QUERY]
            secret_token=config.WEBHOOK_SECRET_PATH,
            drop_pending_updates=True # Сбрасываем старые обновления при перезапуске
        )
        logger.info("Telegram webhook set successfully.")
    except Exception as webhook_err:
        logger.error(f"Failed to set Telegram webhook: {webhook_err}")
        # Можно решить, продолжать ли без вебхука (например, для локального тестирования с polling),
        # но в текущей конфигурации вебхук необходим.
        await ptb_app.shutdown() # Корректно завершаем PTB
        return

    # --- Start Background Tasks ---
    # Запускаем задачу обработки очереди результатов
    results_task = asyncio.create_task(queue_processor.process_results_queue(ptb_app))
    logger.info("Clothoff result processing task scheduled.")

    # --- Start PTB Application (starts polling for updates if no webhook) ---
    # В режиме вебхука start() в основном запускает фоновые задачи PTB
    await ptb_app.start()
    logger.info("PTB Application background tasks started.")

    # --- Setup Flask App and Routes ---
    # Передаем ptb_app в функцию настройки вебхуков
    flask_app = webhooks.setup_routes(ptb_app)
    asgi_flask_app = WsgiToAsgi(flask_app) # Оборачиваем Flask для Uvicorn

    # --- Configure and Run Uvicorn Server ---
    uvicorn_config = uvicorn.Config(
        app=asgi_flask_app,
        host="0.0.0.0",
        port=config.WEBHOOK_PORT,
        log_level="info", # Логи Uvicorn
    )
    server = uvicorn.Server(uvicorn_config)

    logger.info(f"Starting Uvicorn server on port {config.WEBHOOK_PORT}...")
    logger.info(f"Telegram should send updates to: {config.TELEGRAM_RECEIVER_URL}")
    logger.info(f"Clothoff API should send results to: {config.CLOTHOFF_RECEIVER_URL}")
    logger.info(f"Using GCP Project ID for Firestore: {config.GCP_PROJECT_ID}")
    logger.info(f"Using Firestore Database: {config.FIRESTORE_DB_NAME}")

    # --- Run Server and Handle Shutdown ---
    try:
        # Запускаем сервер и ждем его завершения
        await server.serve()
    except (KeyboardInterrupt, SystemExit):
         logger.info("Shutdown signal received (KeyboardInterrupt/SystemExit).")
    finally:
        logger.info("Initiating graceful shutdown...")

        # 1. Останавливаем PTB Application (перестает принимать новые вебхуки/поллить)
        logger.info("Stopping PTB application...")
        await ptb_app.stop()

        # 2. Отменяем задачу обработки очереди
        logger.info("Cancelling result processing task...")
        results_task.cancel()
        try:
            # Ждем завершения задачи (или пока она не выбросит CancelledError)
            await results_task
        except asyncio.CancelledError:
            logger.info("Result processing task cancelled successfully.")
        except Exception as task_err:
             logger.error(f"Error during result processing task shutdown: {task_err}")

        # 3. Завершаем работу PTB Application (закрывает соединения и т.д.)
        logger.info("Shutting down PTB application...")
        await ptb_app.shutdown()

        # 4. Закрытие соединения с БД (если бы оно требовалось)
        # await db.close_db()

        logger.info("Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        # Ловим любые ошибки, которые могли произойти до или во время запуска asyncio.run()
        logger.critical(f"Application failed to run: {e}", exc_info=True)
    finally:
        logging.info("Application exited.")
