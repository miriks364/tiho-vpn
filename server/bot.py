"""Telegram Stars bot with Web App support: durable getUpdates inbox and transactional delivery outbox.
Run exactly one bot process. Web App handles payments on YOUR account.
"""
import datetime
import json
import logging
import os
import threading
import time
import httpx
import billing
import core

LOG = logging.getLogger('tiho.bot')
TOKEN = os.environ.get('BOT_TOKEN', '')
API_URL = os.environ.get('PUBLIC_API_URL', '').rstrip('/')
WEB_APP_URL = os.environ.get('WEB_APP_URL', '').rstrip('/')
SUPPORT = os.environ.get('SUPPORT_CONTACT', '')
TERMS = os.environ.get('TERMS_URL', '')
PRIVACY = os.environ.get('PRIVACY_URL', '')
SELLER = os.environ.get('SELLER_NAME', '')
ADMIN = int(os.environ.get('ADMIN_TG_ID', '0'))
TERMS_VERSION = os.environ.get('TERMS_VERSION', '2026-09-v1')


class TelegramError(Exception):
    def __init__(self, code, retry_after=0, description=""):
        self.description = description
        self.code = code
        self.retry_after = retry_after
        super().__init__(f'Telegram API status {code}')


def telegram(method, data, timeout=12):
    try:
        response = httpx.post(f'https://api.telegram.org/bot{TOKEN}/{method}', json=data, timeout=timeout)
        result = response.json()
    except (httpx.HTTPError, ValueError):
        raise TelegramError(0) from None
    if not result.get('ok'):
        raise TelegramError(result.get('error_code', response.status_code), result.get('parameters', {}).get('retry_after', 0), result.get('description', ''))
    return result['result']


def queue(uid, event, text, markup=None):
    with core.db() as c:
        billing.enqueue(c, 'msg:'+event, uid, 'text', {'text': text, 'reply_markup': markup})


def menu(uid, event):
    queue(uid, event, 
          f'🌐 *тихо VPN*\n\n'
          f'Личный VPN на одно устройство. Оплата через Telegram Stars.\n\n'
          f'💰 Цены: 30 дн → 100⭐ · 90 дн → 270⭐ · 365 дн → 900⭐\n'
          f'📌 Без автосписаний. Одна подписка = один телефон.\n\n'
          f'Что дальше?',
          {'inline_keyboard': [
              [{'text': '💳 Купить / продлить', 'callback_data': 'buy'}],
              [{'text': '🔑 Мой доступ', 'callback_data': 'access'}],
              [{'text': '📱 Смена устройства', 'callback_data': 'device'}],
              [{'text': '❓ Условия', 'callback_data': 'terms'}, {'text': '🔒 Данные', 'callback_data': 'privacy'}]
          ]})


def buy(uid, event):
    """Open Web App for payment"""
    if not WEB_APP_URL:
        queue(uid, event, '⚠️ Платежи временно недоступны. Обратитесь к поддержке: '+SUPPORT, None)
        return
    
    queue(uid, event,
          f'💳 *Выберите тариф*\n\n'
          f'┌─ 📅 30 дней\n│  Цена: 100 ⭐\n│  ~3.3⭐/день\n│\n'
          f'├─ 📅 90 дней\n│  Цена: 270 ⭐\n│  ~3⭐/день (популярно)\n│\n'
          f'└─ 📅 365 дней\n   Цена: 900 ⭐\n   ~2.5⭐/день\n\n'
          f'_Оплата через Web App Telegram Stars_\n'
          f'_Один ключ = одно устройство. Без автосписаний._',
          {'inline_keyboard': [[
              {'text': '💳 Перейти к оплате →', 'web_app': {'url': WEB_APP_URL + f'?user={uid}'}}
          ]]}
    )


def access(uid, event):
    """Show current access code and expiry"""
    try:
        with core.db() as c:
            row = c.execute('SELECT token, expires_at FROM users WHERE tg_id = ?', (uid,)).fetchone()
            if not row or not row[0]:
                queue(uid, event,
                      '❌ *Доступ не активирован*\n\n'
                      'Купи тариф через Web App:',
                      {'inline_keyboard': [[
                          {'text': '💳 Купить в Telegram Stars →', 'callback_data': 'buy'}
                      ]]}
                )
                return
            
            token, expires_at = row
            import datetime
            exp_dt = datetime.datetime.fromtimestamp(expires_at)
            exp_str = exp_dt.strftime('%d.%m.%Y %H:%M')
            
            import hmac
            nonce = c.execute('SELECT nonce FROM users WHERE tg_id = ?', (uid,)).fetchone()[0]
            code_bytes = hmac.new(core.SECRET.encode(), f'{uid}:{nonce}'.encode(), 'sha256').digest()
            code = core.b2sh(code_bytes)[:24]
            
            queue(uid, event,
                  f'✅ *Ваш доступ активен*\n\n'
                  f'📍 Код активации:\n'
                  f'`{code}`\n\n'
                  f'⏰ Действителен до:\n'
                  f'`{exp_str}`\n\n'
                  f'📱 *Как активировать:*\n'
                  f'1. Установите тихо VPN из ссылки ниже\n'
                  f'2. Откройте приложение\n'
                  f'3. Вкладка "Настройки" → укажите адрес API\n'
                  f'4. Вкладка "Подписка" → "Активировать код"\n'
                  f'5. Вставьте код выше\n'
                  f'6. Нажмите "Включить VPN"\n\n'
                  f'🔗 *Ссылки:*',
                  {'inline_keyboard': [
                      [{'text': '📥 Скачать APK', 'url': API_URL + '/download/tiho.apk'}],
                      [{'text': '🏠 Назад', 'callback_data': 'menu'}]
                  ]}
            )
    except Exception as e:
        LOG.exception('Access check failed')
        queue(uid, event, '❌ Ошибка: '+str(e)[:100], None)


def device(uid, event):
    """Change device"""
    queue(uid, event,
          '📱 *Смена устройства*\n\n'
          'Сможешь активировать новый телефон. Старый будет отключен.\n'
          'Ограничение: раз в 24 часа.\n'
          'Срок доступа сохранится.\n\n'
          '⚠️ *Внимание:* непосредственно перед сменой:',
          {'inline_keyboard': [[
              {'text': '✅ Сменить устройство', 'callback_data': 'confirm_device'}
          ]]}
    )


def handle_callback(uid, callback_id, data):
    """Handle callback queries from keyboard buttons"""
    if data == 'menu':
        menu(uid, 'menu_click')
    elif data == 'buy':
        buy(uid, 'buy_click')
    elif data == 'access':
        access(uid, 'access_click')
    elif data == 'device':
        device(uid, 'device_click')
    elif data == 'confirm_device':
        try:
            with core.db() as c:
                c.execute('UPDATE users SET last_device_change = ? WHERE tg_id = ?', (int(time.time()), uid))
                c.commit()
            queue(uid, 'device_confirm', 
                  '✅ Устройство сменено!\n\n'
                  'Получите новый код через /access',
                  None)
        except Exception as e:
            queue(uid, 'device_error', '❌ Ошибка: '+str(e)[:100], None)
    elif data == 'terms':
        queue(uid, 'terms_click', f'📋 Условия и возвраты:\n{TERMS}', None)
    elif data == 'privacy':
        queue(uid, 'privacy_click', f'🔒 Политика данных:\n{PRIVACY}', None)
    
    try:
        telegram('answerCallbackQuery', {'callback_query_id': callback_id})
    except TelegramError:
        pass


def handle_message(uid, msg_id, text):
    """Handle text messages"""
    text = text.lower().strip()
    if text in ('/start', 'start', 'меню'):
        menu(uid, 'start')
    elif text in ('/buy', 'купить', 'продлить'):
        buy(uid, 'buy_cmd')
    elif text in ('/access', 'доступ', 'код'):
        access(uid, 'access_cmd')
    elif text in ('/device', 'устройство', 'смена'):
        device(uid, 'device_cmd')
    elif text in ('/terms', 'условия'):
        queue(uid, 'terms_cmd', f'📋 Условия:\n{TERMS}', None)
    elif text in ('/privacy', 'данные', 'политика'):
        queue(uid, 'privacy_cmd', f'🔒 Данные:\n{PRIVACY}', None)
    elif text in ('/paysupport', 'поддержка'):
        queue(uid, 'support_cmd', 
              f'💬 Помощь с оплатой:\n'
              f'{SUPPORT}\n\n'
              f'Ваш ID: `{uid}`',
              None)
    else:
        menu(uid, 'unknown_cmd')


def process_update(update):
    """Process single Telegram update"""
    try:
        if 'message' in update:
            msg = update['message']
            uid = msg['from']['id']
            text = msg.get('text', '')
            if text:
                handle_message(uid, msg['message_id'], text)
        
        elif 'callback_query' in update:
            cq = update['callback_query']
            uid = cq['from']['id']
            callback_id = cq['id']
            data = cq.get('data', '')
            if data:
                handle_callback(uid, callback_id, data)
        
        elif 'pre_checkout_query' in update:
            pq = update['pre_checkout_query']
            telegram('answerPreCheckoutQuery', {'pre_checkout_query_id': pq['id'], 'ok': True})
        
        elif 'successful_payment' in update and 'message' in update:
            msg = update['message']
            uid = msg['from']['id']
            sp = msg['successful_payment']
            
            if sp['currency'] == 'XTR':
                try:
                    with core.db() as c:
                        charge_id = sp['telegram_payment_charge_id']
                        
                        if c.execute('SELECT 1 FROM payments WHERE charge_id = ?', (charge_id,)).fetchone():
                            return
                        
                        amount = sp['total_amount']
                        plan_days = {'100': 30, '270': 90, '900': 365}.get(str(amount), 0)
                        
                        if plan_days > 0:
                            billing.create_payment(c, uid, charge_id, amount, plan_days)
                            c.commit()
                            access(uid, 'payment_success')
                            return
                except Exception as e:
                    LOG.exception('Payment processing failed')
            
            queue(uid, 'payment_error', '❌ Ошибка платежа. Свяжитесь: '+SUPPORT, None)
    
    except Exception as e:
        LOG.exception('Update processing failed')


def poll_updates():
    """Long polling for Telegram updates"""
    offset = 0
    errors = 0
    
    while True:
        try:
            updates = telegram('getUpdates', {'offset': offset, 'timeout': 30, 'allowed_updates': ['message', 'callback_query', 'pre_checkout_query']})
            errors = 0
            
            for update in updates:
                try:
                    process_update(update)
                except Exception as e:
                    LOG.exception(f'Update {update.get("update_id")} failed')
                
                offset = update['update_id'] + 1
        
        except TelegramError as e:
            errors += 1
            wait = min(300, e.retry_after if e.retry_after else 2 ** errors)
            LOG.warning(f'Telegram error {e.code}: waiting {wait}s')
            time.sleep(wait)


def deliver_messages():
    """Send queued outbox messages"""
    while True:
        try:
            with core.db() as c:
                row = c.execute('SELECT id, tg_id, data FROM outbox WHERE sent IS NULL ORDER BY id LIMIT 1').fetchone()
                if not row:
                    time.sleep(1)
                    continue
                
                oid, uid, data_json = row
                try:
                    data = json.loads(data_json)
                    
                    msg_data = {'chat_id': uid, 'parse_mode': 'Markdown', 'text': data['text']}
                    if data.get('reply_markup'):
                        msg_data['reply_markup'] = data['reply_markup']
                    
                    telegram('sendMessage', msg_data)
                    
                    c.execute('UPDATE outbox SET sent = datetime("now") WHERE id = ?', (oid,))
                    c.commit()
                
                except TelegramError as e:
                    if e.code in (401, 403):
                        c.execute('DELETE FROM outbox WHERE id = ?', (oid,))
                        c.commit()
                    else:
                        time.sleep(5)
                
        except Exception:
            LOG.exception('Delivery failed')
            time.sleep(5)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
    
    if not TOKEN or not API_URL or not WEB_APP_URL:
        raise RuntimeError('Missing BOT_TOKEN, PUBLIC_API_URL or WEB_APP_URL')
    
    with core.db() as c:
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                tg_id INTEGER PRIMARY KEY,
                nonce TEXT,
                token TEXT,
                expires_at INTEGER,
                last_device_change INTEGER DEFAULT 0
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                charge_id TEXT PRIMARY KEY,
                tg_id INTEGER,
                amount INTEGER,
                created INTEGER DEFAULT (CAST(strftime('%s', 'now') AS INTEGER))
            )
        ''')
        c.commit()
    
    t1 = threading.Thread(target=poll_updates, daemon=True)
    t1.start()
    
    t2 = threading.Thread(target=deliver_messages, daemon=True)
    t2.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
