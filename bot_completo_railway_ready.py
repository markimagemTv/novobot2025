import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext, CallbackQueryHandler
from dotenv import load_dotenv
import mercadopago
import requests

# Carrega variáveis do .env
load_dotenv()

# Configurações
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")

# Configura logger
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

# Inicializa cliente do Mercado Pago
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "Olá! Eu sou um bot com integração Mercado Pago.\nDigite /pagar para gerar um link de pagamento."
    )

def pagar(update: Update, context: CallbackContext) -> None:
    preference_data = {
        "items": [
            {
                "title": "Produto de Exemplo",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": 10.00
            }
        ],
        "back_urls": {
            "success": "https://www.google.com",
            "failure": "https://www.google.com",
            "pending": "https://www.google.com"
        },
        "auto_return": "approved"
    }

    preference_response = sdk.preference().create(preference_data)
    preference = preference_response["response"]

    keyboard = [[InlineKeyboardButton("Pagar com Mercado Pago", url=preference["init_point"])]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text("Clique no botão abaixo para pagar:", reply_markup=reply_markup)

def main() -> None:
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("pagar", pagar))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
