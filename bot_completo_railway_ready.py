import os
import logging
import re
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    Updater, CommandHandler, CallbackContext, CallbackQueryHandler,
    MessageHandler, Filters, ConversationHandler
)
import mercadopago

# === Configurações ===
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
MP_TOKEN = os.getenv("MERCADO_PAGO_TOKEN")
sdk = mercadopago.SDK(MP_TOKEN)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

ADMIN_IDS = {123456789}  # Substitua pelo seu ID real
ESPERANDO_MAC = range(1)

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
    ],
    "ATIVAR APP": [
        {"nome": "MEGA IPTV", "preco": 75}
    ]
}

user_temp_data = {}  # {user_id: {"carrinho": [], "produto_pendente": {}}}

# === Teclado Persistente ===
def teclado_persistente():
    return ReplyKeyboardMarkup([
        ["🛍️ Menu", "🛒 Carrinho"],
        ["✅ Finalizar", "❌ Cancelar"]
    ], resize_keyboard=True, one_time_keyboard=False)


# === Início ===
def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_temp_data[user_id] = {"carrinho": []}
    update.message.reply_text(
        "👋 Bem-vindo à loja virtual!",
        reply_markup=teclado_persistente()
    )
    mostrar_menu_principal(update, context)


# === Menus ===
def mostrar_menu_principal(update_or_query, context):
    user_id = (
        update_or_query.effective_user.id
        if hasattr(update_or_query, "effective_user")
        else update_or_query.from_user.id
    )

    keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat:{cat}")] for cat in CATEGORIAS]
    if user_id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("📊 Admin", callback_data="admin_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    send_or_edit(update_or_query, "📦 Escolha uma categoria:", reply_markup)


def mostrar_produtos(update: Update, categoria: str):
    query = update.callback_query
    produtos = CATEGORIAS[categoria]

    keyboard = [
        [InlineKeyboardButton(f"{p['nome']} - R${p['preco']}", callback_data=f"prod:{categoria}:{i}")]
        for i, p in enumerate(produtos)
    ]
    keyboard.append([InlineKeyboardButton("⬅ Voltar", callback_data="voltar")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(f"📚 Produtos em *{categoria}*:", reply_markup=reply_markup, parse_mode='Markdown')


def send_or_edit(target, text, reply_markup=None):
    if hasattr(target, "message") and target.message:
        target.message.reply_text(text, reply_markup=reply_markup or teclado_persistente())
    elif hasattr(target, "edit_message_text"):
        target.edit_message_text(text, reply_markup=reply_markup)
    else:
        target.reply_text(text, reply_markup=reply_markup or teclado_persistente())


# === Handlers ===
def categoria_handler(update: Update, context: CallbackContext):
    categoria = update.callback_query.data.split(":")[1]
    mostrar_produtos(update, categoria)


def produto_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    _, categoria, index = query.data.split(":")
    produto = CATEGORIAS[categoria][int(index)]
    user_id = query.from_user.id

    if categoria == "ATIVAR APP":
        user_temp_data[user_id]["produto_pendente"] = produto
        query.message.reply_text("🔐 Digite o MAC de 12 dígitos (sem `:`):")
        return ESPERANDO_MAC
    else:
        user_temp_data[user_id]["carrinho"].append(produto)
        query.answer(f"{produto['nome']} adicionado ao carrinho!")
        mostrar_menu_principal(query, context)
        return ConversationHandler.END


def receber_mac(update: Update, context: CallbackContext):
    mac = update.message.text.strip()
    user_id = update.message.from_user.id

    if not re.fullmatch(r"[A-Fa-f0-9]{12}", mac):
        update.message.reply_text("❌ MAC inválido! Digite exatamente 12 caracteres alfanuméricos.")
        return ESPERANDO_MAC

    produto = user_temp_data[user_id].pop("produto_pendente", None)
    if not produto:
        update.message.reply_text("⚠️ Nenhum produto aguardando MAC.")
        return ConversationHandler.END

    nome_com_mac = f"{produto['nome']} (MAC: {mac})"
    user_temp_data[user_id]["carrinho"].append({"nome": nome_com_mac, "preco": produto["preco"]})
    update.message.reply_text(f"✅ {nome_com_mac} adicionado ao carrinho.")
    mostrar_menu_principal(update, context)
    return ConversationHandler.END


def ver_carrinho(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    carrinho = user_temp_data.get(user_id, {}).get("carrinho", [])

    if not carrinho:
        update.message.reply_text("🛒 Seu carrinho está vazio.")
        return

    texto = "🛒 *Seu Carrinho:*\n\n"
    total = 0
    for item in carrinho:
        texto += f"- {item['nome']} — R${item['preco']:.2f}\n"
        total += item['preco']
    texto += f"\n💰 *Total:* R${total:.2f}"

    update.message.reply_text(texto, parse_mode="Markdown", reply_markup=teclado_persistente())


def finalizar_compra(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    carrinho = user_temp_data.get(user_id, {}).get("carrinho", [])

    if not carrinho:
        update.message.reply_text("🛒 Carrinho vazio!", reply_markup=teclado_persistente())
        return

    total = 0
    itens = []
    for item in carrinho:
        total += item["preco"]
        itens.append({
            "title": item["nome"],
            "quantity": 1,
            "currency_id": "BRL",
            "unit_price": float(item["preco"])
        })

    preference_data = {
        "items": itens,
        "payment_methods": {
            "excluded_payment_types": [{"id": "credit_card"}],
            "installments": 1
        },
        "payer": {"email": "comprador@email.com"},
        "back_urls": {"success": "https://seusite.com/sucesso"},
        "auto_return": "approved"
    }

    try:
        response = sdk.preference().create(preference_data)
        init_point = response['response']['init_point']
    except Exception as e:
        logging.error(f"Erro Mercado Pago: {e}")
        update.message.reply_text("❌ Erro ao gerar link de pagamento.")
        return

    update.message.reply_text(
        f"✅ *Pedido Gerado!*\n💵 Total: R${total:.2f}\n\n👉 Clique no link para pagar via Pix ou boleto:\n\n{init_point}",
        parse_mode="Markdown"
    )
    update.message.reply_text("🕐 Após o pagamento, aguarde a confirmação.")
    user_temp_data[user_id]["carrinho"] = []


def voltar_handler(update: Update, context: CallbackContext):
    mostrar_menu_principal(update.callback_query, context)


def cancelar(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_temp_data[user_id]["carrinho"] = []
    update.message.reply_text("❌ Carrinho cancelado.", reply_markup=teclado_persistente())


# === Main ===
def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(produto_handler, pattern=r"^prod:")],
        states={ESPERANDO_MAC: [MessageHandler(Filters.text & ~Filters.command, receber_mac)]},
        fallbacks=[CommandHandler("cancelar", cancelar)],
        allow_reentry=True
    )

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(conv_handler)

    dp.add_handler(CallbackQueryHandler(categoria_handler, pattern=r"^cat:"))
    dp.add_handler(CallbackQueryHandler(voltar_handler, pattern=r"^voltar$"))

    dp.add_handler(CallbackQueryHandler(lambda u, c: ver_carrinho(u, c), pattern=r"^ver_carrinho$"))
    dp.add_handler(CallbackQueryHandler(lambda u, c: finalizar_compra(u, c), pattern=r"^finalizar$"))

    # Teclado persistente handlers
    dp.add_handler(MessageHandler(Filters.regex("🛍️ Menu"), mostrar_menu_principal))
    dp.add_handler(MessageHandler(Filters.regex("🛒 Carrinho"), ver_carrinho))
    dp.add_handler(MessageHandler(Filters.regex("✅ Finalizar"), finalizar_compra))
    dp.add_handler(MessageHandler(Filters.regex("❌ Cancelar"), cancelar))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
