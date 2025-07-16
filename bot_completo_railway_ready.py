# --- Imports e configuração mantidos (sem mudanças)
import logging
import os
import io
import qrcode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode, InputFile
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackContext,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
    ConversationHandler
)
from dotenv import load_dotenv
import mercadopago
from flask import Flask, request, jsonify
import threading

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MP_ACCESS_TOKEN = os.getenv("MERCADO_PAGO_TOKEN")
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

ASK_NAME, ASK_PHONE, ASK_MAC = range(3)

MAC_REQUIRED_PRODUCTS = {
    "➕​ ASSIST+ R$ 65",
    "📱 NINJA PLAYER R$65",
    "📺 MEGA IPTV R$ 75",
    "🧠 SMART ONE R$60",
    "🎮 IBO PRO PLAYER R$50",
    "📡 IBO TV OFICIAL R$50",
    "🧩 DUPLECAST R$60",
    "🌐 BAY TV R$60",
    "🟣​ QUICK PLAYER R$65",
    "▶️​ TIVI PLAYER R$65",
    "🔥 SUPER PLAY R$50",
    "☁️ CLOUDDY R$65"
}

PRODUCT_CATALOG = {
    "ATIVAR APP": [
        {"name": "➕​ ASSIST+ R$ 65", "price": 65.00},
        {"name": "📱 NINJA PLAYER R$65", "price": 65.00},
        {"name": "📺 MEGA IPTV R$ 75", "price": 75.00},
        {"name": "🧠 SMART ONE R$60", "price": 70.00},
        {"name": "🎮 IBO PRO PLAYER R$50", "price": 50.00},
        {"name": "📡 IBO TV OFICIAL R$50", "price": 50.00},
        {"name": "🧩 DUPLECAST R$60", "price": 60.00},
        {"name": "🌐 BAY TV R$60", "price": 60.00},
        {"name": "🟣​ QUICK PLAYER R$65", "price": 65.00},
        {"name": "▶️​ TIVI PLAYER R$65", "price": 65.00},
        {"name": "🔥 SUPER PLAY R$50", "price": 50.00},
        {"name": "☁️ CLOUDDY R$65", "price": 65.00},
    ],
    "COMPRAR CRÉDITOS": [
        {"name": "🎯 X SERVER PLAY (13,50und)", "price": 13.50},
        {"name": "⚡ FAST PLAYER (13,50und)", "price": 13.50},
        {"name": "👑 GOLD PLAY (13,50und)", "price": 13.50},
        {"name": "📺 EI TV (13,50und)", "price": 13.50},
        {"name": "🛰️ Z TECH (13,50und)", "price": 13.50},
        {"name": "🧠 GENIAL PLAY (13,50und)", "price": 13.50},
        {"name": "🚀 UPPER PLAY (15,00und)", "price": 150.00},
    ]
}

# --- FLASK Webhook para validar pagamento automático
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if data.get('topic') == 'payment':
        payment = sdk.payment().get(data['id'])['response']
        if payment.get('status') == 'approved':
            chat_id = payment.get('external_reference')
            if chat_id:
                try:
                    updater.bot.send_message(chat_id=int(chat_id), text="✅ Pagamento confirmado com sucesso!")
                except Exception as e:
                    logging.error(f"Erro ao notificar usuário: {e}")
    return jsonify({'status': 'ok'})

def run_webhook():
    app.run(port=5000)

# --- Bot Telegram
def start(update: Update, context: CallbackContext) -> int:
    user_data = context.user_data
    if 'name' in user_data and 'phone' in user_data:
        update.message.reply_text("Olá novamente! Você já está cadastrado.\nUse /produtos para ver o catálogo.")
        return ConversationHandler.END
    update.message.reply_text("Olá! Por favor, diga seu nome para iniciar o cadastro:")
    return ASK_NAME

def ask_phone(update: Update, context: CallbackContext) -> int:
    context.user_data['name'] = update.message.text
    update.message.reply_text("Agora, por favor, envie seu telefone com DDD (somente números):")
    return ASK_PHONE

def save_phone(update: Update, context: CallbackContext) -> int:
    phone = update.message.text.strip()
    if not phone.isdigit():
        update.message.reply_text("❌ Por favor, envie um número de telefone válido contendo apenas dígitos.")
        return ASK_PHONE
    context.user_data['phone'] = phone
    name = context.user_data['name']
    update.message.reply_text(
        f"✅ Cadastro concluído!\nNome: {name}\nTelefone: {phone}\n\nUse /produtos para ver o catálogo."
    )
    return ConversationHandler.END

def produtos(update: Update, context: CallbackContext) -> None:
    keyboard = [[InlineKeyboardButton(f"📦 {cat}", callback_data=f"categoria:{cat}")] for cat in PRODUCT_CATALOG]
    keyboard.append([
        InlineKeyboardButton("💳 Comprar Créditos", callback_data="categoria:COMPRAR CRÉDITOS"),
        InlineKeyboardButton("🛒 Ver Carrinho", callback_data="ver_carrinho")
    ])
    update.message.reply_text("Escolha uma categoria:", reply_markup=InlineKeyboardMarkup(keyboard))

def button_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    data = query.data

    if data.startswith("categoria:"):
        categoria = data.split(":", 1)[1]
        produtos = PRODUCT_CATALOG.get(categoria, [])
        keyboard = [[InlineKeyboardButton(prod['name'], callback_data=f"produto:{prod['name']}:{prod['price']}")] for prod in produtos]
        keyboard.append([InlineKeyboardButton("⬅️ Voltar", callback_data="voltar")])
        query.edit_message_text(f"Produtos em *{categoria}*:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    elif data.startswith("produto:"):
        _, nome, preco = data.split(":", 2)
        preco_float = float(preco)
        context.user_data['selected_product'] = {'
