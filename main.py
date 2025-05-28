# from google.cloud import firestore


# async def main():
#     db = firestore.AsyncClient(
#         project="tg-bot-clotheoff-prod",
#         database="undress-tg-bot-prod"
#     )
#     print("Firestore client initialized successfully.")
#     test_query = db.collection('users').limit(1)
#     print("Test query initialized successfully.")
#     try:
#         print(1)
#         result = await test_query.get()
#         print(dir(result[0]))
#         print(2)
#         print(result[0].to_dict())
#         print(3)
#         print(result[0].id)
#         print("Test query executed successfully.")
#     except Exception as e:
#         print(f"Error during test query execution: {e}")

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
    CallbackQueryHandler,
)

import config
import db
import telegram_handlers
import webhooks
import queue_processor

# Логгер настраивается в config.py при импорте
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

async def main():
    """Initializes the bot, sets up handlers, webhooks, and runs the server."""

    essential_vars_for_startup = {
        "TELEGRAM_BOT_TOKEN": config.TELEGRAM_BOT_TOKEN,
        "CLOTHOFF_API_KEY": config.CLOTHOFF_API_KEY,
        "GCP_PROJECT_ID": config.GCP_PROJECT_ID,
        "WEBHOOK_SECRET_PATH": config.WEBHOOK_SECRET_PATH,
    }

    missing_essential_vars = [k for k, v in essential_vars_for_startup.items() if not v]
    if missing_essential_vars:
        logger.critical(f"Missing essential environment variables: {', '.join(missing_essential_vars)}. "
                        f"Configure these in Secret Manager and connect to Cloud Run.")
        raise EnvironmentError(f"Missing essential environment variables: {', '.join(missing_essential_vars)}")


    logger.info("Essential configuration validated successfully.")

    try:
        await db.init_db()
        if not db.db:
             raise ConnectionError("Firestore client object is still None after init_db()")
        logger.info("Firestore initialized successfully.")
    except Exception as db_err:
        logger.critical(f"Failed to initialize Firestore: {db_err}. Bot cannot start without DB features.", exc_info=True)

    logger.info("Initializing PTB Application...")
    try:
        ptb_app = (
            ApplicationBuilder()
            .token(config.TELEGRAM_BOT_TOKEN)
            .build()
        )
        logger.info("PTB Application built.")
    except Exception as build_err:
        logger.critical(f"Failed to build PTB Application: {build_err}", exc_info=True)
        return

    logger.info("Registering handlers...")
    ptb_app.add_handler(CommandHandler("start", telegram_handlers.start))
    ptb_app.add_handler(CommandHandler("help", telegram_handlers.help_command))
    ptb_app.add_handler(CommandHandler("settings", telegram_handlers.settings_command))
    ptb_app.add_handler(CommandHandler("balance", telegram_handlers.balance_command))
    ptb_app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, telegram_handlers.handle_photo))
    ptb_app.add_handler(CallbackQueryHandler(telegram_handlers.handle_callback_query))
    # Добавьте другие обработчики здесь, если нужно
    logger.info("Handlers registered.")

    try:
        await ptb_app.initialize()
        logger.info("PTB Application initialized.")
    except Exception as init_err:
        logger.critical(f"Failed to initialize PTB Application: {init_err}", exc_info=True)

    logger.info("Setting bot commands...")
    try:
        await telegram_handlers.setup_bot_commands(ptb_app)
        logger.info("Bot commands set.")
    except Exception as cmd_err:
        logger.error(f"Failed to set bot commands: {cmd_err}", exc_info=True)

    if not config.TELEGRAM_RECEIVER_URL:
        logger.warning("Telegram webhook URL is not configured (BASE_URL is missing). Skipping set_webhook.")
    else:
        logger.info(f"Setting Telegram webhook to: {config.TELEGRAM_RECEIVER_URL}")
        try:
            await ptb_app.bot.set_webhook(
                url=config.TELEGRAM_RECEIVER_URL,
                allowed_updates=Update.ALL_TYPES,
                secret_token=config.WEBHOOK_SECRET_PATH,
                drop_pending_updates=True
            )
            logger.info("Telegram webhook set successfully.")
        except Exception as webhook_err:
            logger.error(f"Failed to set Telegram webhook: {webhook_err}", exc_info=True)

    logger.info("Scheduling Clothoff result processing task...")
    results_task = asyncio.create_task(queue_processor.process_results_queue(ptb_app))
    logger.info("Clothoff result processing task scheduled.")

    logger.info("Scheduling notifications processing task...")
    notifications_task = asyncio.create_task(queue_processor.process_notifications_queue(ptb_app))
    logger.info("Notifications processing task scheduled.")

    await ptb_app.start()
    logger.info("PTB Application background tasks started.")

    logger.info("Setting up Flask/Webhook routes...")
    flask_app = webhooks.setup_routes(ptb_app)
    asgi_flask_app = WsgiToAsgi(flask_app)
    logger.info("Flask app and routes setup complete.")

    uvicorn_config = uvicorn.Config(
        app=asgi_flask_app,
        host="0.0.0.0",
        port=config.PORT,
        log_level="info",
    )
    server = uvicorn.Server(uvicorn_config)

    logger.info(f"Starting Uvicorn server on port {config.PORT}...") # Логируем правильный порт
    logger.info(f"Telegram webhook target configured: {config.TELEGRAM_RECEIVER_URL if config.TELEGRAM_RECEIVER_URL else 'URL not set yet, set_webhook skipped'}")
    logger.info(f"Clothoff webhook target configured: {config.CLOTHOFF_RECEIVER_URL if config.CLOTHOFF_RECEIVER_URL else 'URL not set yet'}")
    logger.info(f"Using GCP Project ID for Firestore: {config.GCP_PROJECT_ID}") # GCP_PROJECT_ID проверен
    logger.info(f"Using Firestore Database: {config.FIRESTORE_DB_NAME}")

    try:
        await server.serve()
    except (KeyboardInterrupt, SystemExit):
         logger.info("Shutdown signal received (KeyboardInterrupt/SystemExit).")
    except Exception as server_err:
         logger.critical(f"Uvicorn server failed: {server_err}", exc_info=True)
    finally:
        logger.info("Initiating graceful shutdown...")

        logger.info("Stopping PTB application...")
        try:
             await ptb_app.stop()
        except Exception as e:
             logger.error(f"Error during PTB stop: {e}")


        logger.info("Cancelling result processing task...")
        results_task.cancel()
        try:
            # Ждем завершения задачи (или пока она не выбросит CancelledError)
            await results_task
        except asyncio.CancelledError:
            logger.info("Result processing task cancelled successfully.")
        except Exception as task_err:
             logger.error(f"Error during result processing task shutdown: {task_err}")

        logger.info("Cancelling notifications processing task...")
        notifications_task.cancel()
        try:
            await notifications_task
        except asyncio.CancelledError:
            logger.info("Notifications processing task cancelled successfully.")
        except Exception as task_err:
             logger.error(f"Error during notifications processing task shutdown: {task_err}")

        logger.info("Shutting down PTB application...")
        try:
             await ptb_app.shutdown()
        except Exception as e:
             logger.error(f"Error during PTB shutdown: {e}")

        logger.info("Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Application failed to run or crashed during startup: {e}", exc_info=True)
    finally:
        logging.info("Application exited.")
