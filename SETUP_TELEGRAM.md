# Настройка Telegram для получения Star платежей

**ВАЖНО:** Звезды будут поступать на ВАШ личный аккаунт, а не на аккаунт бота.

## Шаг 1: Создание Web App для платежей

Ваш Web App будет размещен на VPS и управлять оплатой. Stars приходят на ВАШ счёт.

### 1.1 Создайте новый бот через @BotFather

```
/newbot
→ Дайте боту имя, например: "тихо VPN"
→ Дайте боту @username, например: "tiho_vpn_bot"
```

Сохраните `BOT_TOKEN` - это нужно при установке на VPS.

### 1.2 Создайте Web App

Отправьте @BotFather:

```
/myapps
→ Нажмите "Create new Web App"
→ Выберите созданного бота
→ URL Web App: https://YOUR_VPS_DOMAIN/web-app
→ Title: "тихо VPN"
→ Short Name: "tiho_vpn"
```

Сохраните ссылку Web App.

### 1.3 Включите Stars на боте

Отправьте @BotFather:

```
/mybots
→ Выберите вашего бота
→ Bot Settings → Payments
→ Выберите "Telegram Stars"
```

## Шаг 2: Получение вашего Telegram User ID

**Ваше** ID нужно для получения уведомлений о платежах.

1. Найдите бота @userinfobot
2. Отправьте ему любое сообщение
3. Он покажет ваше ID

**Или** используйте @getidsbot

## Шаг 3: Публикация Web App на VPS

### 3.1 Создание HTTPS-подходящего хоста

На VPS убедитесь, что:

```bash
# Проверьте, что домен разрешается
dig YOUR_VPS_DOMAIN

# Проверьте HTTPS сертификат
curl https://YOUR_VPS_DOMAIN/web-app
```

### 3.2 Настройка Web App файлов

Установщик автоматически скопирует Web App файлы в:
```
/var/www/tiho/web-app/
```

### 3.3 Проверка доступности

```bash
curl https://YOUR_VPS_DOMAIN/web-app
# Должен вернуть HTML страницу оплаты
```

## Шаг 4: Настройка Бота на VPS

При запуске `install-all.sh` вас спросят:

```
Введите BOT_TOKEN: YOUR_BOT_TOKEN_HERE
Введите ваш Telegram User ID (для уведомлений): YOUR_USER_ID
Введите публичный URL API (https://vpn.example.com): https://YOUR_VPS_DOMAIN
Введите URL Web App (https://vpn.example.com/web-app): https://YOUR_VPS_DOMAIN/web-app
```

## Шаг 5: Проверка работы

### 5.1 Запуск бота

```bash
sudo systemctl restart tiho-bot
sudo journalctl -u tiho-bot -f
```

### 5.2 Проверка в Telegram

1. Откройте созданного бота
2. Нажмите `/start`
3. Выберите "Купить / продлить"
4. Нажмите на тариф
5. **Откроется Web App** (вместо привычного инвойса!)
6. Выберите тариф
7. Нажмите "Оплатить"
8. Подтвердите платёж

### 5.3 Проверка поступления Stars

```bash
sudo tiho-payments list
```

Должны быть записи о платежах.

## Как это работает внутри

1. **Android приложение** → `/access` в боте
2. **Бот** → Кнопка "Купить в Web App"
3. **Web App** → Выбор тарифа → Оплата Stars
4. **Stars** → Поступают НА ВАШ аккаунт (не на бота!)
5. **API** → Создаёт код доступа
6. **Бот** → Отправляет код пользователю
7. **Android** → Активирует код → Подключается к VPN

## Преимущества Web App подхода

✅ **Звезды на вашем счёте** - вы полный хозяин платежей  
✅ **Ваша коммерция** - полный контроль над ценами и условиями  
✅ **Безопасность** - платежи проходят через Telegram Infrastructure  
✅ **Простота** - не нужны платёжные системы третьих лиц  
✅ **Масштабируемость** - поддержка множества покупателей  

## Ограничения Telegram Stars

- Минимальная сумма платежа: 1⭐
- Максимальная сумма платежа: 2,500⭐
- Звёзды нельзя конвертировать обратно в деньги напрямую
- Вывод: только через Telegram Stars → товары/услуги
- Возвраты: только через команду `/refund` в боте

## Отладка

### Бот не отправляет платёж

```bash
# Проверьте логи бота
sudo journalctl -u tiho-bot -f

# Проверьте конфиг
sudo cat /etc/tiho-bot.env | grep WEB_APP_URL
```

### Web App не открывается

```bash
# Проверьте доступность
curl -I https://YOUR_VPS_DOMAIN/web-app

# Проверьте Caddy логи
sudo journalctl -u caddy -f
```

### Платёж не дошёл

```bash
# Проверьте чёрный список
curl https://YOUR_VPS_DOMAIN/health

# Посмотрите очередь доставки
sudo tiho-payments queue

# Перезагрузите бота
sudo systemctl restart tiho-bot
```

## Контакты поддержки

- **Telegram:** [@BotFather](https://t.me/BotFather) - помощь с ботом
- **Docs:** [Telegram Bot API](https://core.telegram.org/bots)
- **Web App:** [Telegram Web Apps](https://core.telegram.org/bots/webapps)
