import os
import logging
import re
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Updater, CommandHandler, CallbackContext, CallbackQueryHandler,
    MessageHandler, Filters, ConversationHandler
)
import mercadopago

# Configurações iniciais
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
MP_TOKEN = os.getenv("MERCADO_PAGO_TOKEN")
sdk = mercadopago.SDK(MP_TOKEN)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
ADMIN_IDS = {123456789}  # Substitua pelo ID do admin
ESPERANDO_MAC = range(1)

CATEGORIAS = {
    "Eletrônicos": [
        {"nome": "Fone Bluetooth", "preco": 150},
        {"nome": "Carregador Turbo", "preco": 80}
    ],
    "ATIVAR APP": [
        {"nome": "MEGA IPTV", "preco": 75}
    ]
}

user_temp_data = {}  # Armazena carrinhos e dados temporários

def teclado_persistente():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🛒 Finalizar Compra")], [KeyboardButton("❌ Cancelar")]],
        resize_keyboard=True
    )

def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_temp_data[user_id] = {"carrinho": []}
    update.message.reply_text("Bem-vindo à loja!", reply_markup=teclado_persistente())
    mostrar_menu_principal(update, context)

def mostrar_menu_principal(update_or_query, context):
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat:{cat}")] for cat in CATEGORIAS]
    keyboard.append([InlineKeyboardButton("🛒 Finalizar Compra", callback_data="finalizar")])
    if update_or_query.effective_user.id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("📊 Admin", callback_data="admin_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update_or_query.message:
        update_or_query.message.reply_text("Escolha uma categoria:", reply_markup=reply_markup)
    else:
        update_or_query.edit_message_text("Escolha uma categoria:", reply_markup=reply_markup)

def categoria_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    categoria = query.data.split(":")[1]
    produtos = CATEGORIAS[categoria]
    keyboard = [
        [InlineKeyboardButton(f"{p['nome']} - R${p['preco']}", callback_data=f"prod:{categoria}:{i}")]
        for i, p in enumerate(produtos)
    ]
    keyboard.append([InlineKeyboardButton("⬅ Voltar", callback_data="voltar")])
    query.edit_message_text(f"Produtos em *{categoria}*:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

def produto_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    _, categoria, index = query.data.split(":")
    produto = CATEGORIAS[categoria][int(index)]
    user_id = query.from_user.id

    if user_id not in user_temp_data:
        user_temp_data[user_id] = {"carrinho": []}

    if categoria == "ATIVAR APP":
        user_temp_data[user_id]["produto_pendente"] = produto
        context.bot.send_message(chat_id=user_id, text="Digite o MAC de 12 dígitos (somente letras e números):")
        return ESPERANDO_MAC
    else:
        user_temp_data[user_id]["carrinho"].append(produto)
        context.bot.send_message(chat_id=user_id, text=f"✅ {produto['nome']} adicionado ao carrinho.")
        mostrar_menu_principal(query, context)
        return ConversationHandler.END

def receber_mac(update: Update, context: CallbackContext):
    mac = update.message.text.strip()
    user_id = update.message.from_user.id
    if not re.fullmatch(r"[A-Fa-f0-9]{12}", mac):
        update.message.reply_text("❌ MAC inválido. Digite 12 caracteres alfanuméricos.")
        return ESPERANDO_MAC

    produto = user_temp_data[user_id].get("produto_pendente")
    if produto:
        nome_com_mac = f"{produto['nome']} (MAC: {mac})"
        user_temp_data[user_id]["carrinho"].append({"nome": nome_com_mac, "preco": produto["preco"]})
        del user_temp_data[user_id]["produto_pendente"]
        update.message.reply_text(f"✅ {nome_com_mac} adicionado ao carrinho.")
    mostrar_menu_principal(update, context)
    return ConversationHandler.END

def finalizar_compra_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    carrinho = user_temp_data.get(user_id, {}).get("carrinho", [])

    if not carrinho:
        query.answer("Carrinho vazio!", show_alert=True)
        return

    itens = []
    total = 0
    descricao = ""
    for item in carrinho:
        itens.append({
            "title": item["nome"],
            "quantity": 1,
            "currency_id": "BRL",
            "unit_price": float(item["preco"])
        })
        total += item["preco"]
        descricao += f"\u2022 {item['nome']} - R${item['preco']}\n"

    preference_data = {
        "items": itens,
        "payer": {"email": "comprador@email.com"},
        "back_urls": {"success": "https://www.seusite.com/sucesso"},
        "auto_return": "approved"
    }
    preference_response = sdk.preference().create(preference_data)
    link_pagamento = preference_response["response"]["init_point"]

    context.bot.send_message(chat_id=user_id, text=f"🧾 *Resumo do Pedido:*
{descricao}
Total: R${total:.2f}\n\nClique abaixo para pagar:", parse_mode="Markdown")
    context.bot.send_message(chat_id=user_id, text=link_pagamento)

    # Notifica admin
    for admin_id in ADMIN_IDS:
        context.bot.send_message(admin_id, f"📦 Novo pedido de {update.effective_user.full_name} (ID {user_id})\nTotal: R${total:.2f}")
        context.bot.send_message(admin_id, f"Confirmar entrega para {user_id}", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Entregue", callback_data=f"entregue:{user_id}")]
        ]))

    user_temp_data[user_id]["carrinho"] = []

def confirmar_entrega(update: Update, context: CallbackContext):
    user_id = int(update.callback_query.data.split(":")[1])
    context.bot.send_message(chat_id=user_id, text="📦 Seu pedido foi entregue! Obrigado pela compra. 🙌")
    update.callback_query.answer("Entrega confirmada.")

def voltar_handler(update: Update, context: CallbackContext):
    mostrar_menu_principal(update.callback_query, context)

def cancelar_handler(update: Update, context: CallbackContext):
    update.message.reply_text("❌ Operação cancelada.")
    return ConversationHandler.END

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(categoria_handler, pattern=r"^cat:"))
    dp.add_handler(CallbackQueryHandler(produto_handler, pattern=r"^prod:"))
    dp.add_handler(CallbackQueryHandler(finalizar_compra_handler, pattern=r"^finalizar$"))
    dp.add_handler(CallbackQueryHandler(confirmar_entrega, pattern=r"^entregue:"))
    dp.add_handler(CallbackQueryHandler(voltar_handler, pattern=r"^voltar$"))

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(produto_handler, pattern=r"^prod:")],
        states={ESPERANDO_MAC: [MessageHandler(Filters.text & ~Filters.command, receber_mac)]},
        fallbacks=[MessageHandler(Filters.regex("^❌ Cancelar$"), cancelar_handler)],
        allow_reentry=True
    )
    dp.add_handler(conv_handler)

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
