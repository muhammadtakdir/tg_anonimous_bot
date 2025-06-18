from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from config import BOT_TOKEN, PRE_APPROVED_ADMINS
import logging

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

ADMIN_CHAT_IDS = set()

async def register_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if user_id in PRE_APPROVED_ADMINS:
        ADMIN_CHAT_IDS.add(user_id)
        logger.info(f"Admin registered: {user_id}")
        await update.message.reply_text("✅ Anda sekarang terdaftar sebagai admin!")
    else:
        await update.message.reply_text("👋 Halo! Silakan kirim pesan Anda dan akan kami teruskan ke admin.")

async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_chat.id
        if user_id in ADMIN_CHAT_IDS:
            return  # Skip jika pesan dari admin
        
        if not ADMIN_CHAT_IDS:
            await update.message.reply_text("⚠️ Admin belum tersedia. Mohon tunggu...")
            return
            
        user_message = update.message.text
        logger.info(f"Forwarding message from {user_id}: {user_message[:50]}...")
        
        success_count = 0
        for admin_id in ADMIN_CHAT_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"📩 Pesan dari user {user_id}:\n\n{user_message}"
                )
                success_count += 1
            except Exception as e:
                logger.error(f"Gagal mengirim ke admin {admin_id}: {e}")
        
        if success_count > 0:
            await update.message.reply_text("📬 Pesan Anda sudah diteruskan ke admin!")
        else:
            await update.message.reply_text("❌ Gagal mengirim pesan ke admin. Silakan coba lagi nanti.")
            
    except Exception as e:
        logger.error(f"Error in forwarding: {e}")
        await update.message.reply_text("⚠️ Terjadi error saat memproses pesan Anda.")

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /balas"""
    try:
        if update.effective_chat.id not in ADMIN_CHAT_IDS:
            return
            
        command = update.message.text.split(maxsplit=2)
        if len(command) < 3 or command[0].lower() != "/balas":
            await update.message.reply_text("❌ Format salah! Gunakan: /balas <user_id> <pesan>")
            return
        
        target_user_id = int(command[1])
        reply_text = command[2]
        
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"📨 Balasan admin:\n\n{reply_text}"
        )
        await update.message.reply_text("✅ Pesan terkirim ke user!")
        
    except ValueError:
        await update.message.reply_text("❌ Format ID user tidak valid")
    except Exception as e:
        logger.error(f"Error in admin reply: {e}")
        await update.message.reply_text(f"⚠️ Gagal mengirim balasan: {e}")

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Chat ID Anda: {update.effective_chat.id}")

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Register handlers
    application.add_handler(CommandHandler("id", debug))
    application.add_handler(CommandHandler("start", register_admin))
    application.add_handler(CommandHandler("balas", handle_admin_reply))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, forward_to_admin))
    
    logger.info("Bot started polling...")
    application.run_polling()

if __name__ == "__main__":
    main()