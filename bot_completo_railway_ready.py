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

# IDs dos administradores (modifique para seu(s) ID(s))
ADMIN_IDS = [123456789]

# Estado da conversa
ESPERANDO_MAC = range(1)

# Categorias e produtos
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

# Dados temporários do usuário: carrinho, produto pendente, status MAC etc
user_temp_data = {}  # {user_id: {"carrinho": [], "produto_pendente": {...}, "pedidos": [...]}}

# Lista global de pedidos para administração
user_orders = []  # Cada pedido: {user_id, itens, entregue (bool)}


# -------------------- Funções do Bot --------------------

def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in user_temp_data:
        user_temp_data[user_id] = {"carrinho": []}
    else:
        user_temp_data[user_id]["carrinho"] = []
    mostrar_menu_principal(update.message, context)


def mostrar_menu_principal(update_or_query, context):
    user_id = update_or_query.effective_user.id
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat:{cat}")] for cat in CATEGORIAS]
    keyboard.append([InlineKeyboardButton("🛒 Finalizar Compra", callback_data="finalizar")])
    if user_id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("📊 Admin", callback_data="admin_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if hasattr(update_or_query, "message") and update_or_query.message:
        update_or_query.message.reply_text("Bem-vindo à loja! Escolha uma categoria:", reply_markup=reply_markup)
    else:
        update_or_query.edit_message_text("Escolha uma opção:", reply_markup=reply_markup)


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


def finalizar_compra_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    carrinho = user_temp_data.get(user_id, {}).get("carrinho", [])

    if not carrinho:
        query.answer("Carrinho vazio!", show_alert=True)
        return

    # Registra pedido para admin
    user_orders.append({
        "user_id": user_id,
        "itens": carrinho.copy(),
        "entregue": False
    })

    # Prepara dados para Mercado Pago
    itens_mp = []
    total = 0
    for item in carrinho:
        itens_mp.append({
            "title": item["nome"],
            "quantity": 1,
            "currency_id": "BRL",
            "unit_price": float(item["preco"])
        })
        total += item["preco"]

    preference_data = {
        "items": itens_mp,
        "payment_method_id": "pix",
        "payer": {
            "email": "cliente@email.com"
        }
    }

    payment = sdk.payment().create(preference_data)["response"]
    qr_code = payment["point_of_interaction"]["transaction_data"]["qr_code"]
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?data={qr_code}&size=300x300"

    context.bot.send_photo(
        chat_id=user_id,
        photo=qr_url,
        caption=f"*Compra Finalizada*\nTotal: R${total:.2f}\n\n📎 Código Pix:\n`{qr_code}`",
        parse_mode="Markdown"
    )

    context.bot.send_message(
        chat_id=user_id,
        text="🕐 Aguarde a confirmação do pagamento. Obrigado pela compra!"
    )

    # Limpa carrinho após finalizar
    user_temp_data[user_id]["carrinho"] = []


def voltar_handler(update: Update, context: CallbackContext):
    mostrar_menu_principal(update.callback_query, context)


def cancelar(update: Update, context: CallbackContext):
    update.message.reply_text("❌ Operação cancelada.")
    return ConversationHandler.END


# -------------------- Área ADMIN --------------------

def admin_menu_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in ADMIN_IDS:
        query.answer("Acesso negado.", show_alert=True)
        return

    keyboard = [
        [InlineKeyboardButton("📋 Ver Pedidos", callback_data="admin_pedidos")],
        [InlineKeyboardButton("💰 Relatório Financeiro", callback_data="admin_relatorio")],
        [InlineKeyboardButton("⬅ Voltar", callback_data="voltar")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text("🛠 Painel Administrativo", reply_markup=reply_markup)


def admin_pedidos_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in ADMIN_IDS:
        query.answer("Acesso negado.", show_alert=True)
        return

    if not user_orders:
        query.edit_message_text("Nenhum pedido registrado.")
        return

    texto = ""
    for i, pedido in enumerate(user_orders):
        status = "✅ Entregue" if pedido["entregue"] else "⏳ Pendente"
        texto += f"Pedido {i+1} - {status}\n"
        for item in pedido["itens"]:
            texto += f"• {item['nome']} - R${item['preco']}\n"
        texto += f"/entregar_{i}\n\n"

    texto += "Use os comandos /entregar_N (ex: /entregar_0) para marcar pedido como entregue."
    query.edit_message_text(f"📋 Pedidos Recebidos:\n\n{texto}")


def entregar_pedido(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    if user_id not in ADMIN_IDS:
        update.message.reply_text("Acesso negado.")
        return

    cmd = update.message.text.strip()
    if not cmd.startswith("/entregar_"):
        update.message.reply_text("Comando inválido.")
        return

    try:
        index = int(cmd.split("_")[1])
    except:
        update.message.reply_text("Comando inválido.")
        return

    if index < 0 or index >= len(user_orders):
        update.message.reply_text("Pedido não encontrado.")
        return

    pedido = user_orders[index]
    if pedido["entregue"]:
        update.message.reply_text("Pedido já está marcado como entregue.")
        return

    pedido["entregue"] = True
    update.message.reply_text(f"Pedido {index+1} marcado como entregue.")

    # Opcional: notificar cliente
    context.bot.send_message(
        chat_id=pedido["user_id"],
        text="📦 Seu pedido foi marcado como entregue! Obrigado pela preferência."
    )


def admin_relatorio_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in ADMIN_IDS:
        query.answer("Acesso negado.", show_alert=True)
        return

    total_vendido = 0
    pedidos_totais = len(user_orders)
    pedidos_entregues = sum(1 for p in user_orders if p["entregue"])

    for pedido in user_orders:
        total_vendido += sum(item["preco"] for item in pedido["itens"])

    texto = (
        f"📊 Relatório Financeiro\n\n"
        f"Total de pedidos: {pedidos_totais}\n"
        f"Pedidos entregues: {pedidos_entregues}\n"
        f"Faturamento total: R${total_vendido:.2f}"
    )

    query.edit_message_text(texto)


# -------------------- Main e Handlers --------------------

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
    dp.add_handler(CallbackQueryHandler(admin_menu_handler, pattern=r"^admin_menu$"))
    dp.add_handler(CallbackQueryHandler(admin_pedidos_handler, pattern=r"^admin_pedidos$"))
    dp.add_handler(CallbackQueryHandler(admin_relatorio_handler, pattern=r"^admin_relatorio$"))

    dp.add_handler(MessageHandler(Filters.regex(r"^/entregar_\d+$"), entregar_pedido))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
