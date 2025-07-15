import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext, CallbackQueryHandler
import mercadopago
import requests

# Carrega variáveis de ambiente
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
MP_TOKEN = os.getenv("MERCADO_PAGO_TOKEN")

# Configura Mercado Pago
sdk = mercadopago.SDK(MP_TOKEN)

# Logger
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Mock de categorias e produtos
CATEGORIAS = {
    "Eletrônicos": [
        {"nome": "Fone Bluetooth", "preco": 150},
        {"nome": "Carregador Turbo", "preco": 80}
    ],
    "Moda": [
        {"nome": "Camiseta Estampada", "preco": 60},
        {"nome": "Tênis Casual", "preco": 200}
    ],
    "Livros": [
        {"nome": "Python para Iniciantes", "preco": 90},
        {"nome": "Dom Quixote", "preco": 45}
    ]
}

# Comando /start
def start(update: Update, context: CallbackContext):
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat:{cat}")] for cat in CATEGORIAS]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Bem-vindo à loja! Escolha uma categoria:", reply_markup=reply_markup)

# Callback para categorias
def categoria_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    categoria = query.data.split(":")[1]
    produtos = CATEGORIAS[categoria]

    keyboard = [
        [InlineKeyboardButton(f"{p['nome']} - R${p['preco']}", callback_data=f"prod:{categoria}:{i}")]
        for i, p in enumerate(produtos)
    ]
    keyboard.append([InlineKeyboardButton("⬅ Voltar", callback_data="voltar")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(f"Produtos em *{categoria}*:", reply_markup=reply_markup, parse_mode='Markdown')

# Callback para produto com pagamento via PIX
def produto_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    _, categoria, index = query.data.split(":")
    produto = CATEGORIAS[categoria][int(index)]

    payment_data = {
        "transaction_amount": float(produto["preco"]),
        "description": produto["nome"],
        "payment_method_id": "pix",
        "payer": {
            "email": "comprador@email.com"  # obrigatório para simulação de pagamento Pix
        }
    }

    payment_response = sdk.payment().create(payment_data)
    payment = payment_response["response"]

    qr_code_base64 = payment["point_of_interaction"]["transaction_data"]["qr_code_base64"]
    qr_code = payment["point_of_interaction"]["transaction_data"]["qr_code"]
    pix_copy_paste = payment["point_of_interaction"]["transaction_data"]["qr_code"]

    # Envia QR code como imagem
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?data={qr_code}&size=300x300"
    
    context.bot.send_photo(
        chat_id=query.message.chat_id,
        photo=qr_url,
        caption=f"*{produto['nome']}*\n\n💰 *R${produto['preco']}*\n\n📎 Copie o código Pix:\n`{pix_copy_paste}`",
        parse_mode="Markdown"
    )

    keyboard = [[InlineKeyboardButton("⬅ Voltar", callback_data=f"cat:{categoria}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.message.reply_text("Após o pagamento, você será notificado!", reply_markup=reply_markup)

# Voltar
def voltar_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat:{cat}")] for cat in CATEGORIAS]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text("Escolha uma categoria:", reply_markup=reply_markup)

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(categoria_handler, pattern=r"^cat:"))
    dp.add_handler(CallbackQueryHandler(produto_handler, pattern=r"^prod:"))
    dp.add_handler(CallbackQueryHandler(voltar_handler, pattern=r"^voltar$"))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
