from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters
# Ubah impor config untuk mengambil daftar ADMIN_IDS
from config import BOT_TOKEN, ADMIN_IDS
import sqlite3
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- FUNGSI init_db() YANG DIPERBAIKI ---
def init_db():
    """
    Inisialisasi database.
    Membuat tabel jika belum ada, dan melakukan migrasi (menambah kolom) jika diperlukan.
    """
    conn = None
    try:
        conn = sqlite3.connect('chat_history.db')
        cursor = conn.cursor()

        # Langkah 1: Pastikan tabel 'messages' ada.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                admin_id INTEGER,
                original_msg_id INTEGER,
                forwarded_msg_id INTEGER,
                reply_msg_id INTEGER,
                content_type TEXT,
                content TEXT,
                timestamp DATETIME,
                status TEXT DEFAULT 'active'
            )
        ''')
        conn.commit()

        # Langkah 2: Periksa apakah kolom 'file_id' sudah ada.
        cursor.execute("PRAGMA table_info(messages)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'file_id' not in columns:
            logger.info("Memulai migrasi database: Menambahkan kolom 'file_id'...")
            
            # Langkah 3: Lakukan migrasi dengan cara yang lebih aman
            cursor.execute('BEGIN TRANSACTION')
            cursor.execute('ALTER TABLE messages RENAME TO messages_old')
            cursor.execute('''
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    admin_id INTEGER,
                    original_msg_id INTEGER,
                    forwarded_msg_id INTEGER,
                    reply_msg_id INTEGER,
                    content_type TEXT,
                    content TEXT,
                    file_id TEXT,
                    timestamp DATETIME,
                    status TEXT DEFAULT 'active'
                )
            ''')
            cursor.execute('''
                INSERT INTO messages (id, user_id, admin_id, original_msg_id, forwarded_msg_id, 
                                      reply_msg_id, content_type, content, timestamp, status)
                SELECT id, user_id, admin_id, original_msg_id, forwarded_msg_id, 
                       reply_msg_id, content_type, content, timestamp, status
                FROM messages_old
            ''')
            cursor.execute('DROP TABLE messages_old')
            conn.commit()
            logger.info("Migrasi database berhasil.")
        else:
            logger.info("Skema database sudah terbaru.")

    except sqlite3.Error as e:
        logger.error(f"Database error saat inisialisasi: {e}", exc_info=True)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


# Panggil fungsi inisialisasi saat bot dimulai
init_db()

async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # PERUBAHAN: Cek apakah pengirim adalah salah satu admin di dalam list
    if update.effective_chat.id in ADMIN_IDS:
        return

    user = update.effective_user
    user_msg = update.message
    conn = None
    
    try:
        conn = sqlite3.connect('chat_history.db')
        cursor = conn.cursor()

        user_info = (
            f"👤 <b>User Info</b>\n"
            f"ID: {user.id}\n"
            f"Nama: {user.full_name}\n"
            f"Username: @{user.username if user.username else '-'}\n\n"
        )

        content_type = ""
        content = ""
        file_id = None
        
        # PERUBAHAN: Loop untuk mengirim pesan ke setiap admin
        # dan menyimpan setiap pesan yang diteruskan ke database
        # agar setiap admin bisa membalasnya.
        
        # Fungsi pembantu untuk mengirim pesan dan menyimpan ke DB
        async def send_and_record(admin_id, send_function, **kwargs):
            forwarded = await send_function(chat_id=admin_id, **kwargs)
            # Simpan mapping untuk setiap pesan yang diteruskan
            cursor.execute('''
                INSERT INTO messages 
                (user_id, original_msg_id, forwarded_msg_id, content_type, content, file_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                user.id,
                user_msg.message_id,
                forwarded.message_id,
                content_type,
                content,
                file_id,
                datetime.now()
            ))
            logger.info(f"Pesan dari user {user.id} diteruskan ke admin {admin_id} (msg_id: {forwarded.message_id})")

        common_caption = (
            f"----------------\n"
            f"⬇️ Balas pesan ini untuk membalas user ⬇️"
        )

        if user_msg.text:
            content_type = "text"
            content = user_msg.text
            for admin_id in ADMIN_IDS:
                await send_and_record(
                    admin_id,
                    context.bot.send_message,
                    text=f"{user_info}📩 <b>Pesan:</b>\n{content}\n\n{common_caption}",
                    parse_mode="HTML"
                )

        elif user_msg.photo:
            content_type = "photo"
            content = user_msg.caption or ""
            file_id = user_msg.photo[-1].file_id
            for admin_id in ADMIN_IDS:
                await send_and_record(
                    admin_id,
                    context.bot.send_photo,
                    photo=file_id,
                    caption=f"{user_info}📸 <b>Foto:</b>\n{content}\n\n{common_caption}",
                    parse_mode="HTML"
                )
        
        elif user_msg.document:
            content_type = "document"
            content = user_msg.caption or ""
            file_id = user_msg.document.file_id
            for admin_id in ADMIN_IDS:
                await send_and_record(
                    admin_id,
                    context.bot.send_document,
                    document=file_id,
                    caption=f"{user_info}📄 <b>Dokumen:</b>\n{content}\n\n{common_caption}",
                    parse_mode="HTML"
                )

        else:
            await user_msg.reply_text("⚠️ Jenis pesan tidak didukung")
            return

        conn.commit()
        await user_msg.reply_text("📬 Pesan Anda sudah dikirim ke semua admin!")
        
    except sqlite3.Error as e:
        logger.error(f"Database error: {str(e)}")
        await user_msg.reply_text("⚠️ Gagal menyimpan pesan")
    except Exception as e:
        logger.error(f"Forward error: {str(e)}", exc_info=True)
        await user_msg.reply_text("❌ Gagal mengirim pesan ke admin")
    finally:
        if conn:
            conn.close()

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # PERUBAHAN: Cek apakah pengirim BUKAN salah satu admin
    if update.effective_chat.id not in ADMIN_IDS or not update.message.reply_to_message:
        return

    admin_who_replied = update.effective_user.id
    conn = None
    try:
        conn = sqlite3.connect('chat_history.db')
        cursor = conn.cursor()
        
        # Logika pencarian pesan asli sudah benar dan akan berfungsi untuk multi-admin
        cursor.execute('''
            SELECT user_id, original_msg_id FROM messages 
            WHERE forwarded_msg_id = ? AND status = 'active'
            ORDER BY timestamp DESC LIMIT 1
        ''', (update.message.reply_to_message.message_id,))
        original_msg = cursor.fetchone()

        if not original_msg:
            logger.error(f"Pesan tidak ditemukan untuk forwarded_msg_id: {update.message.reply_to_message.message_id}")
            await update.message.reply_text("⚠️ Pesan asli tidak ditemukan. Mungkin sudah terlalu lama atau bot baru saja di-restart.")
            return

        user_id, original_msg_id = original_msg
        
        sent_msg = None
        content_type = ""
        content = ""
        file_id = None
        admin_full_name = update.effective_user.full_name

        # Kirim balasan ke user
        if update.message.text:
            content_type = "text"
            content = update.message.text
            sent_msg = await context.bot.send_message(
                chat_id=user_id,
                text=f"📨 <b>Balasan dari {admin_full_name}:</b>\n\n{content}",
                reply_to_message_id=original_msg_id,
                parse_mode="HTML",
                allow_sending_without_reply=True
            )
        elif update.message.photo:
            content_type = "photo"
            content = update.message.caption or ""
            file_id = update.message.photo[-1].file_id
            sent_msg = await context.bot.send_photo(
                chat_id=user_id,
                photo=file_id,
                caption=f"📨 <b>Balasan dari {admin_full_name}:</b>\n\n{content}",
                reply_to_message_id=original_msg_id,
                parse_mode="HTML",
                allow_sending_without_reply=True
            )
        elif update.message.document:
            content_type = "document"
            content = update.message.caption or ""
            file_id = update.message.document.file_id
            sent_msg = await context.bot.send_document(
                chat_id=user_id,
                document=file_id,
                caption=f"📨 <b>Balasan dari {admin_full_name}:</b>\n\n{content}",
                reply_to_message_id=original_msg_id,
                parse_mode="HTML",
                allow_sending_without_reply=True
            )
        else:
            await update.message.reply_text("⚠️ Jenis balasan tidak didukung")
            return
        
        # Simpan balasan, catat admin mana yang membalas
        cursor.execute('''
            INSERT INTO messages 
            (user_id, admin_id, original_msg_id, reply_msg_id, content_type, content, file_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            admin_who_replied, # PERUBAHAN: Simpan ID admin yang membalas
            original_msg_id,
            sent_msg.message_id,
            content_type,
            content,
            file_id,
            datetime.now()
        ))
        conn.commit()
        
        logger.info(f"Balasan dari admin {admin_who_replied} berhasil dikirim: user={user_id}, reply_to={original_msg_id}")
        await update.message.reply_text("✅ Balasan terkirim ke user!")
        
    except Exception as e:
        logger.error(f"Reply error: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Gagal mengirim balasan: {str(e)}")
    finally:
        if conn:
            conn.close()

async def debug_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # PERUBAHAN: Cek apakah pengirim adalah salah satu admin
    if update.effective_chat.id not in ADMIN_IDS:
        return
    
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM messages")
        count = cursor.fetchone()[0]
        
        cursor.execute("SELECT * FROM messages ORDER BY timestamp DESC LIMIT 5")
        recent = cursor.fetchall()
        
        cursor.execute("PRAGMA table_info(messages)")
        columns = [col[1] for col in cursor.fetchall()]
        
        response = (
            f"📊 <b>Database Info:</b>\n"
            f"Total pesan: {count}\n\n"
            f"<b>5 pesan terakhir:</b>\n"
            f"<code>{', '.join(columns)}</code>\n"
        )
        
        for msg in recent:
            response += f"<code>{msg}</code>\n"
        
        await update.message.reply_text(response, parse_mode="HTML")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        conn.close()


def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # PERUBAHAN: Gunakan list ADMIN_IDS di dalam filter
    # Handler untuk pesan dari user ke admin
    application.add_handler(MessageHandler(
        filters.ALL & ~filters.COMMAND & ~filters.Chat(chat_id=ADMIN_IDS), 
        forward_to_admin
    ))
    
    # Handler untuk balasan dari admin ke user
    application.add_handler(MessageHandler(
        filters.REPLY & filters.Chat(chat_id=ADMIN_IDS),
        handle_admin_reply
    ))

    # Handler untuk command /debug hanya untuk admin
    application.add_handler(CommandHandler("debug", debug_db, filters.Chat(chat_id=ADMIN_IDS)))

    logger.info("Bot started with multi-admin support!")
    application.run_polling()

if __name__ == "__main__":
    main()

