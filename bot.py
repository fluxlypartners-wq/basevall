import os
import json
import logging
from pathlib import Path

from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))          # Your private group with Topics
DATA_FILE = Path("topics.json")
# ============================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def load_topics() -> dict:
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_topics(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """When user presses /start"""
    user = update.effective_user
    await update.message.reply_text(
        "👋 Hello! Send me your message and I’ll forward it.\n"
        "You can also just write your question directly."
    )


async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Messages coming from users in private chat with the bot"""
    if update.effective_chat.type != "private":
        return

    user = update.effective_user
    message = update.message
    topics = load_topics()
    user_id_str = str(user.id)

    # Create topic if it doesn't exist
    if user_id_str not in topics:
        topic_name = f"{user.full_name}"
        if user.username:
            topic_name += f" (@{user.username})"
        else:
            topic_name += f" (ID: {user.id})"

        # Limit topic name length
        topic_name = topic_name[:128]

        try:
            topic = await context.bot.create_forum_topic(
                chat_id=GROUP_ID,
                name=topic_name,
            )
            topics[user_id_str] = {
                "thread_id": topic.message_thread_id,
                "name": topic_name,
                "username": user.username,
            }
            save_topics(topics)
            logger.info(f"Created topic for {user.id}: {topic_name}")
        except Exception as e:
            logger.error(f"Failed to create topic: {e}")
            await message.reply_text("Sorry, something went wrong. Please try again later.")
            return

    thread_id = topics[user_id_str]["thread_id"]

    # Forward the message to the topic
    try:
        # Header
        header = (
            f"👤 <b>{user.full_name}</b>\n"
            f"Username: @{user.username or 'none'}\n"
            f"ID: <code>{user.id}</code>\n"
            f"────────────────"
        )
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=thread_id,
            text=header,
            parse_mode=ParseMode.HTML,
        )

        # Actual message content
        if message.text:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                message_thread_id=thread_id,
                text=message.text,
            )
        elif message.photo:
            await context.bot.send_photo(
                chat_id=GROUP_ID,
                message_thread_id=thread_id,
                photo=message.photo[-1].file_id,
                caption=message.caption,
            )
        elif message.document:
            await context.bot.send_document(
                chat_id=GROUP_ID,
                message_thread_id=thread_id,
                document=message.document.file_id,
                caption=message.caption,
            )
        elif message.voice:
            await context.bot.send_voice(
                chat_id=GROUP_ID,
                message_thread_id=thread_id,
                voice=message.voice.file_id,
                caption=message.caption,
            )
        elif message.video:
            await context.bot.send_video(
                chat_id=GROUP_ID,
                message_thread_id=thread_id,
                video=message.video.file_id,
                caption=message.caption,
            )
        else:
            # Fallback: forward the whole message
            await message.forward(
                chat_id=GROUP_ID,
                message_thread_id=thread_id,
            )

        await message.reply_text("✅ Message sent! I’ll reply here soon.")
    except Exception as e:
        logger.error(f"Failed to send to topic: {e}")
        await message.reply_text("Sorry, failed to deliver your message.")


async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """When admin replies inside a topic → send to the user"""
    if update.effective_chat.id != GROUP_ID:
        return

    if not update.message.is_topic_message:
        return

    # Only allow the admin to reply
    if update.effective_user.id != ADMIN_ID:
        return

    thread_id = update.message.message_thread_id
    topics = load_topics()

    # Find which user this topic belongs to
    target_user_id = None
    for uid, data in topics.items():
        if data["thread_id"] == thread_id:
            target_user_id = int(uid)
            break

    if not target_user_id:
        await update.message.reply_text("⚠️ Could not find the user for this topic.")
        return

    try:
        if update.message.text:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=update.message.text,
            )
        elif update.message.photo:
            await context.bot.send_photo(
                chat_id=target_user_id,
                photo=update.message.photo[-1].file_id,
                caption=update.message.caption,
            )
        elif update.message.document:
            await context.bot.send_document(
                chat_id=target_user_id,
                document=update.message.document.file_id,
                caption=update.message.caption,
            )
        elif update.message.voice:
            await context.bot.send_voice(
                chat_id=target_user_id,
                voice=update.message.voice.file_id,
                caption=update.message.caption,
            )
        elif update.message.video:
            await context.bot.send_video(
                chat_id=target_user_id,
                video=update.message.video.file_id,
                caption=update.message.caption,
            )
        else:
            await update.message.forward(chat_id=target_user_id)

        # Optional confirmation
        # await update.message.reply_text("✅ Sent to user")
    except Exception as e:
        logger.error(f"Failed to send reply to user: {e}")
        await update.message.reply_text(f"❌ Failed to send: {e}")


def main():
    if not all([BOT_TOKEN, ADMIN_ID, GROUP_ID]):
        raise ValueError("BOT_TOKEN, ADMIN_ID and GROUP_ID must be set")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & ~filters.COMMAND,
        handle_user_message
    ))
    application.add_handler(MessageHandler(
        filters.Chat(GROUP_ID) & ~filters.COMMAND,
        handle_admin_reply
    ))

    print("Topics contact bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()