import telebot
from telebot import types, formatting
from google import genai
import time
import json 
import os
from flask import Flask
from threading import Thread

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

bot = telebot.TeleBot(BOT_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)

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

def load_db():
    try:
        with open('magazin.json', 'r', encoding='utf-8') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_db(data):
    with open('magazin.json', 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

# --- КОМАНДЫ ---

@bot.message_handler(commands=['start'])
def start_message(message):
    user_states[message.chat.id] = None 
    bot.reply_to(message, "Здравствуйте! Добро пожаловать в Oisha Shop! 👗 Я ваш ИИ-помощник. Нажмите 'Меню', чтобы увидеть команды.")

@bot.message_handler(commands=['catalog'])
def catalog_message(message):
    user_states[message.chat.id] = None
    magazin = load_db()
    if not magazin:
        bot.reply_to(message, "Каталог пока пуст.")
        return
    
    text = "📦 <b>Наш каталог:</b>\n\n"
    for tovar, data in magazin.items():
        cena = data["price"] if isinstance(data, dict) else data
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
        if message.photo:
            file_id = message.photo[-1].file_id
        elif message.document:
            file_id = message.document.file_id
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

            magazin = load_db()
            magazin[nazvanie] = {"price": cena, "photo": file_id}
            save_db(magazin)
            
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
        magazin = load_db()
        to_delete = None
        for tovar in magazin.keys():
            if text_lower in tovar.lower() or tovar.lower() in text_lower:
                to_delete = tovar
                break
                
        if to_delete:
            del magazin[to_delete]
            save_db(magazin)
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
    magazin = load_db()
    found = False
    
    # УЛУЧШЕННЫЙ ПОИСК (ловим товар, даже если он в середине предложения)
    for tovar, data in magazin.items():
        if tovar.lower() in text_lower or text_lower in tovar.lower():
            found = True
            cena = data["price"] if isinstance(data, dict) else data
            photo_id = data.get("photo", "") if isinstance(data, dict) else ""
            
            if photo_id:
                try:
                    bot.send_photo(chat_id, photo=photo_id, caption=f"👗 <b>{formatting.escape_html(tovar)}</b>\n💰 Цена: {cena} сомони", parse_mode='HTML')
                except Exception:
                    # Если фото устарело или удалилось из телеги, шлем текст
                    bot.reply_to(message, f"👗 <b>{formatting.escape_html(tovar)}</b>\n💰 Цена: {cena} сомони\n(Фото временно недоступно)", parse_mode='HTML')
            else:
                bot.reply_to(message, f"👗 <b>{formatting.escape_html(tovar)}</b>\n💰 Цена: {cena} сомони", parse_mode='HTML')
            break # Нашли товар — дальше не ищем
            
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
    print("Бот с защитой фото и поиском запущен!")
    while True:
        try:
            bot.polling(none_stop=True, timeout=30)
        except Exception as e:
            print(f"[СЕТЬ]: Оборвалось. Ошибка: {e}")
            time.sleep(5)
