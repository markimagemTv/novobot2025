import logging
import os
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton
)
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

# Carrega .env
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MP_ACCESS_TOKEN = os.getenv("MERCADO_PAGO_TOKEN")

if not TELEGRAM_TOKEN or not MP_ACCESS_TOKEN:
    raise ValueError("Tokens de ambiente não encontrados.")

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Estados da conversa
ASK_NAME, ASK_PHONE, ASK_MAC = range(3)

# Produtos que exigem MAC
MAC_REQUIRED_PRODUCTS = {
    "ASSIST+",
    "NINJA PLAYER",
    "MEGA IPTV",
    "SMART ONE",
    "IBO PRO PLAYER",
    "IBO TV OFICIAL",
    "DUPLECAST",
    "BAY TV",
    "QUICK PLAYER",
    "TIVI PLAYER",
    "SUPER PLAY",
    "CLOUDDY"
}

# Catálogo
PRODUCT_CATALOG = {
    "ATIVAR APP": [
        {"name": "ASSIST+", "price": 65.00},
        {"name": "NINJA PLAYER", "price": 65.00},
        {"name": "MEGA IPTV", "price": 75.00},
        {"name": "SMART ONE", "price": 70.00},
        {"name": "IBO PRO PLAYER", "price": 50.00},
        {"name": "IBO TV OFICIAL", "price": 50.00},
        {"name": "DUPLECAST", "price": 60.00},
        {"name": "BAY TV", "price": 60.00},
        {"name": "QUICK PLAYER", "price": 65.00},
        {"name": "TIVI PLAYER", "price": 65.00},
        {"name": "SUPER PLAY", "price": 50.00},
        {"name": "CLOUDDY", "price": 65.00},
    ],
    "COMPRAR CRÉDITOS": [
        {"name": "X SERVER PLAY", "price": 13.50},
        {"name": "FAST PLAYER", "price": 13.50},
        {"name": "GOLD PLAY", "price": 13.50},
        {"name": "EI TV", "price": 13.50},
        {"name": "Z TECH", "price": 13.50},
        {"name": "GENIAL PLAY", "price": 13.50},
        {"name": "UPPER PLAY", "price": 150.00},
    ]
}

def start(update: Update, context: CallbackContext) -> int:
    user_data = context.user_data
    if 'name' in user_data and 'phone' in user_data:
        update.message.reply_text("Olá novamente! Você já está cadastrado.\nUse /produtos para ver o catálogo.")
        return ConversationHandler.END
    update.message.reply_text("Olá! Por favor, diga seu nome para iniciar o cadastro:")
    return ASK_NAME

def ask_phone(update: Update, context: CallbackContext) -> int:
    context.user_data['name'] = update.message.text.strip()
    reply_markup = ReplyKeyboardMarkup(
        [[KeyboardButton("\ud83d\udcf1 Enviar meu telefone", request_contact=True)]],
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
        f"\u2705 Cadastro concluído!\nNome: {name}\nTelefone: {contact.phone_number}\n\nUse /produtos para ver o catálogo."
    )
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Cadastro cancelado.")
    return ConversationHandler.END

def produtos(update: Update, context: CallbackContext) -> None:
    keyboard = [[InlineKeyboardButton(f"\ud83d\udce6 {cat}", callback_data=f"categoria:{cat}")]
                for cat in PRODUCT_CATALOG]
    update.message.reply_text("Escolha uma categoria:", reply_markup=InlineKeyboardMarkup(keyboard))

def button_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    data = query.data

    if data.startswith("categoria:"):
        categoria = data.split(":", 1)[1]
        produtos = PRODUCT_CATALOG.get(categoria, [])
        keyboard = [[InlineKeyboardButton(f"{prod['name']} R$ {prod['price']:.2f}",
                                          callback_data=f"produto:{prod['name']}:{prod['price']}")]
                    for prod in produtos]
        query.edit_message_text(f"Produtos em *{categoria}*:",
                                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data.startswith("produto:"):
        _, nome, preco = data.split(":", 2)
        preco_float = float(preco)
        context.user_data['selected_product'] = {'name': nome, 'price': preco_float}

        if nome in MAC_REQUIRED_PRODUCTS:
            query.edit_message_text(f"\ud83d\udcf2 Produto: *{nome}*\n\nPor favor, envie a MAC (12 dígitos alfanuméricos, sem `:`):", parse_mode='Markdown')
            return ASK_MAC
        else:
            cart = context.user_data.setdefault('cart', [])
            cart.append({'name': nome, 'price': preco_float})
            query.edit_message_text(f"\u2705 Produto *{nome}* foi adicionado ao carrinho!", parse_mode='Markdown')

    return ConversationHandler.END

def receive_mac(update: Update, context: CallbackContext) -> int:
    mac = update.message.text.strip().upper()
    if not (mac.isalnum() and len(mac) == 12):
        update.message.reply_text("\u274c MAC inválida. Envie exatamente 12 caracteres alfanuméricos.")
        return ASK_MAC

    product = context.user_data.get('selected_product')
    if product:
        product['mac'] = mac
        cart = context.user_data.setdefault('cart', [])
        cart.append(product)
        update.message.reply_text(f"\u2705 Produto *{product['name']}* com MAC *{mac}* adicionado ao carrinho!", parse_mode='Markdown')
    else:
        update.message.reply_text("\u26a0\ufe0f Erro ao salvar produto.")

    return ConversationHandler.END

def carrinho(update: Update, context: CallbackContext) -> None:
    cart = context.user_data.get('cart', [])
    if not cart:
        update.message.reply_text("\ud83d\uded2 Seu carrinho está vazio.")
        return

    mensagem = "\ud83d\uded2 *Seu Carrinho:*\n\n"
    total = 0
    for item in cart:
        linha = f"\u2022 {item['name']}"
        if 'mac' in item:
            linha += f" (MAC: {item['mac']})"
        linha += f" - R$ {item['price']:.2f}"
        mensagem += linha + "\n"
        total += item['price']

    mensagem += f"\n\ud83d\udcb0 *Total: R$ {total:.2f}*"
    update.message.reply_text(mensagem, parse_mode='Markdown')

def finalizar_compra(update: Update, context: CallbackContext) -> None:
    cart = context.user_data.get('cart', [])
    if not cart:
        update.message.reply_text("\ud83d\uded2 Seu carrinho está vazio.")
        return

    items = [{
        "title": item['name'] + (f" (MAC: {item['mac']})" if 'mac' in item else ""),
        "quantity": 1,
        "currency_id": "BRL",
        "unit_price": item['price']
    } for item in cart]

    preference_data = {
        "items": items,
        "back_urls": {
            "success": "https://www.seusite.com/sucesso",
            "failure": "https://www.seusite.com/erro",
            "pending": "https://www.seusite.com/pendente"
        },
        "auto_return": "approved"
    }

    try:
        preference_response = sdk.preference().create(preference_data)
        preference = preference_response["response"]
    except Exception as e:
        logging.error(f"Erro ao criar preferência Mercado Pago: {e}")
        update.message.reply_text("❌ Erro ao gerar link de pagamento. Tente novamente mais tarde.")
        return

    context.user_data['cart'] = []  # limpa carrinho

    keyboard = [[InlineKeyboardButton("\ud83d\udcb3 Pagar com Mercado Pago", url=preference["init_point"] )]]
    update.message.reply_text("Clique abaixo para finalizar seu pagamento:", reply_markup=InlineKeyboardMarkup(keyboard))

def main() -> None:
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_NAME: [MessageHandler(Filters.text & ~Filters.command, ask_phone)],
            ASK_PHONE: [MessageHandler(Filters.contact, save_phone)],
            ASK_MAC: [MessageHandler(Filters.text & ~Filters.command, receive_mac)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    dp.add_handler(conv_handler)
    dp.add_handler(CommandHandler("produtos", produtos))
    dp.add_handler(CommandHandler("carrinho", carrinho))
    dp.add_handler(CommandHandler("finalizar_compra", finalizar_compra))
    dp.add_handler(CallbackQueryHandler(button_handler))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
