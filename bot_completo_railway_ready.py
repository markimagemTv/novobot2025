import logging
import os
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters,
    CallbackQueryHandler, CallbackContext, ConversationHandler
)
import mercadopago
import requests
from datetime import datetime
import json

load_dotenv()

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token e MercadoPago token via .env
TOKEN = os.getenv('TELEGRAM_TOKEN')
MP_ACCESS_TOKEN = os.getenv('MERCADO_PAGO_TOKEN')

# MercadoPago client
mp = mercadopago.SDK(MP_ACCESS_TOKEN)

# Estados para ConversationHandler
(
    REGISTER_NAME, REGISTER_PHONE,
    SELECT_CATEGORY, SELECT_PRODUCT,
    INPUT_MAC, CART_CONFIRM,
    PAYMENT_METHOD, ADMIN_MENU,
    ADMIN_ORDERS, ADMIN_REPORTS,
    ADMIN_NOTIFY_DELIVERY
) = range(11)

# Produtos e categorias
CATEGORIES = {
    "ATIVAR APP": [
        {
            "id": "mega_iptv",
            "name": "Mega IPTV",
            "price": 75.00,
            "desc": "Solicita MAC sem ':'",
            "requires_mac": True
        }
    ],
    "COMPRAR CRÉDITOS": [
        {
            "id": "fast_play_10",
            "name": "Fast Play - 10 créditos",
            "price": 13.50 * 10,
            "credits": 10,
            "requires_mac": False
        },
        {
            "id": "fast_play_20",
            "name": "Fast Play - 20 créditos",
            "price": 13.50 * 20,
            "credits": 20,
            "requires_mac": False
        },
        {
            "id": "fast_play_30",
            "name": "Fast Play - 30 créditos",
            "price": 13.50 * 30,
            "credits": 30,
            "requires_mac": False
        }
    ]
}

# Dados dos usuários armazenados em arquivo json para simplicidade
USERS_DB = "users.json"
ORDERS_DB = "orders.json"

def load_json_db(filename):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json_db(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

users = load_json_db(USERS_DB)
orders = load_json_db(ORDERS_DB)

def start(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    if user_id not in users:
        update.message.reply_text(
            "Olá! Para começar, preciso que você faça seu cadastro.\nQual seu nome completo?"
        )
        return REGISTER_NAME
    else:
        return main_menu(update, context)

def register_name(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    users[user_id] = {
        "name": update.message.text,
        "phone": None,
        "cart": []
    }
    save_json_db(USERS_DB, users)
    update.message.reply_text("Ótimo! Agora me informe seu telefone (ex: +5511999999999)")
    return REGISTER_PHONE

def register_phone(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    phone = update.message.text
    # Simples validação básica do telefone
    if len(phone) < 10:
        update.message.reply_text("Número muito curto, por favor digite um telefone válido.")
        return REGISTER_PHONE
    users[user_id]["phone"] = phone
    save_json_db(USERS_DB, users)
    update.message.reply_text(f"Cadastro concluído! Seja bem-vindo, {users[user_id]['name']}!")
    return main_menu(update, context)

def main_menu(update: Update, context: CallbackContext):
    keyboard = [
        [KeyboardButton("🛒 Loja")],
        [KeyboardButton("📦 Meu Carrinho")],
        [KeyboardButton("👤 Meu Perfil")],
    ]

    # Se usuário for admin, mostrar botão admin
    user_id = str(update.effective_user.id)
    if user_id == os.getenv("ADMIN_ID"):
        keyboard.append([KeyboardButton("⚙️ Menu Administrativo")])

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    update.message.reply_text("Escolha uma opção:", reply_markup=reply_markup)
    return SELECT_CATEGORY

def category_menu(update: Update, context: CallbackContext):
    text = update.message.text
    if text == "🛒 Loja":
        keyboard = []
        for cat in CATEGORIES.keys():
            keyboard.append([InlineKeyboardButton(cat, callback_data=f"cat_{cat}")])
        update.message.reply_text("Escolha a categoria:", reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECT_PRODUCT
    elif text == "📦 Meu Carrinho":
        return show_cart(update, context)
    elif text == "👤 Meu Perfil":
        user_id = str(update.effective_user.id)
        user = users.get(user_id, {})
        update.message.reply_text(
            f"Nome: {user.get('name', 'Não cadastrado')}\nTelefone: {user.get('phone', 'Não cadastrado')}"
        )
        return SELECT_CATEGORY
    elif text == "⚙️ Menu Administrativo":
        if str(update.effective_user.id) == os.getenv("ADMIN_ID"):
            return admin_menu(update, context)
        else:
            update.message.reply_text("Você não tem permissão para acessar o menu administrativo.")
            return SELECT_CATEGORY
    else:
        update.message.reply_text("Opção inválida, escolha no menu abaixo.")
        return main_menu(update, context)

def cat_selected(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    category = query.data.split("_", 1)[1]
    context.user_data["category"] = category

    keyboard = []
    for prod in CATEGORIES[category]:
        keyboard.append([InlineKeyboardButton(f"{prod['name']} - R$ {prod['price']:.2f}", callback_data=f"prod_{prod['id']}")])

    query.edit_message_text(f"Categoria: {category}\nEscolha o produto:", reply_markup=InlineKeyboardMarkup(keyboard))
    return INPUT_MAC if any(p.get("requires_mac") for p in CATEGORIES[category]) else CART_CONFIRM

def product_selected(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    prod_id = query.data.split("_", 1)[1]
    context.user_data["selected_product"] = prod_id
    category = context.user_data.get("category")

    product = next((p for p in CATEGORIES[category] if p["id"] == prod_id), None)
    if not product:
        query.edit_message_text("Produto inválido.")
        return main_menu(update, context)

    if product.get("requires_mac"):
        query.edit_message_text("Por favor, informe o MAC sem ':' (exemplo: 001122334455):")
        return INPUT_MAC
    else:
        # Adiciona direto no carrinho para produtos sem MAC
        user_id = str(update.effective_user.id)
        users[user_id]["cart"].append({
            "product_id": prod_id,
            "name": product["name"],
            "price": product["price"],
            "mac": None,
            "quantity": 1
        })
        save_json_db(USERS_DB, users)
        query.edit_message_text(f"Produto {product['name']} adicionado ao carrinho.")
        return show_cart(update, context)

def input_mac(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    mac = update.message.text.strip().replace(":", "").lower()

    # Validação básica MAC - 12 caracteres hexadecimais
    if len(mac) != 12 or any(c not in "0123456789abcdef" for c in mac):
        update.message.reply_text("MAC inválido. Digite novamente sem ':', somente 12 caracteres hexadecimais.")
        return INPUT_MAC

    prod_id = context.user_data.get("selected_product")
    category = context.user_data.get("category")
    product = next((p for p in CATEGORIES[category] if p["id"] == prod_id), None)

    if not product:
        update.message.reply_text("Produto inválido, por favor reinicie o pedido.")
        return main_menu(update, context)

    # Adiciona ao carrinho com mac
    users[user_id]["cart"].append({
        "product_id": prod_id,
        "name": product["name"],
        "price": product["price"],
        "mac": mac,
        "quantity": 1
    })
    save_json_db(USERS_DB, users)

    update.message.reply_text(
        f"Produto {product['name']} adicionado ao carrinho.\nMAC copiable: `{mac}`",
        parse_mode="Markdown"
    )
    return show_cart(update, context)

def show_cart(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    cart = users[user_id].get("cart", [])
    if not cart:
        update.message.reply_text("Seu carrinho está vazio. Volte à loja para adicionar produtos.")
        return main_menu(update, context)

    msg = "🛒 Seu Carrinho:\n\n"
    total = 0
    for i, item in enumerate(cart, 1):
        msg += f"{i}. {item['name']} - R$ {item['price']:.2f}\n"
        if item.get("mac"):
            msg += f"   MAC: `{item['mac']}`\n"
        total += item["price"] * item.get("quantity", 1)
    msg += f"\nTotal: R$ {total:.2f}"

    keyboard = [
        [InlineKeyboardButton("Finalizar Compra", callback_data="checkout")],
        [InlineKeyboardButton("Limpar Carrinho", callback_data="clear_cart")],
        [InlineKeyboardButton("Voltar ao Menu", callback_data="back_menu")]
    ]

    if update.callback_query:
        update.callback_query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return CART_CONFIRM

def cart_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data
    user_id = str(update.effective_user.id)

    if data == "checkout":
        return checkout_start(update, context)
    elif data == "clear_cart":
        users[user_id]["cart"] = []
        save_json_db(USERS_DB, users)
        query.edit_message_text("Carrinho limpo com sucesso.")
        return main_menu(update, context)
    elif data == "back_menu":
        query.delete_message()
        return main_menu(update, context)
    else:
        query.answer("Opção inválida.")
        return CART_CONFIRM

def checkout_start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("PIX", callback_data="pay_pix")],
        # Pode-se adicionar cartão ou outros meios aqui
        [InlineKeyboardButton("Cancelar", callback_data="cancel_checkout")]
    ]
    update.callback_query.edit_message_text("Escolha o método de pagamento:", reply_markup=InlineKeyboardMarkup(keyboard))
    return PAYMENT_METHOD

def payment_method_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    choice = query.data
    user_id = str(update.effective_user.id)
    cart = users[user_id].get("cart", [])

    if choice == "pay_pix":
        # Criar preferência no MercadoPago
        items = []
        for item in cart:
            items.append({
                "title": item["name"],
                "quantity": 1,
                "unit_price": item["price"]
            })

        preference_data = {
            "items": items,
            "payment_methods": {
                "excluded_payment_types": [{"id": "credit_card"}],  # só pix
                "excluded_payment_methods": []
            },
            "auto_return": "approved",
            "back_urls": {
                "success": "https://t.me/seu_bot",  # Ajustar depois
                "failure": "https://t.me/seu_bot",
                "pending": "https://t.me/seu_bot"
            },
            "notification_url": os.getenv("MP_NOTIFICATION_URL", "")  # Webhook para notificações MercadoPago, opcional
        }

        preference_response = mp.preference().create(preference_data)
        preference = preference_response["response"]

        # Pegar QR Code e código PIX (se disponível)
        qr_code_base64 = None
        pix_code = None
        try:
            qr_code_base64 = preference["point_of_interaction"]["transaction_data"]["qr_code_base64"]
            pix_code = preference["point_of_interaction"]["transaction_data"]["qr_code"]
        except:
            # fallback
            pass

        msg = "🚀 Pedido criado! Efetue o pagamento via PIX abaixo:\n\n"
        if qr_code_base64:
            # Enviar como imagem
            import base64
            qr_img_bytes = base64.b64decode(qr_code_base64)
            query.message.reply_photo(photo=qr_img_bytes, caption=msg)
            query.message.reply_text(f"Código PIX:\n`{pix_code}`", parse_mode="Markdown")
        else:
            msg += f"Código PIX:\n`{pix_code}`" if pix_code else "Acesse o link para pagar: " + preference.get("init_point", "")
            query.edit_message_text(msg, parse_mode="Markdown")

        # Salvar pedido para admin e notificações
        order_id = f"{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        orders[order_id] = {
            "user_id": user_id,
            "items": cart,
            "total": sum(i["price"] for i in cart),
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "preference_id": preference.get("id"),
            "payment_method": "pix"
        }
        save_json_db(ORDERS_DB, orders)

        # Notificar admin
        admin_id = os.getenv("ADMIN_ID")
        if admin_id:
            context.bot.send_message(
                chat_id=admin_id,
                text=f"🔔 Novo pedido #{order_id} de {users[user_id]['name']}\nValor: R$ {orders[order_id]['total']:.2f}"
            )

        # Limpar carrinho
        users[user_id]["cart"] = []
        save_json_db(USERS_DB, users)

        return main_menu(update, context)

    elif choice == "cancel_checkout":
        query.edit_message_text("Compra cancelada.")
        return main_menu(update, context)
    else:
        query.answer("Opção inválida.")
        return PAYMENT_METHOD

def admin_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Gerenciar Pedidos", callback_data="admin_orders")],
        [InlineKeyboardButton("Relatórios Financeiros", callback_data="admin_reports")],
        [InlineKeyboardButton("Notificar Entrega", callback_data="admin_notify_delivery")],
        [InlineKeyboardButton("Voltar", callback_data="admin_back")]
    ]
    update.message.reply_text("Menu Administrativo:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_MENU

def admin_menu_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    if data == "admin_orders":
        msg = "Pedidos:\n"
        if not orders:
            msg += "Nenhum pedido encontrado."
        else:
            for oid, o in orders.items():
                user_name = users.get(o["user_id"], {}).get("name", "Desconhecido")
                msg += f"{oid} - {user_name} - R$ {o['total']:.2f} - {o['status']}\n"
        query.edit_message_text(msg)
        return ADMIN_ORDERS

    elif data == "admin_reports":
        # Relatório mensal simples
        month = datetime.now().month
        year = datetime.now().year
        total_sales = 0
        count = 0
        for o in orders.values():
            o_date = datetime.fromisoformat(o["created_at"])
            if o_date.month == month and o_date.year == year and o["status"] == "approved":
                total_sales += o["total"]
                count += 1
        msg = f"Relatório Financeiro {month}/{year}\n\nPedidos aprovados: {count}\nTotal faturado: R$ {total_sales:.2f}"
        query.edit_message_text(msg)
        return ADMIN_REPORTS

    elif data == "admin_notify_delivery":
        msg = "Envie o ID do pedido para notificar o cliente da entrega:"
        query.edit_message_text(msg)
        return ADMIN_NOTIFY_DELIVERY

    elif data == "admin_back":
        query.edit_message_text("Voltando ao menu principal.")
        return main_menu(update, context)
    else:
        query.answer("Opção inválida.")
        return ADMIN_MENU

def admin_notify_delivery(update: Update, context: CallbackContext):
    order_id = update.message.text.strip()
    if order_id not in orders:
        update.message.reply_text("Pedido não encontrado. Tente novamente.")
        return ADMIN_NOTIFY_DELIVERY

    order = orders[order_id]
    user_id = order["user_id"]

    context.bot.send_message(
        chat_id=user_id,
        text=f"Seu pedido {order_id} foi entregue! Obrigado pela preferência."
    )
    update.message.reply_text(f"Cliente {users[user_id]['name']} notificado da entrega.")
    return admin_menu(update, context)

def unknown(update: Update, context: CallbackContext):
    update.message.reply_text("Desculpe, não entendi. Use os botões do menu para navegar.")

def error_handler(update: Update, context: CallbackContext):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            REGISTER_NAME: [MessageHandler(Filters.text & ~Filters.command, register_name)],
            REGISTER_PHONE: [MessageHandler(Filters.text & ~Filters.command, register_phone)],
            SELECT_CATEGORY: [MessageHandler(Filters.regex("^(🛒 Loja|📦 Meu Carrinho|👤 Meu Perfil|⚙️ Menu Administrativo)$"), category_menu)],
            SELECT_PRODUCT: [CallbackQueryHandler(cat_selected, pattern="^cat_")],
            INPUT_MAC: [
                CallbackQueryHandler(product_selected, pattern="^prod_"),
                MessageHandler(Filters.text & ~Filters.command, input_mac)
            ],
            CART_CONFIRM: [CallbackQueryHandler(cart_handler, pattern="^(checkout|clear_cart|back_menu)$")],
            PAYMENT_METHOD: [CallbackQueryHandler(payment_method_handler, pattern="^(pay_pix|cancel_checkout)$")],
            ADMIN_MENU: [CallbackQueryHandler(admin_menu_handler, pattern="^(admin_orders|admin_reports|admin_notify_delivery|admin_back)$")],
            ADMIN_NOTIFY_DELIVERY: [MessageHandler(Filters.text & ~Filters.command, admin_notify_delivery)],
            ADMIN_ORDERS: [MessageHandler(Filters.command | Filters.text, unknown)],
            ADMIN_REPORTS: [MessageHandler(Filters.command | Filters.text, unknown)],
        },
        fallbacks=[CommandHandler("start", start)]
    )

    dp.add_handler(conv_handler)
    dp.add_handler(MessageHandler(Filters.command, unknown))
    dp.add_error_handler(error_handler)

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
