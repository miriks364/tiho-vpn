// Telegram Web App initialization
const tg = window.Telegram.WebApp;
tg.ready();

// Configuration
const PLANS = [
    { id: '30', days: 30, price: 100, label: '30 дней', description: 'Базовый тариф' },
    { id: '90', days: 90, price: 270, label: '90 дней', description: 'Самый популярный', badge: 'popular' },
    { id: '365', days: 365, price: 900, label: '365 дней', description: 'Лучшая цена/день' }
];

let selectedPlan = null;
let isLoading = false;

// DOM Elements
const plansContainer = document.getElementById('plans');
const payBtn = document.getElementById('payBtn');
const backBtn = document.getElementById('backBtn');
const statusEl = document.getElementById('status');

// Initialize
function init() {
    renderPlans();
    setupEventListeners();
    
    // Set Telegram appearance
    tg.setHeaderColor('#0d1117');
    tg.setBackgroundColor('#0d1117');
    tg.expand();
}

// Render plans
function renderPlans() {
    plansContainer.innerHTML = PLANS.map(plan => `
        <div class="plan" data-id="${plan.id}">
            <div class="plan-header">
                <div>
                    <div class="plan-name">${plan.label}</div>
                    <div class="plan-description">${plan.description}</div>
                    ${plan.badge ? `<div class="plan-badge ${plan.badge}">Популярно</div>` : ''}
                </div>
                <div class="plan-price">${plan.price} ⭐</div>
            </div>
        </div>
    `).join('');
    
    // Add click handlers
    document.querySelectorAll('.plan').forEach(el => {
        el.addEventListener('click', () => selectPlan(el.dataset.id));
    });
}

// Select plan
function selectPlan(planId) {
    document.querySelectorAll('.plan').forEach(el => el.classList.remove('selected'));
    document.querySelector(`[data-id="${planId}"]`).classList.add('selected');
    selectedPlan = PLANS.find(p => p.id === planId);
    payBtn.disabled = false;
    payBtn.textContent = `Оплатить ${selectedPlan.price} ⭐`;
}

// Setup event listeners
function setupEventListeners() {
    payBtn.addEventListener('click', handlePayment);
    backBtn.addEventListener('click', () => tg.close());
}

// Handle payment
async function handlePayment() {
    if (!selectedPlan || isLoading) return;
    
    isLoading = true;
    payBtn.classList.add('button-loading');
    payBtn.disabled = true;
    
    try {
        // Get user data from Telegram
        const userId = tg.initDataUnsafe?.user?.id;
        if (!userId) {
            showStatus('Ошибка: не удалось получить данные пользователя', 'error');
            return;
        }
        
        // Get API URL from query params or localStorage
        const urlParams = new URLSearchParams(window.location.search);
        const apiUrl = urlParams.get('api') || localStorage.getItem('tiho_api_url');
        
        if (!apiUrl) {
            showStatus('Ошибка: не указан адрес API', 'error');
            return;
        }
        
        showStatus('Обработка платежа...', 'loading');
        
        // Create invoice
        const response = await fetch(`${apiUrl}/v1/create-invoice`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Telegram-Init-Data': tg.initData
            },
            body: JSON.stringify({
                plan_id: selectedPlan.id,
                days: selectedPlan.days,
                price: selectedPlan.price,
                currency: 'XTR',
                user_id: userId
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Ошибка сервера');
        }
        
        const data = await response.json();
        const invoiceLink = data.invoice_url;
        
        // Open invoice in Telegram
        showStatus('Открываем платёж...', 'loading');
        
        // Handle payment result
        window.addEventListener('beforeunload', async () => {
            // Payment completed
            showStatus('✅ Спасибо! Код доступа отправлен в бот', 'success');
            setTimeout(() => tg.close(), 2000);
        });
        
        // Open URL in Telegram context
        if (invoiceLink) {
            tg.openInvoice(invoiceLink, (status) => {
                if (status === 'paid') {
                    showStatus('✅ Платёж принят! Проверь сообщения в боте', 'success');
                    setTimeout(() => tg.close(), 3000);
                } else if (status === 'cancelled') {
                    showStatus('❌ Платёж отменён', 'error');
                    isLoading = false;
                    payBtn.classList.remove('button-loading');
                    payBtn.disabled = false;
                } else if (status === 'failed') {
                    showStatus('❌ Платёж не прошёл. Попробуй ещё раз', 'error');
                    isLoading = false;
                    payBtn.classList.remove('button-loading');
                    payBtn.disabled = false;
                }
            });
        }
        
    } catch (error) {
        console.error('Payment error:', error);
        showStatus(`❌ ${error.message}`, 'error');
        isLoading = false;
        payBtn.classList.remove('button-loading');
        payBtn.disabled = false;
    }
}

// Show status message
function showStatus(message, type) {
    statusEl.className = `status show ${type}`;
    let icon = '⏳';
    if (type === 'success') icon = '✅';
    if (type === 'error') icon = '❌';
    
    statusEl.innerHTML = `
        <div style="display: flex; align-items: center; gap: 8px;">
            <span class="status-icon">${icon}</span>
            <span class="status-text">${message}</span>
        </div>
    `;
}

// Initialize when ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

// Keep Web App alive
setInterval(() => {
    tg.sendData('ping');
}, 60000);
