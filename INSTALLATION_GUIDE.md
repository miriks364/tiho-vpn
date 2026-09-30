# 📖 Полное руководство установки · Tiho VPN 0.2.0

**Для владельца VPN-сервиса.** Звезды поступают на ВАШ счет.

---

## 🎯 Что вы получите

✅ **Автоматическая система продаж** VPN-доступа через Telegram Stars  
✅ **Один ключ = один телефон** – полный контроль над доступом  
✅ **Web App** для оплаты на вашем сервере (звезды на вашем счёте)  
✅ **Android приложение** с красивым Material Design интерфейсом  
✅ **Полная автоматизация** – платеж → код → активация → VPN включен  

---

## 🚀 Быстрый старт (10-15 минут)

### Шаг 1: Подготовка на VPS

Что вам понадобится:
- **VPS** с Ubuntu 22.04 или 24.04
- **Домен** с DNS на VPS (например, `vpn.example.com`)
- **IP адрес** VPS (публичный IPv4)
- **Telegram бот** (создать через @BotFather)
- **Ваше Telegram ID** (узнать через @userinfobot или @getidsbot)

### Шаг 2: Создание Telegram бота

1. Откройте **@BotFather** в Telegram
2. Отправьте `/newbot`
3. Дайте боту имя: например, **"тихо VPN"**
4. Дайте юзернейм: например, **"tiho_vpn_bot"**
5. 🔑 **Сохраните BOT_TOKEN** – понадобится при установке

Затем включите Stars:
1. Отправьте @BotFather `/mybots` → выберите вашего бота
2. Bot Settings → Payments → Telegram Stars

### Шаг 3: Установка на VPS

Подключитесь к VPS по SSH:

```bash
ssh root@YOUR_VPS_IP
cd /root
```

Скопируйте проект:

```bash
# Если есть архив
unzip Tiho-VPN-0.2.0-full.zip
cd tiho-vpn

# Или клонируйте репозиторий
git clone https://github.com/yourusername/tiho-vpn.git
cd tiho-vpn
```

Запустите установщик:

```bash
sudo env DOMAIN=vpn.example.com PUBLIC_IPV4=203.0.113.10 bash server/install-all.sh
```

**Замените:**
- `vpn.example.com` → ваш домен
- `203.0.113.10` → публичный IP вашего VPS

Установщик спросит вас:

```
BotFather token (hidden): [вставьте ваш BOT_TOKEN]
Your numeric Telegram user ID: [вставьте ваше ID]
API URL: https://vpn.example.com
Web App URL: https://vpn.example.com/web-app
Published purchase/refund terms URL: https://yoursite.com/terms
Published privacy policy URL: https://yoursite.com/privacy
Support contact: @your_support_username
Real seller/operator name: Ваше имя
```

---

## ✅ Проверка установки

После завершения проверьте:

```bash
# Статус сервисов
sudo systemctl status tiho tiho-bot caddy

# API здоров?
curl https://vpn.example.com/health

# Web App доступен?
curl https://vpn.example.com/web-app | head -20

# WireGuard работает?
sudo wg show wg0
```

Должны быть зелёные статусы. Если что-то не так:

```bash
# Посмотрите логи
sudo journalctl -u tiho -n 30
sudo journalctl -u tiho-bot -f  # В реальном времени
sudo journalctl -u caddy -n 30
```

---

## 🧪 Первый тест

### Шаг 1: Откройте вашего бота в Telegram

Найдите бота **@your_bot_username** и:

1. Отправьте `/start`
2. Нажмите кнопку **"💳 Купить / продлить"**
3. **Откроется Web App** с тарифами
4. Выберите тариф (например, 30 дней за 100⭐)
5. Нажмите **"Оплатить"**
6. Подтвердите платёж в Telegram

### Шаг 2: Получите код доступа

После успешного платежа:
- Бот автоматически отправит **код доступа**
- **Срок действия доступа**
- **Ссылку на APK приложения**

### Шаг 3: Активируйте в приложении

1. Установите **тихо VPN** из полученной ссылки
2. Откройте приложение → вкладка **"Настройки"**
3. Введите ваш HTTPS-адрес API: `https://vpn.example.com`
4. Нажмите **"Сохранить API"**
5. Перейдите в **"Подписка"** → **"Активировать код"**
6. Вставьте полученный код
7. На вкладке **"Статус"** нажмите **большую кнопку питания**
8. ✅ VPN должен включиться!

Проверка:
```bash
# Посмотрите активные peers
sudo wg show wg0
# Вы должны увидеть новый peer с вашим телефона
```

---

## 🔧 Управление и администрирование

### Просмотр платежей

```bash
sudo tiho-payments list
```

Вывод:
```
CHARGE_ID                       USER_ID  AMOUNT  DATE
telegram_200...                 12345678 100     2026-09-28 15:30:45
```

### Возврат платежа

```bash
# Показать сумму
sudo tiho-payments refund 'CHARGE_ID_HERE'

# Подтвердить возврат
sudo tiho-payments refund 'CHARGE_ID_HERE' --confirm
```

### Проверка очереди возвратов

```bash
sudo tiho-payments queue
```

### Вывести пользователю код без оплаты (тест)

```bash
sudo tiho-admin issue --user 123456789 --days 30
```

---

## 🛠️ Интеграция с Web App

### Как это работает

```
Пользователь в боте
       ↓
  нажимает "Купить"
       ↓
  [Web App открывается]
       ↓
  выбирает тариф
       ↓
  нажимает "Оплатить" (внутри Telegram)
       ↓
  [Звёзды отправляются ВАМ]
       ↓
  Telegram подтверждает платёж
       ↓
  Ваш API создаёт код доступа
       ↓
  Бот отправляет код пользователю
       ↓
  Пользователь активирует в приложении
```

### Кастомизация Web App

Web App файлы находятся в:
```
/var/www/tiho/web-app/
├─ index.html          # Структура страницы
├─ app.js             # Логика платежей
```

Отредактируйте для вашего стиля:
- Цвета, логотип
- Названия тарифов
- Описания и условия

Перезагрузите Caddy:
```bash
sudo systemctl reload caddy
```

---

## 🚨 Обязательные проверки перед запуском

- ✅ DNS разрешается правильно: `dig vpn.example.com`
- ✅ HTTPS сертификат действителен: `curl https://vpn.example.com/health`
- ✅ Web App открывается в браузере
- ✅ Бот отправляет сообщения (не заблокирован)
- ✅ Полная цепочка: платёж → код → активация → VPN
- ✅ Второй телефон не может активировать тот же код
- ✅ `/device` меняет устройство корректно
- ✅ Возврат уменьшает остаток дней правильно

---

## 🔐 Безопасность

### Обязательно:

1. **Всегда используйте HTTPS** – не публикуйте HTTP версию
2. **Никогда не логируйте BOT_TOKEN** – он сохранён в `/etc/tiho-bot.env` с правами 0600
3. **Резервные копии БД**: `/var/lib/tiho/tiho.db`
4. **Мониторинг логов**: настройте alerts на ошибки API и бота
5. **Firewall**: открыть только 80, 443, 51820 (UDP)

### Рекомендуется:

```bash
# Резервная копия ежедневно
0 3 * * * cp /var/lib/tiho/tiho.db /backup/tiho-$(date +\%Y\%m\%d).db
```

---

## 🐛 Отладка проблем

### Бот не отправляет сообщения

```bash
# Проверьте токен
cat /etc/tiho-bot.env | grep BOT_TOKEN

# Посмотрите логи
sudo journalctl -u tiho-bot -f

# Может быть, вы заблокировали бота? Отправьте ему сообщение:
/start
```

### Web App не открывается

```bash
# Проверьте доступность
curl -I https://vpn.example.com/web-app
# Ответ: HTTP/1.1 200 OK

# Посмотрите ошибки Caddy
sudo journalctl -u caddy -f
```

### Платёж прошёл, но кода не было

```bash
# Проверьте очередь доставки
sudo tiho-payments queue

# Посмотрите, дошла ли уведомление адмнистратору (вам)
sudo journalctl -u tiho-bot | grep "ADMIN"

# Проверьте, есть ли запись о платеже
sudo tiho-payments list | grep `date +%Y-%m-%d`
```

### VPN не подключается с кодом

```bash
# Посмотрите логи API
sudo journalctl -u tiho -f

# Проверьте БД на ошибки
sqlite3 /var/lib/tiho/tiho.db ".schema users"
```

---

## 📚 Структура файлов на VPS

```
/opt/tiho/
├─ api.py              # FastAPI сервер
├─ core.py             # WireGuard управление
├─ bot.py              # Telegram бот (Web App версия)
├─ billing.py          # Платежи и логика
├─ admin.py            # Команды администратора
├─ venv/               # Python виртуальное окружение

/etc/
├─ tiho.env            # Конфиг API (SECRET, DB, WG ключи)
├─ tiho-bot.env        # Конфиг бота (BOT_TOKEN, ADMIN_ID, API_URL)
├─ wireguard/wg0.conf  # WireGuard конфиг
├─ caddy/Caddyfile     # HTTPS reverse proxy

/var/lib/tiho/
└─ tiho.db             # SQLite БД (пользователи, платежи, peers)

/var/www/tiho/
├─ web-app/            # Web App файлы (HTML, JS)
└─ download/tiho.apk   # Android приложение
```

---

## 🎓 Полезные команды

```bash
# Перезагрузка сервисов
sudo systemctl restart tiho tiho-bot caddy

# Статус
sudo systemctl status tiho tiho-bot caddy --no-pager

# Логи в реальном времени
sudo journalctl -u tiho-bot -f

# Проверка WireGuard
sudo wg show wg0
sudo wg set wg0 peer PUBLIC_KEY allowed-ips 10.66.1.0/24

# SQLite БД
sqlite3 /var/lib/tiho/tiho.db
  SELECT * FROM users;
  SELECT * FROM payments;
  SELECT COUNT(*) FROM peers;

# Остановка всего
sudo systemctl stop tiho tiho-bot

# Полная переустановка (осторожно! потеря данных!)
sudo rm -r /opt/tiho /etc/tiho* /var/lib/tiho
# Затем повторите install-all.sh
```

---

## 💰 Монетизация

### Рекомендуемые тарифы

Текущие встроенные:
- **30 дней** — 100⭐ (~3.3⭐/день)
- **90 дней** — 270⭐ (~3⭐/день)
- **365 дней** — 900⭐ (~2.5⭐/день)

Вы можете изменить их, отредактировав:
```
/var/www/tiho/web-app/app.js  →  PLANS array
```

### Конвертация Stars

Telegram Stars нельзя вывести напрямую в деньги.  
Варианты:
1. Используйте Stars для покупки товаров в Telegram
2. Обменяйте на услугу (доп. услуги, консультации)
3. Интегрируйте с payment processor для вывода

---

## 📞 Поддержка

- **Telegram Bot API**: https://core.telegram.org/bots
- **Web Apps**: https://core.telegram.org/bots/webapps
- **WireGuard**: https://www.wireguard.com/quickstart/
- **Caddy**: https://caddyserver.com/docs/

---

## 📝 Чеклист перед продакшеном

- [ ] Домен настроен и доступен по HTTPS
- [ ] Сертификат SSL действителен (Caddy автоматически)
- [ ] Бот создан и токен сохранён безопасно
- [ ] Ваше Telegram ID добавлено в конфиг
- [ ] Web App URL в конфиге указан правильно
- [ ] TERMS_URL и PRIVACY_URL указывают на реальные страницы
- [ ] Поддержку контактную установили
- [ ] Тестовый платёж прошёл успешно
- [ ] Резервная копия БД настроена
- [ ] Мониторинг логов включен
- [ ] Firewall правильно настроен
- [ ] Все сертификаты обновляются автоматически (Caddy)

---

**🎉 Готово! Ваша система автоматических продаж VPN работает.**

Вопросы? Проверьте `/server/BOT-SETUP.md` и логи сервисов.
