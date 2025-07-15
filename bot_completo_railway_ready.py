import os
import logging
import re
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackContext, CallbackQueryHandler,
    MessageHandler, Filters, ConversationHandler
)
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

# Estado da conversa
ESPERANDO_MAC = range(1)

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
    ],
    "ATIVAR APP": [
        {"nome": "MEGA IPTV", "preco": 75}
    ]
}

# Armazenamento temporário por usuário
user_temp_data = {}

# /start
def start(update: Update, context: CallbackContext):
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat:{cat}")] for cat in CATEGORIAS]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Bem-vindo à loja! Escolha uma categoria:", reply_markup=reply_markup)

# Categoria handler
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

# Produto handler
def produto_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    _, categoria, index = query.data.split(":")
    produto = CATEGORIAS[categoria][int(index)]

    user_id = query.from_user.id
    user_temp_data[user_id] = {
        "categoria": categoria,
        "produto": produto
    }

    if categoria == "ATIVAR APP":
        query.message.reply_text("Digite o MAC de 12 dígitos (apenas letras e números, sem `:`):")
        return ESPERANDO_MAC
    else:
        return enviar_pagamento_pix(query, context, produto["nome"], produto["preco"])

# Handler para receber MAC e continuar
def receber_mac(update: Update, context: CallbackContext):
    mac = update.message.text.strip()
    user_id = update.message.from_user.id

    if not re.fullmatch(r"[A-Fa-f0-9]{12}", mac):
        update.message.reply_text("❌ MAC inválido! Digite exatamente 12 caracteres alfanuméricos (sem dois pontos).")
        return ESPERANDO_MAC

    produto = user_temp_data[user_id]["produto"]
    produto_nome = f"{produto['nome']} (MAC: {mac})"
    produto_preco = produto["preco"]

    enviar_pagamento_pix(update, context, produto_nome, produto_preco)
    return ConversationHandler.END

# Função comum para criar e enviar pagamento Pix
def enviar_pagamento_pix(update_or_query, context, nome, preco):
    chat_id = update_or_query.effective_chat.id

    payment_data = {
        "transaction_amount": float(preco),
        "description": nome,
        "payment_method_id": "pix",
        "payer": {
            "email": "comprador@email.com"
        }
    }

    payment_response = sdk.payment().create(payment_data)
    payment = payment_response["response"]

    qr_code = payment["point_of_interaction"]["transaction_data"]["qr_code"]
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?data={qr_code}&size=300x300"

    context.bot.send_photo(
        chat_id=chat_id,
        photo=qr_url,
        caption=f"*{nome}*\n💰 *R${preco}*\n\n📎 Copie e cole o código Pix:\n`{qr_code}`",
        parse_mode="Markdown"
    )

    keyboard = [[InlineKeyboardButton("⬅ Voltar", callback_data="voltar")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.send_message(chat_id=chat_id, text="Após o pagamento, você será notificado!", reply_markup=reply_markup)

# Voltar
def voltar_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat:{cat}")] for cat in CATEGORIAS]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text("Escolha uma categoria:", reply_markup=reply_markup)

def cancelar(update: Update, context: CallbackContext):
    update.message.reply_text("❌ Operação cancelada.")
    return ConversationHandler.END

# Main
def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(produto_handler, pattern=r"^prod:")],
        states={
            ESPERANDO_MAC: [MessageHandler(Filters.text & ~Filters.command, receber_mac)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        allow_reentry=True
    )

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(conv_handler)
    dp.add_handler(CallbackQueryHandler(categoria_handler, pattern=r"^cat:"))
    dp.add_handler(CallbackQueryHandler(voltar_handler, pattern=r"^voltar$"))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
