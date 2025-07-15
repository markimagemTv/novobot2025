import os
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes
)
import mercadopago
import asyncio

# Variáveis de ambiente
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MERCADO_PAGO_TOKEN = os.getenv("MERCADO_PAGO_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
WEBHOOK_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN")  # ex: https://seubot.up.railway.app

# Inicializa bot e SDK Mercado Pago
sdk = mercadopago.SDK(MERCADO_PAGO_TOKEN)
app = FastAPI()
telegram_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Olá! Eu sou o bot da Oola!\nUse /pagar para gerar um link de pagamento.")

# Comando /pagar
async def pagar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    preference_data = {
        "items": [
            {
                "title": "Produto Oola",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": 10.0
            }
        ]
    }
    preference_response = sdk.preference().create(preference_data)
    link = preference_response["response"]["init_point"]
    await update.message.reply_text(f"💳 Pague aqui: {link}")

# Adiciona handlers
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("pagar", pagar))

# Endpoint do webhook
@app.post(f"/{TELEGRAM_TOKEN}")
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}

# Define o webhook ao iniciar a API
@app.on_event("startup")
async def startup():
    webhook_url = f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}"
    await telegram_app.bot.set_webhook(url=webhook_url)
    print(f"✅ Webhook configurado em: {webhook_url}")
