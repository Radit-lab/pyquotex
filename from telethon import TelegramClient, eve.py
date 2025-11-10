from telethon import TelegramClient, events
import asyncio

# ==== CONFIG ====
api_id = 23255624
api_hash = "195b01ad28a4e39c07c790946c2c5366"
session_name = "text_format_bot"

# ==== START CLIENT ====
client = TelegramClient(session_name, api_id, api_hash)

# ==== FUNCTION TO DETECT TEXT FORMAT ====
def detect_text_format(text):
    if text.isdigit():
        return "This text is a number 🔢"
    elif text.isalpha():
        if text.isupper():
            return "All uppercase letters 🔠"
        elif text.islower():
            return "All lowercase letters 🔡"
        else:
            return "Alphabetic mixed case 📝"
    elif any(char.isdigit() for char in text) and any(char.isalpha() for char in text):
        return "Alphanumeric (letters + numbers) 🔣"
    elif text.strip() == "":
        return "Blank or whitespace 🕳️"
    elif any(char in "😀😁😂🤣😅😇😉😊😋😎😍😘🥰🤩🤔😐😶😏🙄😬😴😪😷🤒🤕🤢🤮🥵🥶🥴😵🤯" for char in text):
        return "Contains emojis 😁"
    else:
        return "General text or sentence 💬"

# ==== MESSAGE HANDLER (your own messages only) ====
@client.on(events.NewMessage(outgoing=True))
async def handler(event):
    user_text = event.raw_text
    format_description = detect_text_format(user_text)
    await event.reply(f"🧩 **Text Analysis:** {format_description}")

# ==== RUN THE BOT SAFELY ====
if __name__ == "__main__":
    print("🤖 Text Format Bot is starting...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client.start()
    print("✅ Bot is now running. Type any text in Telegram.")
    client.run_until_disconnected()
