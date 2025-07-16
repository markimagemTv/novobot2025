# bot_vendas.py

import os
import json
import logging
import uuid
from datetime import datetime
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters,
                          CallbackQueryHandler, CallbackContext, ConversationHandler)
import mercadopago

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tokens e Config
TOKEN = os.getenv("TELEGRAM_TOKEN")
MP_TOKEN = os.getenv("MERCADO_PAGO_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

mp = mercadopago.SDK(MP_TOKEN)

# Estados para conversas
NOME, TELEFONE, COLETA_DADOS = range(3)

# Simples armazenamento em JSON
USERS_FILE = "users.json"
ORDERS_FILE = "orders.json"
CARTS = {}

# Catálogo fixo
CATALOGO = {
    "ATIVAR APP": [
        {"name": "Mega IPTV", "price": 75.0, "fields": ["MAC"]}
    ],
    "COMPRAR CRÉDITOS": [
        {"name": "Painel Fast Play", "price": 135.0, "credits": 10}
    ]
}

def carregar_json(caminho):
    if os.path.exists(caminho):
        with open(caminho, 'r') as f:
            return json.load(f)
    return {}

def salvar_json(caminho, dados):
    with open(caminho, 'w') as f:
        json.dump(dados, f, indent=2)

USERS = carregar_json(USERS_FILE)
ORDERS = carregar_json(ORDERS_FILE)

# Comandos e handlers

def start(update: Update, context: CallbackContext):
    update.message.reply_text("Bem-vindo! Por favor, envie seu nome completo:")
    return NOME

def receber_nome(update: Update, context: CallbackContext):
    context.user_data['nome'] = update.message.text
    update.message.reply_text("Agora envie seu telefone:")
    return TELEFONE

def receber_telefone(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    USERS[str(user_id)] = {
        "nome": context.user_data['nome'],
        "telefone": update.message.text
    }
    salvar_json(USERS_FILE, USERS)
    update.message.reply_text("Cadastro completo! Use /produtos para ver os produtos.")
    return ConversationHandler.END

def produtos(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton(cat, callback_data=f"categoria_{cat}")]
        for cat in CATALOGO.keys()
    ]
    update.message.reply_text("Escolha uma categoria:", reply_markup=InlineKeyboardMarkup(keyboard))

def categoria_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    categoria = query.data.split("_", 1)[1]
    produtos = CATALOGO[categoria]
    keyboard = []
    for i, p in enumerate(produtos):
        keyboard.append([InlineKeyboardButton(f"{p['name']} - R${p['price']:.2f}", callback_data=f"produto_{categoria}_{i}")])
    query.edit_message_text(f"Produtos em {categoria}:", reply_markup=InlineKeyboardMarkup(keyboard))

def produto_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    _, categoria, idx = query.data.split("_")
    produto = CATALOGO[categoria][int(idx)]
    context.user_data['produto'] = produto
    context.user_data['categoria'] = categoria
    context.user_data['dados_produto'] = {}
    field = produto.get("fields", [""])[0]
    query.edit_message_text(f"Informe {field}:")
    return COLETA_DADOS

def coletar_dado_produto(update: Update, context: CallbackContext):
    valor = update.message.text.replace(":", "").strip()
    user_id = str(update.effective_user.id)
    produto = context.user_data['produto']
    context.user_data['dados_produto'][produto['fields'][0]] = valor
    item = {
        "name": produto['name'],
        "price": produto['price'],
        "fields": context.user_data['dados_produto']
    }
    CARTS.setdefault(user_id, []).append(item)
    update.message.reply_text("Produto adicionado ao carrinho. Use /carrinho para finalizar.")
    return ConversationHandler.END

def carrinho(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    carrinho = CARTS.get(user_id, [])
    if not carrinho:
        update.message.reply_text("Seu carrinho está vazio.")
        return
    total = sum(i['price'] for i in carrinho)
    txt = "\n".join([f"{i['name']} - R${i['price']} ({json.dumps(i.get('fields', {}))})" for i in carrinho])
    txt += f"\nTotal: R${total:.2f}"
    keyboard = [[InlineKeyboardButton("Pagar com PIX", callback_data="pagar_pix")]]
    update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(keyboard))

def pagar_pix(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = str(query.from_user.id)
    carrinho = CARTS.get(user_id, [])
    total = sum(i['price'] for i in carrinho)
    order_id = str(uuid.uuid4())[:8]
    order = {
        "id": order_id,
        "user": USERS.get(user_id, {}),
        "items": carrinho,
        "status": "pendente",
        "created_at": datetime.now().isoformat()
    }
    ORDERS[order_id] = order
    salvar_json(ORDERS_FILE, ORDERS)
    CARTS[user_id] = []
    payment = mp.payment().create({
        "transaction_amount": float(total),
        "description": f"Pedido #{order_id}",
        "payment_method_id": "pix",
        "payer": {"email": f"{user_id}@exemplo.com"}
    })['response']
    pix = payment['point_of_interaction']['transaction_data']['qr_code']
    context.bot.send_message(user_id, f"Use o código PIX:\n`{pix}`", parse_mode='Markdown')
    if ADMIN_ID:
        context.bot.send_message(ADMIN_ID, f"📦 Novo Pedido #{order_id}\nCliente: {order['user']}\nItens: {len(carrinho)}\nTotal: R${total:.2f}")

def admin_entregar(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args
    if not args:
        update.message.reply_text("Uso: /entregar <id_do_pedido>")
        return
    order_id = args[0]
    order = ORDERS.get(order_id)
    if not order:
        update.message.reply_text("Pedido não encontrado")
        return
    order['status'] = 'entregue'
    salvar_json(ORDERS_FILE, ORDERS)
    uid = next(k for k, v in USERS.items() if v == order['user'])
    context.bot.send_message(uid, f"✅ Seu pedido #{order_id} foi entregue!")
    update.message.reply_text("Cliente notificado.")

def admin_relatorio(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return
    total = sum(sum(i['price'] for i in o['items']) for o in ORDERS.values() if o['status'] == 'entregue')
    update.message.reply_text(f"💰 Total de vendas entregues: R${total:.2f}")

def main():
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NOME: [MessageHandler(Filters.text & ~Filters.command, receber_nome)],
            TELEFONE: [MessageHandler(Filters.text & ~Filters.command, receber_telefone)],
            COLETA_DADOS: [MessageHandler(Filters.text & ~Filters.command, coletar_dado_produto)]
        },
        fallbacks=[]
    )

    dp.add_handler(conv_handler)
    dp.add_handler(CommandHandler("produtos", produtos))
    dp.add_handler(CommandHandler("carrinho", carrinho))
    dp.add_handler(CommandHandler("entregar", admin_entregar))
    dp.add_handler(CommandHandler("relatorio", admin_relatorio))
    dp.add_handler(CallbackQueryHandler(categoria_callback, pattern="^categoria_"))
    dp.add_handler(CallbackQueryHandler(produto_callback, pattern="^produto_"))
    dp.add_handler(CallbackQueryHandler(pagar_pix, pattern="^pagar_pix$"))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
