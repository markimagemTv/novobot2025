import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext, CallbackQueryHandler
from dotenv import load_dotenv
import mercadopago

# Carrega variáveis do .env
load_dotenv()

# Configurações
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MP_ACCESS_TOKEN = os.getenv("MERCADO_PAGO_TOKEN")

# Inicializa cliente Mercado Pago
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# Configura logger
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

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

# Comando /start
def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("Olá! Eu sou um bot com integração Mercado Pago.\nUse /produtos para ver o catálogo.")

# Comando /produtos
def produtos(update: Update, context: CallbackContext) -> None:
    keyboard = []

    for categoria, produtos in PRODUCT_CATALOG.items():
        keyboard.append([InlineKeyboardButton(f"📦 {categoria}", callback_data=f"categoria:{categoria}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Escolha uma categoria:", reply_markup=reply_markup)

# Lida com cliques em categorias ou produtos
def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    data = query.data

    if data.startswith("categoria:"):
        categoria = data.split(":")[1]
        produtos = PRODUCT_CATALOG.get(categoria, [])
        keyboard = []

        for produto in produtos:
            callback_data = f"produto:{produto['name']}:{produto['price']}"
            keyboard.append([InlineKeyboardButton(produto['name'], callback_data=callback_data)])

        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text=f"Produtos em *{categoria}*:", reply_markup=reply_markup, parse_mode='Markdown')

    elif data.startswith("produto:"):
        _, nome, preco = data.split(":", 2)
        preco_float = float(preco)

        # Cria preferência Mercado Pago
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
        reply_markup = InlineKeyboardMarkup(keyboard)

        query.edit_message_text(f"Produto: *{nome}*\nPreço: R$ {preco_float:.2f}", reply_markup=reply_markup, parse_mode='Markdown')

# Inicialização
def main() -> None:
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("produtos", produtos))
    dp.add_handler(CallbackQueryHandler(button_handler))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
