# group_owner_finder_bot.py

import logging
import re
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

from telethon.tl.types import ChannelParticipantsAdmins, User

API_ID = 5746709
API_HASH = 'c00191beb5cdedc2bacf532977d07cd8'
BOT_TOKEN = '8113111429:AAEjjVLWMcpyV8nqXG9koj-HC4ksNtsXLCg'
ADMIN_ID = 5893249491

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

user_sessions = {}

main_keyboard = InlineKeyboardMarkup(row_width=1)
main_keyboard.add(
    InlineKeyboardButton("🚪 Logout", callback_data="logout")
)

@dp.message_handler(commands=['start'])
async def start_cmd(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    await msg.reply("👋 Welcome! Use /login_userbot to start login or press below to logout.", reply_markup=main_keyboard)

@dp.callback_query_handler(lambda c: c.data == 'logout')
async def cb_logout(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id != ADMIN_ID:
        return
    try:
        if os.path.exists("userbot.session"):
            os.remove("userbot.session")
        if user_id in user_sessions:
            del user_sessions[user_id]
        await bot.send_message(user_id, "✅ You have been logged out and session removed.", reply_markup=main_keyboard)
    except Exception as e:
        await bot.send_message(user_id, f"❌ Logout error: {e}")
    await bot.answer_callback_query(callback_query.id)

@dp.message_handler(commands=['login_userbot'])
async def login_userbot(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    await msg.reply("📱 Send your phone number with country code (e.g. +91xxxxxxxxxx):")
    user_sessions[msg.from_user.id] = {'step': 'phone'}

@dp.message_handler(lambda msg: msg.from_user.id == ADMIN_ID and msg.text.startswith('+'))
async def handle_phone(msg: types.Message):
    session = user_sessions.get(msg.from_user.id)
    if not session or session['step'] != 'phone':
        return
    session['phone'] = msg.text.strip()
    session['client'] = TelegramClient(StringSession(), API_ID, API_HASH)
    await session['client'].connect()
    try:
        sent = await session['client'].send_code_request(session['phone'])
        session['step'] = 'code'
        session['otp'] = ""
        session['code_hash'] = sent.phone_code_hash

        otp_keyboard = InlineKeyboardMarkup(row_width=3)
        for i in range(1, 10):
            otp_keyboard.insert(InlineKeyboardButton(str(i), callback_data=f"otp_digit:{i}"))
        otp_keyboard.insert(InlineKeyboardButton("0", callback_data="otp_digit:0"))
        otp_keyboard.add(InlineKeyboardButton("✅ Confirm", callback_data="otp_confirm"))

        await msg.reply("🔢 Enter OTP using buttons:", reply_markup=otp_keyboard)
    except Exception as e:
        await msg.reply(f"❌ Failed to send code: {e}")

@dp.callback_query_handler(lambda c: c.data.startswith("otp_digit:"))
async def otp_digit_press(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id not in user_sessions:
        return
    digit = callback_query.data.split(":")[1]
    user_sessions[user_id]['otp'] += digit
    await callback_query.message.edit_text(
        f"🔢 Enter OTP using buttons:\nCurrent: {user_sessions[user_id]['otp']}",
        reply_markup=callback_query.message.reply_markup
    )
    await bot.answer_callback_query(callback_query.id)

@dp.callback_query_handler(lambda c: c.data == "otp_confirm")
async def otp_confirm(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id not in user_sessions:
        return
    session = user_sessions[user_id]
    try:
        await session['client'].sign_in(session['phone'], session['otp'])
    except SessionPasswordNeededError:
        session['step'] = 'password'
        await bot.send_message(user_id, "🔐 2FA enabled. Send your password:")
        await bot.answer_callback_query(callback_query.id)
        return
    except Exception as e:
        await bot.send_message(user_id, f"❌ OTP login failed: {e}")
        await bot.answer_callback_query(callback_query.id)
        return

    string = session['client'].session.save()
    with open("userbot.session", "w") as f:
        f.write(string)
    await bot.send_message(user_id, "✅ Userbot session saved successfully! Now send any group @username to contact the owner.", reply_markup=main_keyboard)
    del user_sessions[user_id]
    await bot.answer_callback_query(callback_query.id)

@dp.message_handler(lambda msg: msg.from_user.id == ADMIN_ID)
async def handle_password_or_group(msg: types.Message):
    user_id = msg.from_user.id

    if user_id in user_sessions and user_sessions[user_id].get('step') == 'password':
        session = user_sessions[user_id]
        try:
            await session['client'].sign_in(password=msg.text.strip())
            string = session['client'].session.save()
            with open("userbot.session", "w") as f:
                f.write(string)
            await msg.reply("✅ Userbot session saved with 2FA! Now send any group @username to contact the owner.", reply_markup=main_keyboard)
            del user_sessions[user_id]
        except Exception as e:
            await msg.reply(f"❌ 2FA login failed: {e}")
        return

    if user_id not in user_sessions:
        match = re.search(r"(?:https://t\.me/|@)([a-zA-Z0-9_]+)", msg.text)
        if not match:
            await msg.reply("❗ Invalid group username or link.")
            return

        group_username = match.group(1)
        try:
            with open("userbot.session", "r") as f:
                session_str = f.read()
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.start()

            entity = await client.get_entity(group_username)
            admins = await client.get_participants(entity, filter=ChannelParticipantsAdmins, limit=10)

            messaged = False
            for admin in admins:
                if isinstance(admin, User) and not admin.bot:
                    try:
                        await client.send_message(admin.id, f"Hello! Kya ye group (@{group_username}) selling ke liye available hai?")
                        await msg.reply(f"✅ Message sent to: {admin.first_name}")
                        messaged = True
                        break
                    except Exception as e:
                        await msg.reply(f"❌ Failed to message admin: {e}")
                        break

            

            
           
               
            else:
                if not messaged:
                    await msg.reply("⚠️ No admin or username could be messaged.")

        except Exception as e:
            await msg.reply(f"❌ Error: {e}")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
