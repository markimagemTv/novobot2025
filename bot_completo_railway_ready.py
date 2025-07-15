import os
import logging
import re
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Updater, CommandHandler, CallbackContext, CallbackQueryHandler,
    MessageHandler, Filters, ConversationHandler
)
import mercadopago

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
MP_TOKEN = os.getenv("MERCADO_PAGO_TOKEN")
sdk = mercadopago.SDK(MP_TOKEN)

logging.basicConfig(level=logging.INFO)
ADMIN_IDS = {123456789}  # Seu ID aqui
ESPERANDO_MAC = range(1)
CATEGORIAS = {
    "Eletrônicos": [{"nome": "Fone Bluetooth", "preco": 150}, {"nome": "Carregador Turbo", "preco": 80}],
    "Moda": [{"nome": "Camiseta Estampada", "preco": 60}, {"nome": "Tênis Casual", "preco": 200}],
    "Livros": [{"nome": "Python para Iniciantes", "preco": 90}, {"nome": "Dom Quixote", "preco": 45}],
    "ATIVAR APP": [{"nome": "MEGA IPTV", "preco": 75}]
}
user_temp_data = {}  # {user_id: {"carrinho": [], "produto_pendente": {}, "last_input": ""}}

def teclado_persistente():
    return ReplyKeyboardMarkup([["🛍️ Menu", "🛒 Carrinho"], ["✅ Finalizar", "❌ Cancelar"]], resize_keyboard=True)

def start(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user_temp_data[uid] = {"carrinho": [], "last_input": ""}
    update.message.reply_text("Bem-vindo à loja!", reply_markup=teclado_persistente())
    mostrar_menu_principal(update, context)

def mostrar_menu_principal(update_or_query, context: CallbackContext):
    uid = update_or_query.effective_user.id if hasattr(update_or_query, "effective_user") else update_or_query.from_user.id
    buttons = [[InlineKeyboardButton(cat, callback_data=f"cat:{cat}")] for cat in CATEGORIAS]
    buttons.append([InlineKeyboardButton("📋 Copiar entrada / replay", callback_data="copiar")])
    keyboard = InlineKeyboardMarkup(buttons)
    send_or_edit(update_or_query, "Escolha uma categoria ou ação:", keyboard)

def produto_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    _, cat, idx = query.data.split(":")
    user = query.from_user.id
    prod = CATEGORIAS[cat][int(idx)]
    if cat == "ATIVAR APP":
        user_temp_data[user]["produto_pendente"] = prod
        query.message.reply_text("Digite o MAC de 12 dígitos sem ':'")
        return ESPERANDO_MAC
    else:
        user_temp_data[user]["carrinho"].append(prod)
        query.answer(f"{prod['nome']} adicionado.")
        mostrar_menu_principal(query, context)
        return ConversationHandler.END

def categoria_handler(update: Update, context: CallbackContext):
    cat = update.callback_query.data.split(":")[1]
    produtos = CATEGORIAS[cat]
    keyboard = [[InlineKeyboardButton(f"{p['nome']} - R${p['preco']}", callback_data=f"prod:{cat}:{i}")]
                for i, p in enumerate(produtos)]
    keyboard.append([InlineKeyboardButton("⬅ Voltar", callback_data="voltar")])
    update.callback_query.edit_message_text(f"Produtos: *{cat}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

def receber_mac(update: Update, context: CallbackContext):
    uid = update.message.from_user.id
    mac = update.message.text.strip()
    if not re.fullmatch(r"[A-Fa-f0-9]{12}", mac):
        update.message.reply_text("MAC inválido! Digite novamente.")
        return ESPERANDO_MAC
    prod = user_temp_data[uid].pop("produto_pendente", None)
    nome = f"{prod['nome']} (MAC: {mac})"
    user_temp_data[uid]["carrinho"].append({"nome": nome, "preco": prod["preco"]})
    update.message.reply_text(f"{nome} adicionado ao carrinho.")
    mostrar_menu_principal(update, context)
    return ConversationHandler.END

def ver_carrinho(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    carrinho = user_temp_data[uid]["carrinho"]
    if not carrinho:
        return update.message.reply_text("Carrinho vazio", reply_markup=teclado_persistente())
    txt = "🛒 Carrinho:\n"
    total = 0
    for i, item in enumerate(carrinho, 1):
        nome = item.get("nome", item["nome"])
        preco = item.get("preco", item["preco"])
        txt += f"{i}. {nome} — R${preco:.2f}\n"
        total += preco
    txt += f"\nTotal: R${total:.2f}"
    update.message.reply_text(txt, reply_markup=teclado_persistente())

def finalizar_compra_handler(update: Update, context: CallbackContext):
    if isinstance(update, Update) and update.callback_query:
        query = update.callback_query
        uid = query.from_user.id
        query.answer()
        origin_msg = query.message
    else:
        uid = update.effective_user.id
        origin_msg = update.message

    carrinho = user_temp_data[uid]["carrinho"]
    if not carrinho:
        return origin_msg.reply_text("Carrinho vazio!", reply_markup=teclado_persistente())

    itens = [{"title": it["nome"], "quantity": 1, "currency_id":"BRL", "unit_price": float(it["preco"])}
             for it in carrinho]
    total = sum(it["unit_price"] for it in itens)
    pref = {
        "items": itens,
        "payment_methods": {"excluded_payment_types": [{"id":"credit_card"}], "installments":1},
        "payer":{"email":"comprador@email.com"},
        "back_urls":{"success":"https://seusite.com/sucesso"},
        "auto_return":"approved"
    }
    try:
        resp = sdk.preference().create(pref)
        link = resp["response"]["init_point"]
    except Exception as e:
        logging.error("MercadoPago: %s", e)
        return origin_msg.reply_text("Erro ao gerar pagamento.", reply_markup=teclado_persistente())

    origin_msg.reply_text(f"✅ Pedido por R${total:.2f} gerado.\nPague aqui: {link}")
    origin_msg.reply_text("Após o pagamento, confirme abaixo:", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("Confirmar Entrega", callback_data=f"confirm:{uid}")
    ]]))
    # notifica admin
    for aid in ADMIN_IDS:
        context.bot.send_message(aid, f"Novo pedido de {uid}: R${total:.2f}")
    user_temp_data[uid]["carrinho"] = []

def confirmar_entrega(update: Update, context: CallbackContext):
    query = update.callback_query
    uid = int(query.data.split(":")[1])
    context.bot.send_message(uid, "Seu pedido foi marcado como ENTREGUE. Obrigado!")
    query.edit_message_text("Entrega confirmada ✅")

def copiar_entrada(update: Update, context: CallbackContext):
    query = update.callback_query
    uid = query.from_user.id
    last = user_temp_data.setdefault(uid, {}).get("last_input")
    if not last:
        query.answer("Sem entrada salva.")
    else:
        context.bot.send_message(uid, f"Cópia: `{last}`", parse_mode="Markdown")
    query.answer()

def save_last_input(update: Update, context: CallbackContext):
    if update.message and update.message.text and update.message.text not in ["🛍️ Menu","🛒 Carrinho","✅ Finalizar","❌ Cancelar"]:
        user_temp_data.setdefault(update.message.from_user.id, {})["last_input"] = update.message.text

def send_or_edit(target, text, markup=None):
    if hasattr(target, "message") and target.message:
        target.message.reply_text(text, reply_markup=markup or teclado_persistente())
    elif hasattr(target, "edit_message_text"):
        target.edit_message_text(text, reply_markup=markup)

def main():
    dp = Updater(TOKEN).dispatcher

    conv = ConversationHandler(entry_points=[CallbackQueryHandler(produto_handler, pattern=r"^prod:")],
        states={ESPERANDO_MAC: [MessageHandler(Filters.text & ~Filters.command, receber_mac)]},
        fallbacks=[CommandHandler("❌ Cancelar", lambda u,c: None)], allow_reentry=True
    )

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(conv)
    dp.add_handler(CallbackQueryHandler(categoria_handler, pattern=r"^cat:"))
    dp.add_handler(CallbackQueryHandler(copiar_entrada, pattern="^copiar$"))
    dp.add_handler(CallbackQueryHandler(lambda u,c: mostrar_menu_principal(u, c), pattern="^voltar$"))
    dp.add_handler(CallbackQueryHandler(finalizar_compra_handler, pattern="^finalizar$"))
    dp.add_handler(CallbackQueryHandler(confirmar_entrega, pattern="^confirm:"))
    dp.add_handler(MessageHandler(Filters.regex("^🛍️ Menu"), mostrar_menu_principal))
    dp.add_handler(MessageHandler(Filters.regex("^🛒 Carrinho"), ver_carrinho))
    dp.add_handler(MessageHandler(Filters.regex("^✅ Finalizar"), finalizar_compra_handler))
    dp.add_handler(MessageHandler(Filters.regex("^❌ Cancelar"), lambda u,c: u.message.reply_text("Carrinho limpo.", reply_markup=teclado_persistente())))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, save_last_input))

    Updater(TOKEN).start_polling()
    Updater(TOKEN).idle()

if __name__ == "__main__":
    main()
