import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
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
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Estados da conversa
ASK_NAME, ASK_PHONE, ASK_MAC = range(3)

# Produtos que exigem MAC
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

# Catálogo
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

# Cancelar cadastro
def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Cadastro cancelado.")
    return ConversationHandler.END

# Listar produtos
def produtos(update: Update, context: CallbackContext) -> None:
    keyboard = [[InlineKeyboardButton(f"📦 {cat}", callback_data=f"categoria:{cat}")]
                for cat in PRODUCT_CATALOG]
    keyboard.append([InlineKeyboardButton("🛒 Ver Carrinho", callback_data="ver_carrinho")])
    update.message.reply_text("Escolha uma categoria:", reply_markup=InlineKeyboardMarkup(keyboard))

# Handler de botão
def button_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    data = query.data

    if data.startswith("categoria:"):
        categoria = data.split(":", 1)[1]
        produtos = PRODUCT_CATALOG.get(categoria, [])
        keyboard = [[InlineKeyboardButton(prod['name'], callback_data=f"produto:{prod['name']}:{prod['price']}")]
                    for prod in produtos]
        keyboard.append([InlineKeyboardButton("⬅️ Voltar", callback_data="voltar")])
        query.edit_message_text(f"Produtos em *{categoria}*:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data.startswith("produto:"):
        _, nome, preco = data.split(":", 2)
        preco_float = float(preco)
        context.user_data['selected_product'] = {'name': nome, 'price': preco_float}

        if nome in MAC_REQUIRED_PRODUCTS:
            query.edit_message_text(f"📲 Produto: *{nome}*\n\nPor favor, envie a MAC (12 dígitos alfanuméricos, sem `:`):", parse_mode='Markdown')
            return ASK_MAC
        else:
            cart = context.user_data.setdefault('cart', [])
            if any(item['name'] == nome for item in cart):
                query.edit_message_text(f"⚠️ O produto *{nome}* já está no carrinho.", parse_mode='Markdown')
            else:
                cart.append({'name': nome, 'price': preco_float})
                query.edit_message_text(f"✅ Produto *{nome}* foi adicionado ao carrinho!", parse_mode='Markdown')

    elif data == "ver_carrinho":
        return exibir_carrinho(update, context)

    elif data == "voltar":
        produtos(update, context)

    return ConversationHandler.END

# Receber MAC
def receive_mac(update: Update, context: CallbackContext) -> int:
    mac = update.message.text.strip().upper()
    if not (mac.isalnum() and len(mac) == 12):
        update.message.reply_text("❌ MAC inválida. Envie exatamente 12 caracteres alfanuméricos.")
        return ASK_MAC

    product = context.user_data.get('selected_product')
    if product:
        product['mac'] = mac
        cart = context.user_data.setdefault('cart', [])
        cart.append(product)
        update.message.reply_text(f"✅ Produto *{product['name']}* com MAC *{mac}* adicionado ao carrinho!", parse_mode='Markdown')
    else:
        update.message.reply_text("⚠️ Erro ao salvar produto.")

    return ConversationHandler.END

# Exibir carrinho
def exibir_carrinho(update: Update, context: CallbackContext) -> int:
    cart = context.user_data.get('cart', [])
    if not cart:
        update.callback_query.message.reply_text("🛒 Seu carrinho está vazio.")
        return ConversationHandler.END

    mensagem = "🛒 *Seu Carrinho:*\n\n"
    total = 0
    for item in cart:
        linha = f"• {item['name']}"
        if 'mac' in item:
            linha += f" (MAC: {item['mac']})"
        linha += f" - R$ {item['price']:.2f}"
        mensagem += linha + "\n"
        total += item['price']

    mensagem += f"\n──────────────\n💰 *Total: R$ {total:.2f}*"
    keyboard = [[InlineKeyboardButton("💳 Finalizar Compra", callback_data="finalizar_pagamento")]]
    update.callback_query.message.reply_text(mensagem, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# Finalizar compra
def finalizar_compra(update: Update, context: CallbackContext) -> None:
    cart = context.user_data.get('cart', [])
    if not cart:
        update.message.reply_text("🛒 Seu carrinho está vazio.")
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
            "success": "https://seusite.com/sucesso",
            "failure": "https://seusite.com/erro",
            "pending": "https://seusite.com/pendente"
        },
        "auto_return": "approved"
    }

    try:
        preference_response = sdk.preference().create(preference_data)
        preference = preference_response["response"]
        context.user_data['cart'] = []  # limpa carrinho
        keyboard = [[InlineKeyboardButton("💳 Pagar com Mercado Pago", url=preference["init_point"] )]]
        update.message.reply_text("Clique abaixo para finalizar seu pagamento:", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        update.message.reply_text("❌ Ocorreu um erro ao criar o link de pagamento.")
        logging.error(f"Erro ao criar preferencia: {e}")

# Main
def main() -> None:
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_NAME: [MessageHandler(Filters.text & ~Filters.command, ask_phone)],
            ASK_PHONE: [MessageHandler(Filters.text & ~Filters.command, save_phone)],
            ASK_MAC: [MessageHandler(Filters.text & ~Filters.command, receive_mac)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    dp.add_handler(conv_handler)
    dp.add_handler(CommandHandler("produtos", produtos))
    dp.add_handler(CommandHandler("finalizar_compra", finalizar_compra))
    dp.add_handler(CallbackQueryHandler(button_handler))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
