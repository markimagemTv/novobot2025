import logging
import os
import requests
import mercadopago
from uuid import uuid4
from dotenv import load_dotenv
from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    CallbackQueryHandler,
    ConversationHandler,
)

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
MERCADO_PAGO_TOKEN = os.getenv("MERCADO_PAGO_TOKEN")

# Setup Mercado Pago
sdk = mercadopago.SDK(MERCADO_PAGO_TOKEN)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Storage temporário (ideal seria banco de dados)
users = {}
cart = {}

# States
NAME, PHONE, CHOOSE_CAT, GET_MAC, CHECKOUT = range(5)

def start(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    if user_id not in users:
        update.message.reply_text("Olá! Bem-vindo. Por favor, envie seu nome para cadastro.")
        return NAME
    return main_menu(update, context)

def name(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    users[user_id] = {"name": update.message.text}
    update.message.reply_text("Agora envie seu número de telefone:")
    return PHONE

def phone(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    users[user_id]["phone"] = update.message.text
    update.message.reply_text("Cadastro realizado com sucesso!")
    return main_menu(update, context)

def main_menu(update: Update, context: CallbackContext):
    buttons = [
        [KeyboardButton("🛒 Loja"), KeyboardButton("📦 Meus Pedidos")],
        [KeyboardButton("👤 Perfil")]
    ]
    update.message.reply_text("Menu principal:", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True))
    return CHOOSE_CAT

def loja_menu(update: Update, context: CallbackContext):
    buttons = [
        [InlineKeyboardButton("ATIVAR APP", callback_data="cat_ativar")],
        [InlineKeyboardButton("COMPRAR CRÉDITOS", callback_data="cat_creditos")],
    ]
    update.message.reply_text("Escolha a categoria:", reply_markup=InlineKeyboardMarkup(buttons))

def categoria_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.message.chat_id

    if query.data == "cat_ativar":
        cart[user_id] = {"produto": "Mega IPTV", "valor": 75.00}
        context.bot.send_message(chat_id=user_id, text="Informe o MAC (sem os dois-pontos):")
        return GET_MAC

    elif query.data == "cat_creditos":
        buttons = [
            [InlineKeyboardButton("10 Créditos - R$135,00", callback_data="comprar_fastplay_10")]
        ]
        context.bot.send_message(chat_id=user_id, text="Escolha uma opção:", reply_markup=InlineKeyboardMarkup(buttons))

def get_mac(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    cart[user_id]["mac"] = update.message.text
    mac_copy = cart[user_id]["mac"]
    context.bot.send_message(chat_id=user_id, text=f"MAC salvo: `{mac_copy}`", parse_mode='Markdown')
    return checkout(update, context)

def comprar_credito_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.message.chat_id
    cart[user_id] = {"produto": "FAST PLAY - 10 Créditos", "valor": 135.00}
    return checkout(update, context)

def checkout(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    produto = cart[user_id]["produto"]
    valor = cart[user_id]["valor"]
    
    payment_data = {
        "transaction_amount": float(valor),
        "description": produto,
        "payment_method_id": "pix",
        "payer": {
            "email": f"user{user_id}@email.com",
            "first_name": users[user_id]["name"],
        }
    }

    payment = sdk.payment().create(payment_data)
    qr_code_base64 = payment["response"]["point_of_interaction"]["transaction_data"]["qr_code_base64"]
    pix_code = payment["response"]["point_of_interaction"]["transaction_data"]["qr_code"]

    context.bot.send_photo(chat_id=user_id, photo=f"data:image/png;base64,{qr_code_base64}")
    context.bot.send_message(chat_id=user_id, text=f"Chave PIX (toque para copiar):\n`{pix_code}`", parse_mode='Markdown')

    # Notifica admin
    context.bot.send_message(chat_id=ADMIN_ID, text=f"📥 Novo pedido!\nCliente: {users[user_id]['name']}\nProduto: {produto}\nValor: R${valor}")
    return ConversationHandler.END

def admin_notify_user(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return
    try:
        args = update.message.text.split()
        user_id = int(args[1])
        msg = " ".join(args[2:])
        context.bot.send_message(chat_id=user_id, text=f"📢 Atualização do pedido: {msg}")
    except Exception as e:
        update.message.reply_text("Erro ao enviar notificação.")

def pedidos(update: Update, context: CallbackContext):
    update.message.reply_text("🔍 Em breve: histórico de pedidos.")

def perfil(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    if user_id in users:
        nome = users[user_id]["name"]
        telefone = users[user_id]["phone"]
        update.message.reply_text(f"👤 Nome: {nome}\n📞 Telefone: {telefone}")
    else:
        update.message.reply_text("Você ainda não fez cadastro.")

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(Filters.text & ~Filters.command, name)],
            PHONE: [MessageHandler(Filters.text & ~Filters.command, phone)],
            CHOOSE_CAT: [
                MessageHandler(Filters.regex("🛒 Loja"), loja_menu),
                MessageHandler(Filters.regex("📦 Meus Pedidos"), pedidos),
                MessageHandler(Filters.regex("👤 Perfil"), perfil),
            ],
            GET_MAC: [MessageHandler(Filters.text & ~Filters.command, get_mac)],
        },
        fallbacks=[],
    )

    dp.add_handler(conv_handler)
    dp.add_handler(CallbackQueryHandler(categoria_callback, pattern="cat_.*"))
    dp.add_handler(CallbackQueryHandler(comprar_credito_callback, pattern="comprar_fastplay_10"))
    dp.add_handler(CommandHandler("notificar", admin_notify_user))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
