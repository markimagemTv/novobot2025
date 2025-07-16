import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
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

# Carrega variáveis do .env
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MP_ACCESS_TOKEN = os.getenv("MERCADO_PAGO_TOKEN")
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Estados da conversa
ASK_NAME, ASK_PHONE = range(2)

# Catálogo de produtos
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

# Cadastro inicial
def start(update: Update, context: CallbackContext) -> int:
    user_data = context.user_data
    if 'name' in user_data and 'phone' in user_data:
        update.message.reply_text("Olá novamente, você já está cadastrado!\nUse /produtos para ver o catálogo.")
        return ConversationHandler.END
    else:
        update.message.reply_text("Olá! Antes de continuar, por favor me diga seu nome:")
        return ASK_NAME

def ask_phone(update: Update, context: CallbackContext) -> int:
    context.user_data['name'] = update.message.text
    reply_markup = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Enviar meu telefone", request_contact=True)]],
        one_time_keyboard=True,
        resize_keyboard=True
    )
    update.message.reply_text("Agora, clique abaixo para enviar seu telefone:", reply_markup=reply_markup)
    return ASK_PHONE

def save_phone(update: Update, context: CallbackContext) -> int:
    contact = update.message.contact
    context.user_data['phone'] = contact.phone_number
    name = context.user_data['name']

    update.message.reply_text(
        f"✅ Cadastro concluído!\nNome: {name}\nTelefone: {contact.phone_number}\n\nUse /produtos para ver o catálogo.",
        reply_markup=InlineKeyboardMarkup([])
    )
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Cadastro cancelado.")
    return ConversationHandler.END

# Produtos
def produtos(update: Update, context: CallbackContext) -> None:
    keyboard = []
    for categoria in PRODUCT_CATALOG:
        keyboard.append([InlineKeyboardButton(f"📦 {categoria}", callback_data=f"categoria:{categoria}")])
    update.message.reply_text("Escolha uma categoria:", reply_markup=InlineKeyboardMarkup(keyboard))

# Handler dos botões
def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    data = query.data

    if data.startswith("categoria:"):
        categoria = data.split(":", 1)[1]
        produtos = PRODUCT_CATALOG.get(categoria, [])
        keyboard = []
        for produto in produtos:
            callback_data = f"produto:{produto['name']}:{produto['price']}"
            keyboard.append([InlineKeyboardButton(produto['name'], callback_data=callback_data)])
        query.edit_message_text(f"Produtos em *{categoria}*:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data.startswith("produto:"):
        _, nome, preco = data.split(":", 2)
        preco_float = float(preco)

        preference_data = {
            "items": [{
                "title": nome,
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": preco_float
            }],
            "back_urls": {
                "success": "https://www.google.com",
                "failure": "https://www.google.com",
                "pending": "https://www.google.com"
            },
            "auto_return": "approved"
        }

        preference_response = sdk.preference().create(preference_data)
        preference = preference_response["response"]

        keyboard = [[InlineKeyboardButton("💳 Pagar com Mercado Pago", url=preference["init_point"])]]
        query.edit_message_text(f"Produto: *{nome}*\nPreço: R$ {preco_float:.2f}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# Main
def main() -> None:
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Conversa de cadastro
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_NAME: [MessageHandler(Filters.text & ~Filters.command, ask_phone)],
            ASK_PHONE: [MessageHandler(Filters.contact, save_phone)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    dp.add_handler(conv_handler)
    dp.add_handler(CommandHandler("produtos", produtos))
    dp.add_handler(CallbackQueryHandler(button_handler))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
