import os
import logging
import re
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackContext, CallbackQueryHandler,
    MessageHandler, Filters, ConversationHandler
)
import mercadopago

# Carrega variáveis de ambiente
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
MP_TOKEN = os.getenv("MERCADO_PAGO_TOKEN")

# Configura Mercado Pago
sdk = mercadopago.SDK(MP_TOKEN)

# Logger
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Estado da conversa
ESPERANDO_MAC = range(1)

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
    ],
    "ATIVAR APP": [
        {"nome": "MEGA IPTV", "preco": 75}
    ]
}

# Armazenamento por usuário
user_temp_data = {}  # {user_id: {"carrinho": [...], "produto_pendente": {...}}}

# /start
def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_temp_data[user_id] = {"carrinho": []}  # limpa carrinho
    mostrar_menu_principal(update, context)

def mostrar_menu_principal(update_or_query, context):
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat:{cat}")] for cat in CATEGORIAS]
    keyboard.append([InlineKeyboardButton("🛒 Finalizar Compra", callback_data="finalizar")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update_or_query.message:
        update_or_query.message.reply_text("Bem-vindo à loja! Escolha uma categoria:", reply_markup=reply_markup)
    else:
        update_or_query.edit_message_text("Escolha uma categoria:", reply_markup=reply_markup)

# Categoria handler
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

# Produto handler
def produto_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    _, categoria, index = query.data.split(":")
    produto = CATEGORIAS[categoria][int(index)]
    user_id = query.from_user.id

    if user_id not in user_temp_data:
        user_temp_data[user_id] = {"carrinho": []}

    if categoria == "ATIVAR APP":
        user_temp_data[user_id]["produto_pendente"] = produto
        query.message.reply_text("Digite o MAC de 12 dígitos (apenas letras e números, sem `:`):")
        return ESPERANDO_MAC
    else:
        user_temp_data[user_id]["carrinho"].append({"nome": produto["nome"], "preco": produto["preco"]})
        query.message.reply_text(f"✅ {produto['nome']} adicionado ao carrinho.")
        mostrar_menu_principal(query, context)
        return ConversationHandler.END

# Receber MAC e adicionar ao carrinho
def receber_mac(update: Update, context: CallbackContext):
    mac = update.message.text.strip()
    user_id = update.message.from_user.id

    if not re.fullmatch(r"[A-Fa-f0-9]{12}", mac):
        update.message.reply_text("❌ MAC inválido! Digite exatamente 12 caracteres alfanuméricos (sem dois pontos).")
        return ESPERANDO_MAC

    produto = user_temp_data[user_id].get("produto_pendente")
    if not produto:
        update.message.reply_text("❌ Erro: nenhum produto aguardando MAC.")
        return ConversationHandler.END

    nome_formatado = f"{produto['nome']} (MAC: {mac})"
    user_temp_data[user_id]["carrinho"].append({"nome": nome_formatado, "preco": produto["preco"]})
    del user_temp_data[user_id]["produto_pendente"]

    update.message.reply_text(f"✅ {nome_formatado} adicionado ao carrinho.")
    mostrar_menu_principal(update, context)
    return ConversationHandler.END

# Finalizar compra com pagamento único Pix
def finalizar_compra_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    carrinho = user_temp_data.get(user_id, {}).get("carrinho", [])

    if not carrinho:
        query.answer("Carrinho vazio!", show_alert=True)
        return

    # Soma total e monta descrição
    total = sum(item["preco"] for item in carrinho)
    descricao = " | ".join(item["nome"] for item in carrinho)
    if len(descricao) > 250:  # Mercado Pago limite de descrição
        descricao = descricao[:247] + "..."

    # Cria pagamento Pix direto
    payment_data = {
        "transaction_amount": float(total),
        "description": descricao,
        "payment_method_id": "pix",
        "payer": {
            "email": "comprador@email.com"
        }
    }

    payment_response = sdk.payment().create(payment_data)
    payment = payment_response["response"]

    qr_code = payment["point_of_interaction"]["transaction_data"]["qr_code"]
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?data={qr_code}&size=300x300"

    context.bot.send_photo(
        chat_id=user_id,
        photo=qr_url,
        caption=f"*Compra Finalizada*\nTotal: R${total:.2f}\n\n📎 Copie e cole o código Pix abaixo:\n`{qr_code}`",
        parse_mode="Markdown"
    )

    context.bot.send_message(
        chat_id=user_id,
        text="🕐 Aguarde a confirmação do pagamento. Obrigado pela compra!"
    )

    # Limpa carrinho após gerar pagamento
    user_temp_data[user_id]["carrinho"] = []

# Voltar
def voltar_handler(update: Update, context: CallbackContext):
    mostrar_menu_principal(update.callback_query, context)

def cancelar(update: Update, context: CallbackContext):
    update.message.reply_text("❌ Operação cancelada.")
    return ConversationHandler.END

# Main
def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(produto_handler, pattern=r"^prod:")],
        states={
            ESPERANDO_MAC: [MessageHandler(Filters.text & ~Filters.command, receber_mac)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        allow_reentry=True
    )

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(conv_handler)
    dp.add_handler(CallbackQueryHandler(categoria_handler, pattern=r"^cat:"))
    dp.add_handler(CallbackQueryHandler(voltar_handler, pattern=r"^voltar$"))
    dp.add_handler(CallbackQueryHandler(finalizar_compra_handler, pattern=r"^finalizar$"))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
