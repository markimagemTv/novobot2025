import os
import json
import logging
import requests
from uuid import uuid4
from datetime import datetime
from telegram import (
    Bot, Update, KeyboardButton, ReplyKeyboardMarkup,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Updater, CommandHandler, CallbackContext,
    ConversationHandler, MessageHandler, Filters, CallbackQueryHandler
)
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
ADMIN_ID = list(map(int, os.getenv("ADMIN_ID", "").split(",")))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Estados
REGISTER_NAME, REGISTER_PHONE, SELECT_CATEGORY, SELECT_PRODUCT, INPUT_MAC, CART_CONFIRM, PAYMENT_METHOD, ADMIN_MENU, ADMIN_NOTIFY_DELIVERY = range(9)

# Dados em memória
users = {}
carts = {}
orders = {}

products = {
    "ATIVAR APP": [
        {"id": "mega_iptv", "name": "Mega IPTV", "price": 75.0, "require_mac": True}
    ],
    "COMPRAR CRÉDITOS": [
        {"id": "fast_play_10", "name": "FAST PLAY 10", "price": 13.5},
        {"id": "fast_play_20", "name": "FAST PLAY 20", "price": 27.0},
        {"id": "fast_play_30", "name": "FAST PLAY 30", "price": 40.5},
    ]
}

def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in users:
        update.message.reply_text("Bem-vindo! Qual o seu nome?")
        return REGISTER_NAME
    return main_menu(update, context)

def register_name(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    users[user_id] = {"name": update.message.text}
    update.message.reply_text("Agora, envie seu telefone:")
    return REGISTER_PHONE

def register_phone(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    users[user_id]["phone"] = update.message.text
    return main_menu(update, context)

def main_menu(update: Update, context: CallbackContext):
    buttons = [[KeyboardButton("\U0001F6D2 Loja")], [KeyboardButton("\U0001F4E6 Meu Carrinho")], [KeyboardButton("\U0001F464 Meu Perfil")]]
    if update.effective_user.id in ADMIN_IDS:
        buttons.append([KeyboardButton("\u2699\ufe0f Menu Administrativo")])
    update.message.reply_text("Menu Principal:", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True))
    return SELECT_CATEGORY

def category_menu(update: Update, context: CallbackContext):
    text = update.message.text
    if text == "\U0001F6D2 Loja":
        keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat_{cat}")] for cat in products.keys()]
        update.message.reply_text("Escolha uma categoria:", reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECT_PRODUCT
    elif text == "\U0001F4E6 Meu Carrinho":
        return show_cart(update, context)
    elif text == "\U0001F464 Meu Perfil":
        user = users[update.effective_user.id]
        update.message.reply_text(f"Nome: {user['name']}\nTelefone: {user['phone']}")
        return SELECT_CATEGORY
    elif text == "\u2699\ufe0f Menu Administrativo":
        if update.effective_user.id in ADMIN_IDS:
            return admin_menu(update, context)
        else:
            update.message.reply_text("Acesso negado.")
    return SELECT_CATEGORY

def cat_selected(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    category = query.data.replace("cat_", "")
    keyboard = []
    for prod in products[category]:
        keyboard.append([InlineKeyboardButton(f"{prod['name']} - R${prod['price']:.2f}", callback_data=f"prod_{prod['id']}")])
    query.edit_message_text("Escolha um produto:", reply_markup=InlineKeyboardMarkup(keyboard))
    return INPUT_MAC

def product_selected(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    prod_id = query.data.replace("prod_", "")
    for category in products:
        for p in products[category]:
            if p['id'] == prod_id:
                context.user_data['selected_product'] = p
                if p.get("require_mac"):
                    query.edit_message_text("Digite o MAC (sem ':' ou '-' e com 12 caracteres):")
                    return INPUT_MAC
                else:
                    return add_to_cart(update, context)


def input_mac(update: Update, context: CallbackContext):
    mac = update.message.text.strip()
    if len(mac) != 12:
        update.message.reply_text("MAC inválido. Deve ter 12 caracteres.")
        return INPUT_MAC
    context.user_data['selected_product']['mac'] = mac
    return add_to_cart(update, context)

def add_to_cart(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    product = context.user_data['selected_product']
    carts.setdefault(user_id, []).append({"product": product})
    update.message.reply_text(f"Produto '{product['name']}' adicionado ao carrinho!")
    return SELECT_CATEGORY

def show_cart(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_cart = carts.get(user_id, [])
    if not user_cart:
        update.message.reply_text("Seu carrinho está vazio.")
        return SELECT_CATEGORY
    msg = "Seu carrinho:\n"
    total = 0
    for item in user_cart:
        p = item['product']
        msg += f"- {p['name']} - R${p['price']:.2f}\n"
        if 'mac' in p:
            msg += f"  MAC: `{p['mac']}`\n"
        total += p['price']
    msg += f"\nTotal: R${total:.2f}"
    keyboard = [[
        InlineKeyboardButton("Checkout PIX", callback_data="checkout"),
        InlineKeyboardButton("Limpar", callback_data="clear_cart")
    ], [
        InlineKeyboardButton("\u2B05\ufe0f Voltar", callback_data="back_menu")
    ]]
    update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return CART_CONFIRM

def cart_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    if query.data == "checkout":
        query.edit_message_text("Processando pagamento via PIX...")
        return payment_method_handler(update, context)
    elif query.data == "clear_cart":
        carts[user_id] = []
        query.edit_message_text("Carrinho esvaziado.")
        return SELECT_CATEGORY
    else:
        query.edit_message_text("Voltando...")
        return SELECT_CATEGORY

def payment_method_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    user_cart = carts.get(user_id, [])
    if not user_cart:
        query.edit_message_text("Seu carrinho está vazio.")
        return SELECT_CATEGORY

    items = [{
        "title": item["product"]["name"],
        "quantity": 1,
        "currency_id": "BRL",
        "unit_price": float(item["product"]["price"])
    } for item in user_cart]

    preference_data = {
        "items": items,
        "payment_methods": {
            "excluded_payment_types": [{"id": "credit_card"}]
        }
    }

    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    response = requests.post(
        "https://api.mercadopago.com/checkout/preferences",
        headers=headers,
        data=json.dumps(preference_data)
    )
    data = response.json()

    order_id = str(uuid4())[:8].upper()
    orders[order_id] = {
        "user_id": user_id,
        "items": user_cart,
        "total": sum(item["product"]["price"] for item in user_cart),
        "status": "Pago (PIX)",
        "timestamp": datetime.now().isoformat()
    }
    carts[user_id] = []
    query.edit_message_text(
        f"✅ Pagamento via PIX confirmado!\n\nPedido {order_id} finalizado. Obrigado!"
    )
    return SELECT_CATEGORY

def admin_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Pedidos", callback_data="admin_orders")],
        [InlineKeyboardButton("Relatório Mensal", callback_data="admin_reports")],
        [InlineKeyboardButton("Notificar Entrega", callback_data="admin_notify_delivery")],
        [InlineKeyboardButton("\u2B05\ufe0f Voltar", callback_data="admin_back")]
    ]
    update.message.reply_text("Menu Administrativo:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_MENU

def admin_menu_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data

    if data == "admin_orders":
        msg = "Pedidos recentes:\n"
        for oid, info in list(orders.items())[-5:]:
            msg += f"- ID: {oid} | Total: R${info['total']:.2f}\n"
        query.edit_message_text(msg)
        return ADMIN_MENU

    elif data == "admin_reports":
        month = datetime.now().strftime("%Y-%m")
        total = sum(order['total'] for order in orders.values() if order['timestamp'].startswith(month))
        query.edit_message_text(f"Total de vendas em {month}: R${total:.2f}")
        return ADMIN_MENU

    elif data == "admin_notify_delivery":
        query.edit_message_text("Envie o ID do pedido para notificar entrega:")
        return ADMIN_NOTIFY_DELIVERY

    elif data == "admin_back":
        query.edit_message_text("Voltando ao menu principal.")
        return SELECT_CATEGORY

    return ADMIN_MENU

def admin_notify_delivery(update: Update, context: CallbackContext):
    order_id = update.message.text.strip()
    if order_id not in orders:
        update.message.reply_text("Pedido não encontrado.")
        return ADMIN_NOTIFY_DELIVERY
    user_id = orders[order_id]['user_id']
    context.bot.send_message(chat_id=user_id, text=f"Seu pedido {order_id} foi entregue!")
    update.message.reply_text("Cliente notificado.")
    return SELECT_CATEGORY

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            REGISTER_NAME: [MessageHandler(Filters.text & ~Filters.command, register_name)],
            REGISTER_PHONE: [MessageHandler(Filters.text & ~Filters.command, register_phone)],
            SELECT_CATEGORY: [MessageHandler(Filters.text & ~Filters.command, category_menu)],
            SELECT_PRODUCT: [CallbackQueryHandler(cat_selected, pattern="^cat_.*")],
            INPUT_MAC: [
                CallbackQueryHandler(product_selected, pattern="^prod_.*"),
                MessageHandler(Filters.text & ~Filters.command, input_mac)
            ],
            CART_CONFIRM: [CallbackQueryHandler(cart_handler)],
            PAYMENT_METHOD: [CallbackQueryHandler(payment_method_handler)],
            ADMIN_MENU: [CallbackQueryHandler(admin_menu_handler)],
            ADMIN_NOTIFY_DELIVERY: [MessageHandler(Filters.text & ~Filters.command, admin_notify_delivery)],
        },
        fallbacks=[CommandHandler("start", start)]
    )

    dp.add_handler(conv_handler)
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
