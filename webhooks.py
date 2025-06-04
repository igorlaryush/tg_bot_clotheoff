import logging
import json
import asyncio # Для asyncio.QueueFull и asyncio.sleep
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application
from telegram.error import Forbidden, BadRequest # Added for error handling

import config      # Для секретного пути Telegram
import bot_state   # Для очереди результатов
import payments    # Для обработки платежей
import db          # Для работы с базой данных
import localization # Added for localized messages

logger = logging.getLogger(__name__)

flask_app = Flask(__name__)
flask_app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # Ограничение размера запроса

# Эта функция будет вызвана из main.py для передачи Application
def setup_routes(ptb_app: Application):

    @flask_app.route(f"/{config.WEBHOOK_SECRET_PATH}", methods=['POST'])
    async def telegram_webhook_handler():
        """Handles incoming Telegram updates."""
        if ptb_app is None:
            logger.error("PTB Application not initialized in webhook handler.")
            return jsonify({"error": "Bot not ready"}), 503

        try:
            update_data = request.get_json(force=True) # force=True может помочь с некоторыми прокси
        except Exception as json_err:
             logger.error(f"Failed to decode JSON from Telegram: {json_err}. Body: {request.data[:200]}") # Логируем начало тела запроса
             return jsonify({"error": "Bad Request: Invalid JSON"}), 400

        if not update_data:
            logger.warning("Received empty payload from Telegram.")
            return jsonify({"error": "Bad Request: Empty payload"}), 400

        logger.debug(f"Telegram webhook received: {json.dumps(update_data)}") # Не логгируем всё тело по умолчанию

        try:
            update = Update.de_json(update_data, ptb_app.bot)
            # Используем встроенный метод PTB для обработки обновления в очереди
            await ptb_app.process_update(update)
            return jsonify({"ok": True}), 200
        except Exception as e:
            logger.exception(f"Error processing Telegram update in webhook: {e}")
            # Важно вернуть 200 OK, чтобы Telegram не повторял отправку
            return jsonify({"ok": f"Error processing update: {e}"}), 200

    @flask_app.route('/webhook', methods=['POST'])
    def clothoff_webhook_handler():
        """Handles incoming results from API."""
        content_type = request.content_type or ''
        if 'multipart/form-data' not in content_type:
            logger.warning(f"Clothoff: Received non-multipart request: {content_type}")
            return jsonify({"error": "Bad Request: Expected multipart/form-data"}), 400

        try:
            status = request.form.get('status')
            id_gen = request.form.get('id_gen')
            time_gen = request.form.get('time_gen')
            res_image_file = request.files.get('res_image')
            img_message = request.form.get('img_message') # Сообщение об ошибке от Clothoff

            logger.info(f"Clothoff Webhook received for id_gen: {id_gen}, status: {status}")

            if not id_gen:
                logger.error("Missing 'id_gen' in Clothoff webhook form data.")
                raise ValueError("Missing 'id_gen' in Clothoff webhook data")

            result_data = {
                "id_gen": id_gen,
                "status": status,
                "image_data": None,
                "error_message": None,
                "time_gen": time_gen
            }

            if status == '200' and res_image_file:
                if not res_image_file.filename:
                     logger.warning(f"Clothoff: 'res_image' file received for {id_gen} but has no filename.")
                     # Можно или проигнорировать, или считать ошибкой
                     # raise ValueError("'res_image' received but has no filename")

                image_bytes = res_image_file.read()
                if not image_bytes:
                     logger.warning(f"Clothoff: 'res_image' file received for {id_gen} but is empty.")
                     result_data["status"] = '500' # Считаем это ошибкой
                     result_data["error_message"] = "Received empty image file from Clothoff."
                else:
                    result_data["image_data"] = image_bytes
                    logger.info(f"Clothoff: Received image for id_gen: {id_gen}, size: {len(image_bytes)} bytes")

            elif status != '200':
                result_data["error_message"] = img_message or f"Unknown error from Clothoff (status {status})"
                logger.warning(f"Clothoff: Error status for id_gen {id_gen}: {status} - {result_data['error_message']}")
            # Случай status == '200' но нет res_image_file (или он пустой и обработан выше)
            elif status == '200' and not result_data["image_data"]:
                 logger.error(f"Clothoff: Status 200 for {id_gen} but 'res_image' file is missing or was empty.")
                 result_data["status"] = '500' # Считаем ошибкой
                 result_data["error_message"] = "Clothoff reported success (200) but did not provide an image file."


            # Помещаем результат в очередь (используя bot_state)
            try:
                bot_state.results_queue.put_nowait(result_data)
                logger.debug(f"Clothoff: Successfully put result for {id_gen} onto the queue. Queue size: {bot_state.results_queue.qsize()}")
            except asyncio.QueueFull:
                logger.error(f"Result queue is full! Dropping Clothoff result for id_gen: {id_gen}")
                # Важно вернуть ошибку, чтобы Clothoff, возможно, попробовал снова (если он так умеет)
                return jsonify({"error": "Internal server error: Processing queue full"}), 503
            except Exception as q_err:
                logger.exception(f"Error putting Clothoff result onto queue for id_gen {id_gen}: {q_err}")
                return jsonify({"error": "Internal server error: Failed to queue result"}), 500

            return jsonify({"message": "Clothoff webhook received successfully"}), 200

        except ValueError as ve:
            logger.error(f"Invalid Clothoff webhook data: {ve}")
            return jsonify({"error": f"Bad Request: {ve}"}), 400
        except Exception as e:
            logger.exception(f"Unexpected error processing Clothoff webhook: {e}")
            return jsonify({"error": "Internal Server Error"}), 500

    @flask_app.route('/payment/callback', methods=['GET'])
    async def streampay_callback_handler():
        """Handles payment callbacks from StreamPay."""
        if not config.STREAMPAY_ENABLED:
            logger.warning("StreamPay callback received but StreamPay is not enabled")
            return jsonify({"error": "StreamPay not enabled"}), 503

        try:
            # Получаем все query параметры
            query_params = dict(request.args)
            signature = request.headers.get('Signature')
            
            if not signature:
                logger.error("StreamPay callback: Missing Signature header")
                return jsonify({"error": "Missing signature"}), 400

            # Формируем строку для проверки подписи
            sorted_params = sorted(query_params.items())
            query_string = '&'.join(f'{k}={v}' for k, v in sorted_params)
            
            logger.info(f"StreamPay callback received: {query_string}")
            
            # Проверяем подпись
            if not payments.streampay_api.verify_callback_signature(query_string, signature):
                logger.error(f"StreamPay callback: Invalid signature for params: {query_string}")
                return jsonify({"error": "Invalid signature"}), 403

            # Обрабатываем callback
            success = await payments.process_payment_callback(query_params)
            
            if success:
                # Если платеж успешен, уведомляем пользователя
                if query_params.get('status') == 'success':
                    external_id = query_params.get('external_id')
                    if external_id:
                        # Получаем информацию о заказе для уведомления
                        order = await db.get_payment_order_by_external_id(external_id)
                        if order and order.get('processed'):
                            package_info = payments.get_package_info(order['package_id'], 'ru')  # Используем русский по умолчанию
                            if package_info:
                                new_balance = await db.get_user_photos_balance(order['user_id'])
                                # Уведомляем пользователя (это нужно будет адаптировать)
                                try:
                                    from telegram_handlers import notify_payment_success
                                    await notify_payment_success(
                                        order['user_id'],
                                        package_info['name'],
                                        order['photos_count'],
                                        new_balance
                                    )
                                except Exception as notify_err:
                                    logger.error(f"Failed to notify user about payment success: {notify_err}")
                
                return jsonify({"message": "Callback processed successfully"}), 200
            else:
                return jsonify({"error": "Failed to process callback"}), 500

        except Exception as e:
            logger.exception(f"Unexpected error processing StreamPay callback: {e}")
            return jsonify({"error": "Internal Server Error"}), 500

    @flask_app.route('/payment/success', methods=['GET'])
    def payment_success_page():
        """Страница успешной оплаты."""
        return """
        <html>
        <head><title>Payment Successful</title></head>
        <body>
            <h1>✅ Payment Successful!</h1>
            <p>Your payment has been processed successfully. You can now return to the Telegram bot.</p>
            <script>
                setTimeout(function() {
                    window.close();
                }, 3000);
            </script>
        </body>
        </html>
        """

    @flask_app.route('/payment/fail', methods=['GET'])
    def payment_fail_page():
        """Страница неудачной оплаты."""
        return """
        <html>
        <head><title>Payment Failed</title></head>
        <body>
            <h1>❌ Payment Failed</h1>
            <p>Your payment could not be processed. Please try again or contact support.</p>
            <script>
                setTimeout(function() {
                    window.close();
                }, 3000);
            </script>
        </body>
        </html>
        """

    @flask_app.route('/payment/cancel', methods=['GET'])
    def payment_cancel_page():
        """Страница отмененной оплаты."""
        return """
        <html>
        <head><title>Payment Cancelled</title></head>
        <body>
            <h1>❌ Payment Cancelled</h1>
            <p>Your payment has been cancelled. You can try again anytime.</p>
            <script>
                setTimeout(function() {
                    window.close();
                }, 3000);
            </script>
        </body>
        </html>
        """

    @flask_app.route('/scheduler/send_notifications', methods=['POST'])
    async def scheduler_send_notifications_handler():
        """Handles scheduled requests to send notifications to all users."""

        scheduler_token = request.headers.get('X-Scheduler-Token')
        if not scheduler_token or scheduler_token != getattr(config, 'SCHEDULER_SECRET_TOKEN', None):
            logger.warning("Unauthorized attempt to access /scheduler/send_notifications")
            return jsonify({"error": "Unauthorized"}), 401

        if ptb_app is None:
            logger.error("PTB Application not initialized in scheduler notification handler.")
            return jsonify({"error": "Bot not ready"}), 503

        logger.info("Scheduler: Received request to send notifications.")
        
        try:
            users = await db.get_all_users()
            if not users:
                logger.info("Scheduler: No users found to send notifications to.")
                return jsonify({"message": "No users to notify"}), 200

            # notification_message = "Hello! This is a scheduled notification from your bot."
            # You can customize this message or fetch it from config/db

            success_count = 0
            failure_count = 0

            for user in users:
                chat_id = user.get("chat_id")
                user_id = user.get("user_id")
                user_lang = user.get("language", localization.DEFAULT_LANG) # Get user's language, fallback to default

                if not chat_id:
                    logger.warning(f"Scheduler: User {user_id} missing chat_id, skipping notification.")
                    failure_count += 1
                    continue
                
                notification_message = localization.get_text("scheduled_notification_promo", user_lang)

                try:
                    with open("images/notification_image.png", "rb") as photo_file:
                        await ptb_app.bot.send_photo(
                            chat_id=chat_id,
                            photo=photo_file,
                            caption=notification_message
                        )
                    logger.debug(f"Scheduler: Successfully sent notification photo to user {user_id} (chat_id {chat_id}, lang: {user_lang})")
                    success_count += 1
                except Forbidden:
                    logger.warning(f"Scheduler: Bot was blocked by user {user_id} (chat_id {chat_id}). Cannot send notification.")
                    failure_count += 1
                    # Optionally, mark user as inactive in DB
                except BadRequest as br_err:
                    logger.warning(f"Scheduler: Bad request sending to user {user_id} (chat_id {chat_id}): {br_err}")
                    failure_count += 1
                    # Optionally, mark chat_id as invalid
                except Exception as e:
                    logger.error(f"Scheduler: Failed to send notification to user {user_id} (chat_id {chat_id}): {e}", exc_info=True)
                    failure_count += 1
                finally:
                    await asyncio.sleep(0.05) # Add a small delay to avoid hitting rate limits
            
            logger.info(f"Scheduler: Notification sending complete. Success: {success_count}, Failures: {failure_count}")
            return jsonify({
                "message": "Notification process completed.",
                "sent_count": success_count,
                "failed_count": failure_count
            }), 200

        except Exception as e:
            logger.exception(f"Scheduler: Error during send_notifications_handler: {e}")
            return jsonify({"error": "Internal Server Error while processing notifications"}), 500

    # Возвращаем настроенное приложение Flask
    return flask_app
