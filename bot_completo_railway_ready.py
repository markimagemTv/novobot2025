import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext, CallbackQueryHandler
import mercadopago

# Carrega variáveis de ambiente
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
MP_TOKEN = os.getenv("MERCADOPAGO_ACCESS_TOKEN")

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

# Callback para produto
def produto_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    _, categoria, index = query.data.split(":")
    produto = CATEGORIAS[categoria][int(index)]

    # Simula criação de preferência de pagamento
    preference_data = {
        "items": [
            {
                "title": produto["nome"],
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": float(produto["preco"])
            }
        ],
        "back_urls": {
            "success": "https://www.google.com",
            "failure": "https://www.google.com"
        },
        "auto_return": "approved"
    }

    preference_response = sdk.preference().create(preference_data)
    init_point = preference_response["response"]["init_point"]

    keyboard = [[InlineKeyboardButton("Pagar com Mercado Pago 💳", url=init_point)],
                [InlineKeyboardButton("⬅ Voltar", callback_data=f"cat:{categoria}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    query.edit_message_text(
        text=f"*{produto['nome']}*\nPreço: R${produto['preco']}\nClique abaixo para pagar:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

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
