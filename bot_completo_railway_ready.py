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
    keyboard = [[InlineKeyboardButton(f"📦 {cat}", callback_data=f"categoria:{cat}")] for cat in PRODUCT_CATALOG]
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
        keyboard = [[InlineKeyboardButton(prod['name'], callback_data=f"produto:{prod['name']}:{prod['price']}")] for prod in produtos]
        keyboard.append([InlineKeyboardButton("⬅️ Voltar", callback_data="voltar")])
        query.edit_message_text(f"Produtos em *{categoria}*:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    elif data.startswith("produto:"):
        _, nome, preco = data.split(":", 2)
        preco_float = float(preco)
        context.user_data['selected_product'] = {'name': nome, 'price': preco_float}

        if nome in MAC_REQUIRED_PRODUCTS:
            query.edit_message_text(f"📲 Produto: *{nome}*\n\nPor favor, envie a MAC (12 dígitos alfanuméricos, sem `:`):", parse_mode=ParseMode.MARKDOWN)
            return ASK_MAC
        else:
            cart = context.user_data.setdefault('cart', [])
            if any(item['name'] == nome for item in cart):
                query.edit_message_text(f"⚠️ O produto *{nome}* já está no carrinho.", parse_mode=ParseMode.MARKDOWN)
            else:
                cart.append({'name': nome, 'price': preco_float})
                query.edit_message_text(f"✅ Produto *{nome}* foi adicionado ao carrinho!", parse_mode=ParseMode.MARKDOWN)

    elif data == "ver_carrinho":
        return exibir_carrinho(update, context)

    elif data == "voltar":
        produtos(update, context)

    elif data == "finalizar_pagamento":
        finalizar_compra(update, context)

    return ConversationHandler.END

# Receber MAC e gerar pagamento com QR code
def receive_mac(update: Update, context: CallbackContext) -> int:
    mac = update.message.text.strip().upper()
    if not (mac.isalnum() and len(mac) == 12):
        update.message.reply_text("❌ MAC inválida. Envie exatamente 12 caracteres alfanuméricos.")
        return ASK_MAC

    product = context.user_data.get('selected_product')
    if product:
        cart = context.user_data.setdefault('cart', [])
        if any(item['name'] == product['name'] and item.get('mac') == mac for item in cart):
            update.message.reply_text(f"⚠️ O produto *{product['name']}* com MAC *{mac}* já está no carrinho!", parse_mode=ParseMode.MARKDOWN)
            return ConversationHandler.END
        else:
            product_with_mac = product.copy()
            product_with_mac['mac'] = mac
            cart.append(product_with_mac)
            update.message.reply_text(f"✅ Produto *{product['name']}* com MAC *{mac}* adicionado ao carrinho!", parse_mode=ParseMode.MARKDOWN)

            # Limpa produto selecionado
            context.user_data.pop('selected_product', None)

            # Gera pagamento Pix e envia QR code
            enviar_link_pix_com_qr(update, context, cart)

            return ConversationHandler.END
    else:
        update.message.reply_text("⚠️ Erro ao salvar produto.")
        return ConversationHandler.END

# Função para gerar preferência Pix com Mercado Pago e enviar QR code no Telegram
def enviar_link_pix_com_qr(update: Update, context: CallbackContext, cart: list) -> None:
    try:
        total = sum(item['price'] for item in cart)
        # Criar preferência MERCADO PAGO sem itens, pois vamos usar pagamento direto Pix (você pode ajustar se quiser manter itens)
        # Aqui vamos criar um pagamento Pix direto via API MercadoPago (customizando)
        payment_data = {
            "transaction_amount": total,
            "description": "Compra via Telegram",
            "payment_method_id": "pix",
            "payer": {
                "email": "cliente@example.com"  # pode ser genérico ou usar email real se tiver
            }
        }
        payment_response = sdk.payment().create(payment_data)
        payment = payment_response["response"]

        pix_info = payment.get("point_of_interaction", {}).get("transaction_data", {})
        qr_code = pix_info.get("qr_code")
        qr_code_base64 = pix_info.get("qr_code_base64")

        if not qr_code:
            update.message.reply_text("❌ Não foi possível gerar o QR code PIX. Tente novamente mais tarde.")
            return

        # Gerar imagem do QR code a partir do texto QR code
        img = qrcode.make(qr_code)
        bio = io.BytesIO()
        img.save(bio, format='PNG')
        bio.seek(0)

        # Enviar imagem do QR code no Telegram junto com o link de pagamento
        update.message.reply_photo(photo=InputFile(bio, filename="pix.png"),
                                  caption=f"💳 Total: R$ {total:.2f}\n\n"
                                          f"📲 Escaneie o QR code acima para pagar via PIX.\n"
                                          f"Ou clique no link abaixo para pagar:\n"
                                          f"{payment['transaction_details']['external_resource_url']}")

        # Limpa carrinho após enviar
        context.user_data['cart'] = []

    except Exception as e:
        logging.error(f"Erro ao criar pagamento Pix: {e}")
        update.message.reply_text("❌ Ocorreu um erro ao criar o pagamento Pix.")

# Exibir carrinho com opção de finalizar
def exibir_carrinho(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    cart = context.user_data.get('cart', [])
    if not cart:
        query.edit_message_text("🛒 Seu carrinho está vazio.")
        return ConversationHandler.END

    texto = "🛒 *Seu carrinho:*\n"
    total = 0
    for item in cart:
        nome = item['name']
        preco = item['price']
        mac = item.get('mac')
        texto += f"- {nome}" + (f" (MAC: {mac})" if mac else "") + f": R$ {preco:.2f}\n"
        total += preco
    texto += f"\n*Total: R$ {total:.2f}*"

    keyboard = [[InlineKeyboardButton("Finalizar Pagamento", callback_data="finalizar_pagamento")],
                [InlineKeyboardButton("Continuar Comprando", callback_data="voltar")]]
    query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END

# Finalizar compra - gera QR code Pix se carrinho não vazio
def finalizar_compra(update: Update, context: CallbackContext) -> None:
    if update.callback_query:
        update.callback_query.answer()
        user_message = update.callback_query.message
    else:
        user_message = update.message

    cart = context.user_data.get('cart', [])
    if not cart:
        user_message.reply_text("🛒 Seu carrinho está vazio.")
        return

    enviar_link_pix_com_qr(update, context, cart)

# Setup do bot e handlers
def main() -> None:
    updater = Updater(TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            ASK_NAME: [MessageHandler(Filters.text & ~Filters.command, ask_phone)],
            ASK_PHONE: [MessageHandler(Filters.text & ~Filters.command, save_phone)],
            ASK_MAC: [MessageHandler(Filters.text & ~Filters.command, receive_mac)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(CommandHandler('produtos', produtos))
    dispatcher.add_handler(CallbackQueryHandler(button_handler))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
