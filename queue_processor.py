import logging
import asyncio
from telegram.ext import Application
from telegram.error import TelegramError

import bot_state # Очередь и ожидающие запросы
import db        # Функции БД

logger = logging.getLogger(__name__)

async def process_results_queue(app: Application):
    """Processes results from the Clothoff webhook queue."""
    logger.info("Result processing task started.")
    while True:
        try:
            # Ждем результат из очереди
            result = await bot_state.results_queue.get()
            id_gen = result.get("id_gen")

            if not id_gen:
                logger.warning("Received result from queue with missing id_gen.")
                bot_state.results_queue.task_done()
                continue

            logger.info(f"Dequeued result for id_gen: {id_gen}, status: {result.get('status')}")

            # Извлекаем информацию о запросе
            request_info = bot_state.pending_requests.pop(id_gen, None)
            if request_info is None:
                logger.warning(f"Received result for unknown or timed-out id_gen: {id_gen}. Discarding.")
                bot_state.results_queue.task_done()
                continue

            chat_id = request_info.get("chat_id")
            user_id = request_info.get("user_id")
            original_message_id = request_info.get("message_id") # ID исходного сообщения с фото
            status_message_id = request_info.get("status_message_id") # ID сообщения "Processing..."

            if not chat_id or not user_id:
                logger.error(f"Missing chat_id or user_id in pending_requests for id_gen: {id_gen}")
                bot_state.results_queue.task_done()
                continue

            status = result.get("status")
            image_data = result.get("image_data")
            error_message = result.get("error_message")
            processing_time = result.get("time_gen") # Время обработки от Clothoff

            # --- Отправка результата пользователю ---
            try:
                if status == '200' and image_data:
                    logger.info(f"Sending processed image for id_gen {id_gen} to chat_id {chat_id} (user: {user_id})")
                    caption = f"✅ Processed image (ID: {id_gen})."
                    if processing_time:
                        caption += f"\nProcessing time: {processing_time}s"

                    await app.bot.send_photo(
                        chat_id=chat_id,
                        photo=bytes(image_data),
                        caption=caption,
                        reply_to_message_id=original_message_id # Отвечаем на исходное сообщение
                    )
                    # Инкрементируем счетчик после *успешной* отправки
                    await db.increment_user_counter(user_id, "photos_processed")

                    # Удаляем сообщение "Processing..."
                    if status_message_id:
                        try:
                             await app.bot.delete_message(chat_id=chat_id, message_id=status_message_id)
                        except TelegramError as del_err:
                             logger.warning(f"Could not delete status message {status_message_id} for {id_gen}: {del_err}")

                else:
                    # Обработка не удалась
                    error_msg = error_message or f"Processing failed (status {status})."
                    logger.warning(f"Processing failed for id_gen {id_gen} (user {user_id}, chat {chat_id}): {error_msg}")

                    final_error_message = f"❌ Processing failed for image (ID: {id_gen}).\nReason: {error_msg}"

                    # Обновляем сообщение "Processing..." текстом ошибки или отправляем новое
                    if status_message_id:
                        try:
                            await app.bot.edit_message_text(
                                text=final_error_message,
                                chat_id=chat_id,
                                message_id=status_message_id
                            )
                        except TelegramError as edit_err:
                             logger.warning(f"Could not edit status message {status_message_id} for {id_gen} with error: {edit_err}. Sending new message.")
                             await app.bot.send_message(
                                chat_id=chat_id,
                                text=final_error_message,
                                reply_to_message_id=original_message_id
                             )
                    else: # Если вдруг статус-сообщения не было
                        await app.bot.send_message(
                            chat_id=chat_id,
                            text=final_error_message,
                            reply_to_message_id=original_message_id
                        )

            except TelegramError as send_err:
                logger.error(f"Failed to send result/error for id_gen {id_gen} to chat_id {chat_id} (user: {user_id}): {send_err}")
                # Попытка уведомить об ошибке отправки, если предыдущее не удалось
                if status != '200': # Только если была ошибка обработки
                     try:
                          await app.bot.send_message(chat_id=chat_id, text=f"Failed to deliver processing result for ID: {id_gen}. Error: {send_err}", reply_to_message_id=original_message_id)
                     except Exception as final_err:
                          logger.error(f"Also failed to send final error notification to chat_id {chat_id}: {final_err}")
            except Exception as e:
                 logger.exception(f"Unexpected error sending result for id_gen {id_gen} to {chat_id}: {e}")

            finally:
                # Обязательно помечаем задачу как выполненную
                bot_state.results_queue.task_done()
                logger.debug(f"Task done for id_gen: {id_gen}. Pending requests: {len(bot_state.pending_requests)}")

        except asyncio.CancelledError:
            logger.info("Result processing task cancelled.")
            break # Выходим из цикла при отмене
        except Exception as e:
            logger.exception(f"Critical error in results processing loop: {e}")
            # Добавляем небольшую задержку перед повторной попыткой в случае общей ошибки цикла
            await asyncio.sleep(5)