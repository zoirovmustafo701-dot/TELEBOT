import telebot
from telebot import types, formatting
from google import genai
import time
import os
from flask import Flask
from threading import Thread
from pymongo import MongoClient # Библиотека для базы данных

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MONGO_URI = os.environ.get("MONGO_URI", "") # Ссылка на базу данных

bot = telebot.TeleBot(BOT_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)

# --- ПОДКЛЮЧЕНИЕ К MONGODB ---
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["oisha_shop_db"]
    collection = db["tovary"]
    print("Успешное подключение к базе данных MongoDB!")
except Exception as e:
    print(f"ОШИБКА ПОДКЛЮЧЕНИЯ К БАЗЕ: {e}")

# --- МИНИ-САЙТ ДЛЯ RENDER ---
app = Flask('')
@app.route('/')
def home():
    return "Bot Oisha Shop is alive!"
def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# --- ОСТАЛЬНОЙ КОД ---
MODELS = ['gemini-3.5-flash-lite', 'gemini-3.6-flash', 'gemini-3.5-flash', 'gemini-flash-latest']

SYSTEM_PROMPT = """
Ты — вежливый и умный консультант магазина одежды "Oisha Shop".
Отвечай кратко, дружелюбно на русском и таджикском языке. 
Если клиент спрашивает про заказ, говори: "Зайдите на наш Instagram @oisha_shop_1989 и напишите в Direct".
"""

user_states = {} 

def set_commands():
    commands = [
        types.BotCommand("start", "Запустить бота 🚀"),
        types.BotCommand("catalog", "Каталог товаров 🛍️"),
        types.BotCommand("admin", "Админка 🛠️"),
        types.BotCommand("delete", "Удалить товар ❌"),
        types.BotCommand("cancel", "Отменить действие 🛑"),
        types.BotCommand("help", "Помощь ⚠️")
    ]
    bot.set_my_commands(commands)
set_commands()

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С БАЗОЙ ДАННЫХ ---
def get_all_items():
    items = {}
    for item in collection.find():
        items[item["_id"]] = {
            "price": item["price"], 
            "photo": item.get("photo", ""), 
            "is_doc": item.get("is_doc", False)
        }
    return items

def add_item_to_db(nazvanie, cena, photo_id="", is_doc=False):
    collection.update_one(
        {"_id": nazvanie},
        {"$set": {"price": cena, "photo": photo_id, "is_doc": is_doc}},
        upsert=True
    )

def delete_item_from_db(nazvanie):
    collection.delete_one({"_id": nazvanie})

# --- КОМАНДЫ ---

@bot.message_handler(commands=['start'])
def start_message(message):
    user_states[message.chat.id] = None 
    bot.reply_to(message, "Здравствуйте! Добро пожаловать в Oisha Shop! 👗 Я ваш ИИ-помощник. Нажмите 'Меню', чтобы увидеть команды.")

@bot.message_handler(commands=['catalog'])
def catalog_message(message):
    user_states[message.chat.id] = None
    magazin = get_all_items()
    if not magazin:
        bot.reply_to(message, "Каталог пока пуст.")
        return
    
    text = "📦 <b>Наш каталог:</b>\n\n"
    for tovar, data in magazin.items():
        cena = data["price"]
        safe_tovar = formatting.escape_html(tovar)
        text += f"🔹 {safe_tovar} — {cena} сомони\n"
    bot.reply_to(message, text, parse_mode='HTML')

@bot.message_handler(commands=['cancel'])
def cancel_message(message):
    user_states[message.chat.id] = None
    bot.reply_to(message, "🛑 Действие отменено. Вы вернулись в главное меню.")

@bot.message_handler(commands=['help'])
def help_message(message):
    user_states[message.chat.id] = None
    text = '🤖 <b>Помощь:</b>\n\nНапишите название товара, и я найду его.\n\nДля заказа пишите в Instagram: <a href="https://instagram.com/oisha_shop_1989">oisha_shop_1989</a>'
    bot.reply_to(message, text, parse_mode='HTML')

# --- АДМИНКА ---
@bot.message_handler(commands=['admin'])
def admin_start(message):
    user_states[message.chat.id] = 'awaiting_admin_password'
    bot.send_message(message.chat.id, "🔒 <b>Вход в Админ-панель</b>\nВведите пароль:", parse_mode='HTML')

@bot.message_handler(commands=['delete'])
def delete_start(message):
    user_states[message.chat.id] = 'awaiting_delete_password'
    bot.send_message(message.chat.id, "🔒 <b>Удаление товара</b>\nВведите пароль для подтверждения:", parse_mode='HTML')

@bot.message_handler(content_types=['photo', 'document'])
def handle_photo(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id)
    
    if state == 'awaiting_new_item':
        is_doc = False
        if message.photo:
            file_id = message.photo[-1].file_id
        elif message.document:
            file_id = message.document.file_id
            is_doc = True
        else:
            return
            
        caption = message.caption
        if not caption:
            bot.send_message(chat_id, "Ошибка: Вы отправили фото без подписи. Напишите название и цену в описании к фото.")
            return

        try:
            parts = caption.split()
            if len(parts) < 2:
                bot.send_message(chat_id, "Ошибка формата подписи. Напишите: Название Цена")
                return
            cena = int(parts[-1])
            nazvanie = " ".join(parts[:-1])
            
            if cena > 10000:
                bot.send_message(chat_id, "Ошибка: Слишком дорого! Максимум 10 000 сомони.")
                return

            add_item_to_db(nazvanie, cena, file_id, is_doc)
            
            user_states[chat_id] = None
            safe_name = formatting.escape_html(nazvanie)
            bot.send_message(chat_id, f"✅ УСПЕХ! Товар '<b>{safe_name}</b>' с фото добавлен за {cena} сомони.", parse_mode='HTML')
        except ValueError:
            bot.send_message(chat_id, "Ошибка: Цена должна быть числом (последнее слово в подписи).")
    else:
        bot.send_message(chat_id, "Чтобы добавить фото, зайдите в /admin.")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    text = message.text
    text_lower = text.lower()
    state = user_states.get(chat_id)

    if state == 'awaiting_admin_password':
        bot.delete_message(chat_id, message.message_id) 
        if text == "oisha2026":
            user_states[chat_id] = 'awaiting_new_item'
            bot.send_message(chat_id, "✅ Пароль верный!\n\n<b>Отправьте фото товара</b>, а в подписи к нему напишите название и цену.\nПример: <code>Шапка 500</code>", parse_mode='HTML')
        else:
            user_states[chat_id] = None
            bot.send_message(chat_id, "❌ ДОСТУП ЗАПРЕЩЕН!")
        return

    if state == 'awaiting_delete_password':
        bot.delete_message(chat_id, message.message_id)
        if text == "oisha2026":
            user_states[chat_id] = 'awaiting_delete_item'
            bot.send_message(chat_id, "✅ Пароль верный!\nВведите название товара для удаления (или /cancel):", parse_mode='HTML')
        else:
            user_states[chat_id] = None
            bot.send_message(chat_id, "❌ ДОСТУП ЗАПРЕЩЕН!")
        return

    if state == 'awaiting_delete_item':
        user_states[chat_id] = None
        magazin = get_all_items()
        to_delete = None
        for tovar in magazin.keys():
            if text_lower in tovar.lower() or tovar.lower() in text_lower:
                to_delete = tovar
                break
                
        if to_delete:
            delete_item_from_db(to_delete)
            safe_name = formatting.escape_html(to_delete)
            bot.send_message(chat_id, f"✅ Товар '<b>{safe_name}</b>' удален из базы!", parse_mode='HTML')
        else:
            bot.send_message(chat_id, f"Товар не найден.")
        return

    if state == 'awaiting_new_item':
        bot.send_message(chat_id, "Пожалуйста, отправьте <b>фотографию</b> товара, а в подписи укажите название и цену.", parse_mode='HTML')
        return

    if "заказ" in text_lower or "тавр" in text_lower or "фармоиш" in text_lower or "харид" in text_lower:
        answer = 'Зайдите на наш <a href="https://instagram.com/oisha_shop_1989">Instagram</a> и напишите в Direct. 👗✨'
        bot.reply_to(message, answer, parse_mode='HTML')
        return 
    
    bot.send_chat_action(chat_id, 'typing')
    magazin = get_all_items()
    found = False
    
    for tovar, data in magazin.items():
        if tovar.lower() in text_lower or text_lower in tovar.lower():
            found = True
            cena = data["price"]
            photo_id = data.get("photo", "")
            is_doc = data.get("is_doc", False)
            
            if photo_id:
                try:
                    if is_doc:
                        bot.send_document(chat_id, document=photo_id, caption=f"👗 <b>{formatting.escape_html(tovar)}</b>\n💰 Цена: {cena} сомони", parse_mode='HTML')
                    else:
                        bot.send_photo(chat_id, photo=photo_id, caption=f"👗 <b>{formatting.escape_html(tovar)}</b>\n💰 Цена: {cena} сомони", parse_mode='HTML')
                except Exception as e:
                    bot.reply_to(message, f"👗 <b>{formatting.escape_html(tovar)}</b>\n💰 Цена: {cena} сомони", parse_mode='HTML')
            else:
                bot.reply_to(message, f"👗 <b>{formatting.escape_html(tovar)}</b>\n💰 Цена: {cena} сомони", parse_mode='HTML')
            break 
            
    if not found:
        prompt = f"{SYSTEM_PROMPT}\n\nКлиент спрашивает: {text}"
        try:
            response = client.models.generate_content(model='gemini-3.5-flash-lite', contents=prompt)
            bot.reply_to(message, response.text) 
        except Exception:
            bot.reply_to(message, "Извините, сервера перегружены. Попробуйте позже.")

# --- ЗАПУСК ---
if __name__ == "__main__":
    keep_alive()
    print("Бот подключен к базе данных и запущен!")
    while True:
        try:
            bot.polling(none_stop=True, timeout=30)
        except Exception as e:
            print(f"[СЕТЬ]: Оборвалось. Ошибка: {e}")
            time.sleep(5)
