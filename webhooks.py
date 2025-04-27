import logging
import json
import asyncio # Для asyncio.QueueFull
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application

import config      # Для секретного пути Telegram
import bot_state   # Для очереди результатов

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
        """Handles incoming results from Clothoff API."""
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

    # Возвращаем настроенное приложение Flask
    return flask_app
