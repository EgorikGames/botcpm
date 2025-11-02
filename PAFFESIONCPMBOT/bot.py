import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
import asyncio
from datetime import datetime, timedelta

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация (твои данные)
BOT_TOKEN = "8286753286:AAFk5h_iNiBEkRKmGgCcHsfZx1_N6lnhmoQ"
CHANNEL_ID = "@PAFFESIONCPM"
ADMIN_ID = 6747805355

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Инициализация БД
def init_db():
    conn = sqlite3.connect('submissions.db')
    cursor = conn.cursor()
    
    # Таблица заявок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            photo_file_id TEXT,
            caption TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица пользователей для статистики
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            submissions_count INTEGER DEFAULT 0,
            published_count INTEGER DEFAULT 0,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

# Функция для обновления статистики пользователя
async def update_user_stats(user: types.User):
    conn = sqlite3.connect('submissions.db')
    cursor = conn.cursor()
    
    # Проверяем существует ли пользователь
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user.id,))
    existing_user = cursor.fetchone()
    
    if existing_user:
        # Обновляем последнюю активность
        cursor.execute(
            'UPDATE users SET last_active = ?, username = ? WHERE user_id = ?',
            (datetime.now(), user.username, user.id)
        )
    else:
        # Добавляем нового пользователя
        cursor.execute(
            'INSERT INTO users (user_id, username, first_name, last_name, first_seen) VALUES (?, ?, ?, ?, ?)',
            (user.id, user.username, user.first_name, user.last_name, datetime.now())
        )
    
    conn.commit()
    conn.close()

# Функция для увеличения счетчика заявок
async def increment_submission_count(user_id: int):
    conn = sqlite3.connect('submissions.db')
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET submissions_count = submissions_count + 1 WHERE user_id = ?',
        (user_id,)
    )
    conn.commit()
    conn.close()

# Функция для увеличения счетчика опубликованных работ
async def increment_published_count(user_id: int):
    conn = sqlite3.connect('submissions.db')
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET published_count = published_count + 1 WHERE user_id = ?',
        (user_id,)
    )
    conn.commit()
    conn.close()

# Команда /start
@dp.message(Command("start"))
async def start_command(message: types.Message):
    await update_user_stats(message.from_user)
    await message.answer(
        "📸 Привет! Присылай сюда крутые винилы из Car Parking Multiplayer.\n\n"
        "Просто загрузи фото (скриншот или фото экрана) и добавь описание если хочешь."
    )

# Команда /stats - статистика для админа
@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Эта команда только для администратора")
        return
    
    conn = sqlite3.connect('submissions.db')
    cursor = conn.cursor()
    
    try:
        # Общая статистика
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM submissions')
        total_submissions = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM submissions WHERE status = "published"')
        published_submissions = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM submissions WHERE status = "pending"')
        pending_submissions = cursor.fetchone()[0]
        
        # Активные пользователи за последние 7 дней
        week_ago = datetime.now() - timedelta(days=7)
        cursor.execute('SELECT COUNT(*) FROM users WHERE last_active > ?', (week_ago,))
        active_users = cursor.fetchone()[0]
        
        # Топ пользователей по публикациям
        cursor.execute('''
            SELECT username, published_count, submissions_count 
            FROM users 
            WHERE published_count > 0 
            ORDER BY published_count DESC 
            LIMIT 10
        ''')
        top_users = cursor.fetchall()
        
        stats_text = f"""
📊 **Статистика бота**

👥 **Пользователи:**
• Всего пользователей: {total_users}
• Активных за неделю: {active_users}

📨 **Заявки:**
• Всего заявок: {total_submissions}
• Опубликовано: {published_submissions}
• На модерации: {pending_submissions}

🏆 **Топ авторов:**
"""
        
        if top_users:
            for i, (username, published, total) in enumerate(top_users, 1):
                display_name = f"@{username}" if username else "Без username"
                stats_text += f"{i}. {display_name} - {published} публикаций\n"
        else:
            stats_text += "Пока нет публикаций"
        
        await message.answer(stats_text)
        
    except Exception as e:
        logger.error(f"Ошибка в stats: {e}")
        await message.answer(f"❌ Ошибка при получении статистики: {e}")
    finally:
        conn.close()

# Команда /broadcast - рассылка для админа
@dp.message(Command("broadcast"))
async def broadcast_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Эта команда только для администратора")
        return
    
    # Проверяем есть ли текст рассылки
    if not message.reply_to_message:
        await message.answer("❌ Ответь этой командой на сообщение для рассылки")
        return
    
    broadcast_message = message.reply_to_message
    
    conn = sqlite3.connect('submissions.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT user_id FROM users')
        users = cursor.fetchall()
        total_users = len(users)
        
        if total_users == 0:
            await message.answer("❌ Нет пользователей для рассылки")
            return
            
        successful = 0
        failed = 0
        
        status_msg = await message.answer(f"🔄 Рассылка начата... 0/{total_users}")
        
        for user_id, in users:
            try:
                # Копируем сообщение пользователю
                await bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=message.chat.id,
                    message_id=broadcast_message.message_id
                )
                successful += 1
            except Exception as e:
                failed += 1
                logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
            
            # Обновляем статус каждые 10 отправок
            if (successful + failed) % 10 == 0:
                await status_msg.edit_text(
                    f"🔄 Рассылка... {successful + failed}/{total_users}\n"
                    f"✅ Успешно: {successful}\n"
                    f"❌ Ошибок: {failed}"
                )
            
            # Небольшая задержка чтобы не спамить
            await asyncio.sleep(0.1)
        
        await status_msg.edit_text(
            f"✅ Рассылка завершена!\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"✅ Успешно: {successful}\n"
            f"❌ Ошибок: {failed}"
        )
        
    except Exception as e:
        logger.error(f"Ошибка в broadcast: {e}")
        await message.answer(f"❌ Ошибка рассылки: {e}")
    finally:
        conn.close()

# Обработка фото
@dp.message(F.photo)
async def handle_photo(message: types.Message):
    try:
        user = message.from_user
        photo_file_id = message.photo[-1].file_id
        caption = message.caption or ""
        
        await update_user_stats(user)
        logger.info(f"Получено фото от @{user.username}")

        # Сохраняем в БД
        conn = sqlite3.connect('submissions.db')
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO submissions (user_id, username, photo_file_id, caption) VALUES (?, ?, ?, ?)',
            (user.id, user.username, photo_file_id, caption)
        )
        submission_id = cursor.lastrowid
        conn.commit()
        conn.close()

        await increment_submission_count(user.id)

        # Создаем кнопки для модерации
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"publish_{submission_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{submission_id}")
            ]
        ])

        # Текст для админа
        admin_text = f"🆕 Новая заявка #{submission_id}\n"
        if caption:
            admin_text += f"📝 Описание: {caption}\n"
        admin_text += f"👤 От: @{user.username if user.username else 'N/A'}"

        # Отправляем админу
        await bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo_file_id,
            caption=admin_text,
            reply_markup=keyboard
        )
        
        await message.answer("✅ Фото отправлено на модерацию! Ожидай публикации в канале.")
        logger.info(f"Заявка #{submission_id} отправлена админу")

    except Exception as e:
        logger.error(f"Ошибка в handle_photo: {e}")
        await message.answer("❌ Произошла ошибка. Попробуй еще раз.")

# Обработка кнопки "Опубликовать"
@dp.callback_query(F.data.startswith("publish_"))
async def publish_handler(callback: types.CallbackQuery):
    try:
        submission_id = int(callback.data.split('_')[1])
        logger.info(f"Публикация заявки #{submission_id}")
        
        # Получаем данные из БД
        conn = sqlite3.connect('submissions.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM submissions WHERE id = ?', (submission_id,))
        submission = cursor.fetchone()
        
        if not submission:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        user_id, username, photo_file_id, caption, status = submission[1], submission[2], submission[3], submission[4], submission[5]
        
        original_caption = caption if caption else ""
        final_caption = f"{original_caption}\n\n➖➖➖➖➖➖➖➖➖➖\n⭐️ Хочешь тоже быть в топе? Присылай свой винил!"

        # Создаем кнопку для канала
        channel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📸 Прислать свой винил", 
                url=f"https://t.me/{(await bot.get_me()).username}?start=submit"
            )]
        ])

        # Публикуем в канал
        await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=photo_file_id,
            caption=final_caption,
            reply_markup=channel_keyboard
        )
        
        # Обновляем статус
        cursor.execute('UPDATE submissions SET status = "published" WHERE id = ?', (submission_id,))
        await increment_published_count(user_id)
        conn.commit()
        conn.close()
        
        # Удаляем клавиатуру у оригинального сообщения
        await callback.message.edit_reply_markup(reply_markup=None)
        
        # Отправляем отдельное сообщение о успехе
        await callback.message.answer(f"✅ Заявка #{submission_id} опубликована в канале!")
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                chat_id=user_id,
                text="🎉 Твой винил опубликован в канале! Смотри: @PAFFESIONCPM"
            )
        except:
            logger.warning(f"Не удалось уведомить пользователя {user_id}")
        
        await callback.answer("✅ Опубликовано!")
        logger.info(f"Заявка #{submission_id} успешно опубликована")
        
    except Exception as e:
        logger.error(f"Ошибка в publish_handler: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

# Обработка кнопки "Отклонить"
@dp.callback_query(F.data.startswith("reject_"))
async def reject_handler(callback: types.CallbackQuery):
    try:
        submission_id = int(callback.data.split('_')[1])
        logger.info(f"Отклонение заявки #{submission_id}")
        
        conn = sqlite3.connect('submissions.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE submissions SET status = "rejected" WHERE id = ?', (submission_id,))
        conn.commit()
        conn.close()
        
        # Удаляем клавиатуру у оригинального сообщения
        await callback.message.edit_reply_markup(reply_markup=None)
        
        # Отправляем отдельное сообщение об отклонении
        await callback.message.answer(f"❌ Заявка #{submission_id} отклонена")
        
        await callback.answer("❌ Отклонено!")
        
    except Exception as e:
        logger.error(f"Ошибка в reject_handler: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

# Запуск бота
async def main():
    init_db()
    logger.info("Бот запускается...")
    
    # Проверяем, что бот работает
    bot_info = await bot.get_me()
    logger.info(f"Бот @{bot_info.username} успешно запущен!")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())




    import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_bot():
    bot = Bot(token="YOUR_BOT_TOKEN")
    dp = Dispatcher()
    
    while True:
        try:
            logger.info("🔄 Запуск бота...")
            bot_info = await bot.get_me()
            logger.info(f"✅ Бот @{bot_info.username} запущен!")
            
            await dp.start_polling(bot)
            
        except TelegramNetworkError as e:
            logger.error(f"📡 Ошибка сети: {e}")
            logger.info("🔄 Перезапуск через 5 секунд...")
            await asyncio.sleep(5)
            
        except TelegramRetryAfter as e:
            logger.warning(f"⏳ Лимит запросов, ждем {e.retry_after} сек...")
            await asyncio.sleep(e.retry_after)
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            logger.info("🔄 Перезапуск через 10 секунд...")
            await asyncio.sleep(10)

# Запуск
if __name__ == "__main__":
    asyncio.run(run_bot())