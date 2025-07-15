import os
import re
import logging
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ParseMode
)
from telegram.ext import (
    Updater, CommandHandler, CallbackContext, CallbackQueryHandler,
    MessageHandler, Filters, ConversationHandler
)
import mercadopago
import requests

# --- CONFIGURAÇÃO INICIAL ---

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
MP_ACCESS_TOKEN = os.getenv("MERCADO_PAGO_TOKEN")
if not TOKEN or not MP_ACCESS_TOKEN:
    raise EnvironmentError("Variáveis TELEGRAM_TOKEN e MERCADO_PAGO_TOKEN devem estar definidas.")

# Inicializa SDK Mercado Pago (v2.x)
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# Logging básico
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

ADMIN_IDS = {123456789}  # IDs admins — substitua pelos seus reais

# Estados da conversa
ESPERANDO_MAC = range(1)

# Categorias e produtos
CATEGORIAS = {
    "Eletrônicos": [
        {"nome": "Fone Bluetooth", "preco": 150},
        {"nome": "Carregador Turbo", "preco": 80}
    ],
    "ATIVAR APP": [
        {"nome": "MEGA IPTV", "preco": 75}
    ]
}

# Dados temporários dos usuários (em memória)
user_temp_data = {}

# --- FUNÇÕES AUXILIARES ---

def teclado_persistente():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🛒 Finalizar Compra")], [KeyboardButton("❌ Cancelar")]],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def limpar_mac(raw_mac: str) -> str:
    """Remove tudo que não for hexadecimal para validar MAC."""
    return re.sub(r'[^A-Fa-f0-9]', '', raw_mac.strip())

def criar_preferencia_mercado_pago(user_id: int, carrinho: list):
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
        "payer": {"email": f"user{user_id}@example.com"},
        "back_urls": {
            "success": "https://www.seusite.com/sucesso",
            "failure": "https://www.seusite.com/falha",
            "pending": "https://www.seusite.com/pending"
        },
        "auto_return": "approved",
        "notification_url": "https://seusite.com/webhook"  # se usar webhook futuramente
    }
    try:
        response = sdk.preference().create(preference_data)
        if response['status'] != 201:
            raise Exception(f"Status inválido na criação: {response['status']}")
        return response['response']['init_point'], descricao, total
    except Exception as e:
        logger.error(f"Erro ao criar preferência Mercado Pago: {e}")
        return None, None, None

def verificar_admin(update: Update):
    return update.effective_user.id in ADMIN_IDS

# --- HANDLERS ---

def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_temp_data[user_id] = {"carrinho": []}
    update.message.reply_text(
        "👋 Bem-vindo à loja! Use o menu abaixo para navegar.",
        reply_markup=teclado_persistente()
    )
    mostrar_menu_principal(update, context)

def mostrar_menu_principal(update_or_query, context: CallbackContext):
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat:{cat}")] for cat in CATEGORIAS]
    keyboard.append([InlineKeyboardButton("🛒 Finalizar Compra", callback_data="finalizar")])

    if verificar_admin(update_or_query):
        keyboard.append([InlineKeyboardButton("📊 Admin", callback_data="admin_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if hasattr(update_or_query, 'message') and update_or_query.message:
        update_or_query.message.reply_text("Escolha uma categoria:", reply_markup=reply_markup)
    else:
        try:
            update_or_query.edit_message_text("Escolha uma categoria:", reply_markup=reply_markup)
        except Exception as e:
            logger.warning(f"Erro ao editar mensagem: {e}")

def categoria_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    categoria = query.data.split(":")[1]
    produtos = CATEGORIAS.get(categoria, [])

    keyboard = [
        [InlineKeyboardButton(f"{p['nome']} - R${p['preco']}", callback_data=f"prod:{categoria}:{i}")]
        for i, p in enumerate(produtos)
    ]
    keyboard.append([InlineKeyboardButton("⬅ Voltar", callback_data="voltar")])

    query.answer()
    query.edit_message_text(
        f"Produtos em *{categoria}*:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

def produto_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    _, categoria, index = query.data.split(":")
    index = int(index)
    produtos = CATEGORIAS.get(categoria, [])
    if index >= len(produtos):
        query.answer("Produto inválido.", show_alert=True)
        return ConversationHandler.END

    produto = produtos[index]
    user_id = query.from_user.id

    if user_id not in user_temp_data:
        user_temp_data[user_id] = {"carrinho": []}
    # Remove pendência anterior, se existir
    user_temp_data[user_id].pop("produto_pendente", None)

    if categoria == "ATIVAR APP":
        user_temp_data[user_id]["produto_pendente"] = produto
        query.answer()
        context.bot.send_message(chat_id=user_id, text="Digite o MAC de 12 dígitos (somente letras e números, pode usar ':' ou '-'): ")
        return ESPERANDO_MAC
    else:
        user_temp_data[user_id]["carrinho"].append(produto)
        query.answer()
        context.bot.send_message(chat_id=user_id, text=f"✅ {produto['nome']} adicionado ao carrinho.")
        mostrar_menu_principal(query, context)
        return ConversationHandler.END

def receber_mac(update: Update, context: CallbackContext):
    raw_mac = update.message.text
    mac = limpar_mac(raw_mac)
    user_id = update.message.from_user.id

    if len(mac) != 12:
        update.message.reply_text("❌ MAC inválido. Digite 12 caracteres hexadecimais (0-9, A-F). Tente novamente:")
        return ESPERANDO_MAC

    produto = user_temp_data.get(user_id, {}).get("produto_pendente")
    if not produto:
        update.message.reply_text("❌ Nenhum produto pendente para MAC. Use /start para recomeçar.")
        return ConversationHandler.END

    nome_com_mac = f"{produto['nome']} (MAC: {mac.upper()})"
    user_temp_data[user_id]["carrinho"].append({"nome": nome_com_mac, "preco": produto["preco"]})
    del user_temp_data[user_id]["produto_pendente"]

    update.message.reply_text(f"✅ {nome_com_mac} adicionado ao carrinho.", reply_markup=teclado_persistente())
    mostrar_menu_principal(update, context)
    return ConversationHandler.END

def finalizar_compra_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    carrinho = user_temp_data.get(user_id, {}).get("carrinho", [])

    if not carrinho:
        query.answer("Carrinho vazio!", show_alert=True)
        return

    query.answer()
    link_pagamento, descricao, total = criar_preferencia_mercado_pago(user_id, carrinho)
    if not link_pagamento:
        context.bot.send_message(chat_id=user_id, text="❌ Não foi possível gerar o link de pagamento. Tente novamente mais tarde.")
        return

    resumo_msg = f"🧾 *Resumo do Pedido:*\n{descricao}Total: R${total:.2f}\n\nClique no link abaixo para pagar:"
    context.bot.send_message(chat_id=user_id, text=resumo_msg, parse_mode=ParseMode.MARKDOWN)
    context.bot.send_message(chat_id=user_id, text=link_pagamento)

    # Notifica admins
    for admin_id in ADMIN_IDS:
        try:
            context.bot.send_message(
                chat_id=admin_id,
                text=f"📦 Novo pedido de {update.effective_user.full_name} (ID {user_id})\nTotal: R${total:.2f}"
            )
            context.bot.send_message(
                chat_id=admin_id,
                text=f"Confirmar entrega para {user_id}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Entregue", callback_data=f"entregue:{user_id}")]
                ])
            )
        except Exception as e:
            logger.error(f"Erro notificando admin {admin_id}: {e}")

    # Limpa dados temporários do usuário
    user_temp_data.pop(user_id, None)

def confirmar_entrega(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data.split(":")
    if len(data) != 2:
        query.answer("Formato inválido.", show_alert=True)
        return
    user_id_entrega = int(data[1])
    try:
        context.bot.send_message(chat_id=user_id_entrega, text="📦 Seu pedido foi entregue! Obrigado pela compra. 🙌")
        query.answer("Entrega confirmada.")
        query.edit_message_text("✅ Entrega confirmada para o usuário.")
    except Exception as e:
        logger.error(f"Erro confirmando entrega para {user_id_entrega}: {e}")
        query.answer("Erro ao confirmar entrega.", show_alert=True)

def voltar_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    mostrar_menu_principal(query, context)

def cancelar_handler(update: Update, context: CallbackContext):
    update.message.reply_text("❌ Operação cancelada.", reply_markup=teclado_persistente())
    return ConversationHandler.END

def admin_menu_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    if not verificar_admin(update):
        query.answer("Acesso negado.", show_alert=True)
        return
    query.answer()
    # Implementar funcionalidades futuras do menu admin
    query.edit_message_text("🔧 Menu Admin (em construção)")

# --- MAIN ---

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))

    dp.add_handler(CallbackQueryHandler(categoria_handler, pattern=r"^cat:"))
    dp.add_handler(CallbackQueryHandler(produto_handler, pattern=r"^prod:"))
    dp.add_handler(CallbackQueryHandler(finalizar_compra_handler, pattern=r"^finalizar$"))
    dp.add_handler(CallbackQueryHandler(confirmar_entrega, pattern=r"^entregue:"))
    dp.add_handler(CallbackQueryHandler(voltar_handler, pattern=r"^voltar$"))
    dp.add_handler(CallbackQueryHandler(admin_menu_handler, pattern=r"^admin_menu$"))

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(produto_handler, pattern=r"^prod:")],
        states={
            ESPERANDO_MAC: [MessageHandler(Filters.text & ~Filters.command, receber_mac)]
        },
        fallbacks=[MessageHandler(Filters.regex("^❌ Cancelar$"), cancelar_handler)],
        allow_reentry=True
    )
    dp.add_handler(conv_handler)

    updater.start_polling()
    logger.info("Bot iniciado.")
    updater.idle()

if __name__ == '__main__':
    main()
