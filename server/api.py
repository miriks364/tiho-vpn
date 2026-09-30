import asyncio
import logging
import os
import hmac
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
import core


async def reaper():
    while True:
        await asyncio.sleep(30)
        try:
            await asyncio.to_thread(core.reconcile)
        except Exception:
            # systemd stops wg0 on API failure: do not leave unpaid peers online.
            logging.exception('Peer reconciliation failed; stopping service')
            os._exit(1)


@asynccontextmanager
async def lifespan(app):
    if len(core.SECRET) < 32:
        raise RuntimeError('Missing TIHO_SECRET')
    core.init()
    core.reconcile()
    task = asyncio.create_task(reaper())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title='Tiho VPN', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

# Telegram Web App support
TELEGRAM_BOT_TOKEN = os.environ.get('BOT_TOKEN', '')


class Activation(BaseModel):
    code: str = Field(min_length=20, max_length=100)
    public_key: str = Field(min_length=44, max_length=44)


class InvoiceRequest(BaseModel):
    plan_id: str = Field(min_length=1, max_length=10)
    days: int = Field(ge=1, le=365)
    price: int = Field(ge=1, le=2500)
    currency: str = "XTR"
    user_id: int


def verify_telegram_data(init_data: str) -> dict:
    """Verify Telegram Web App init data"""
    try:
        params = dict(item.split('=') for item in init_data.split('&'))
        hash_value = params.pop('hash')
        
        # Create data check string
        data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(params.items()))
        
        # Compute HMAC
        secret_key = hmac.new(b'WebAppData', TELEGRAM_BOT_TOKEN.encode(), 'sha256').digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), 'sha256').hexdigest()
        
        if computed_hash != hash_value:
            raise ValueError('Invalid signature')
        
        # Parse user data
        if 'user' in params:
            import base64
            user_data = json.loads(base64.b64decode(params['user']))
            return {'user_id': user_data.get('id'), 'username': user_data.get('username')}
        
        return {}
    except Exception as e:
        raise ValueError(f'Invalid Telegram data: {str(e)}')


@app.get('/health')
def health():
    return {'status': 'ok', 'version': '0.2.0'}


@app.post('/v1/public')
def public_info():
    """Get public bot info"""
    bot_url = os.environ.get('BOT_URL', '')
    return {'bot_url': bot_url}


@app.post('/v1/create-invoice')
def create_invoice(request: Request, data: InvoiceRequest):
    """Create Telegram Stars invoice for Web App"""
    try:
        # Verify Telegram data
        telegram_data = request.headers.get('X-Telegram-Init-Data', '')
        user_info = verify_telegram_data(telegram_data)
        
        if not user_info or user_info.get('user_id') != data.user_id:
            raise HTTPException(403, 'Invalid user')
        
        # Validate plan
        if data.plan_id not in ['30', '90', '365']:
            raise HTTPException(400, 'Invalid plan')
        
        prices = {'30': 100, '90': 270, '365': 900}
        if prices.get(data.plan_id) != data.price:
            raise HTTPException(400, 'Invalid price')
        
        # Create invoice URL for Web App
        # In production, this would integrate with Telegram's payment system
        # For now, we return a placeholder that Web App will handle
        invoice_url = f"tg://invoice?currency={data.currency}&total_amount={data.price}&provider_token=&payload={data.user_id}_{data.plan_id}"
        
        return {
            'invoice_url': invoice_url,
            'plan_id': data.plan_id,
            'days': data.days,
            'price': data.price,
            'currency': data.currency
        }
        
    except ValueError as e:
        raise HTTPException(403, str(e))


@app.post('/v1/activate')
def activate(data: Activation, request: Request):
    if not core.rate_limit(request.client.host):
        raise HTTPException(429, 'Try later')
    try:
        return core.activate(data.code, data.public_key)
    except (PermissionError, ValueError):
        raise HTTPException(403, 'Invalid or expired activation')


@app.post('/v1/connect')
def connect(request: Request):
    auth = request.headers.get('authorization', '')
    if not auth.startswith('Bearer ') or len(auth) != 71:
        raise HTTPException(401, 'Invalid session')
    try:
        return core.connect(auth[7:])
    except PermissionError:
        raise HTTPException(403, 'Access expired or revoked')


@app.post('/v1/public')
def public_config():
    import sqlite3
    import re
    try:
        with core.db() as c:
            r = c.execute("SELECT value FROM bot_state WHERE key='bot_username'").fetchone()
        name = r['value'] if r else ''
        return {'bot_url': 'https://t.me/' + name if re.fullmatch(r'[A-Za-z0-9_]{5,32}', name) else ''}
    except sqlite3.OperationalError:
        return {'bot_url': ''}
