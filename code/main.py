import telebot
import sqlite3
import random
from telebot import types

TOKEN = '7441081537:AAEWxaWYEIQ_arpvbxYfODAJeVdWRhg2l5g'
bot = telebot.TeleBot(TOKEN)

# Подключение к базе данных
conn = sqlite3.connect('math_bot.db', check_same_thread=False)
cursor = conn.cursor()

# Создание таблицы пользователей
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    difficulty TEXT,
    correct_answers INTEGER DEFAULT 0,
    score INTEGER DEFAULT 0,
    current_question TEXT,
    correct_answer INTEGER
)
''')
conn.commit()

# Уровни сложности и баллы
DIFFICULTIES = {
    'easy': {'range': (1, 10), 'operations': ['+', '-'], 'points': 10},
    'medium': {'range': (2, 15), 'operations': ['*'], 'points': 20},
    'hard': {'range': (10, 30), 'operations': ['+-*'], 'points': 30}
}

# Генерация вопросов
def generate_question(difficulty):
    config = DIFFICULTIES[difficulty]
    if difficulty == 'easy':
        a = random.randint(*config['range'])
        b = random.randint(*config['range'])
        op = random.choice(config['operations'])
        question = f"{a} {op} {b}"
        answer = eval(question)
        return question, answer
    
    elif difficulty == 'medium':
        a = random.randint(*config['range'])
        b = random.randint(*config['range'])
        question = f"{a} * {b}"
        return question, a * b
    
    elif difficulty == 'hard':
        a = random.randint(10, 30)
        b = random.randint(10, 30)
        c = random.randint(2, 10)
        op = random.choice(['+', '-'])
        question = f"({a} {op} {b}) * {c}"
        answer = eval(question)
        return question, answer

# Клавиатура с кнопкой остановки
def get_stop_keyboard():
    markup = types.InlineKeyboardMarkup()
    stop_btn = types.InlineKeyboardButton("⏹ Остановить игру", callback_data='stop_game')
    markup.add(stop_btn)
    return markup

# Обработчик старта
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)', (user_id, username))
    conn.commit()
    
    bot.reply_to(message, "Привет! Я бот для тренировки устного счета.\n"
                 "Используй /startgame чтобы начать игру\n"
                 "/leaderboard - таблица лидеров\n"
                 "/stop - остановить текущую игру")


# Обработчик запуска игры
@bot.message_handler(commands=['startgame'])
def start_game(message):
    markup = types.InlineKeyboardMarkup()
    for diff in DIFFICULTIES:
        btn = types.InlineKeyboardButton(
            text=diff.capitalize(),
            callback_data=f'setdiff_{diff}'
        )
        markup.add(btn)
    
    bot.send_message(message.chat.id, "Выбери уровень сложности:", reply_markup=markup)

@bot.message_handler(commands=['stop'])
def stop_game_command(message):
    user_id = message.from_user.id
    cursor.execute('''
        UPDATE users 
        SET current_question = NULL,
            correct_answer = NULL 
        WHERE user_id = ?
    ''', (user_id,))
    conn.commit()
    
    cursor.execute('SELECT score FROM users WHERE user_id = ?', (user_id,))
    score = cursor.fetchone()[0]
    
    bot.reply_to(message, f"🛑 Игра остановлена. Твой счет: {score} баллов")

# Обработчик выбора сложности
@bot.callback_query_handler(func=lambda call: call.data.startswith('setdiff_'))
def set_difficulty(call):
    user_id = call.from_user.id
    difficulty = call.data.split('_')[1]
    
    cursor.execute('UPDATE users SET difficulty = ? WHERE user_id = ?', (difficulty, user_id))
    conn.commit()
    
    question, answer = generate_question(difficulty)
    cursor.execute('UPDATE users SET current_question = ?, correct_answer = ? WHERE user_id = ?',
                  (question, answer, user_id))
    conn.commit()
    
    bot.send_message(call.message.chat.id, 
                    f"Реши пример: {question}",
                    reply_markup=get_stop_keyboard())

# Обработчик остановки игры
@bot.callback_query_handler(func=lambda call: call.data == 'stop_game')
def stop_game(call):
    user_id = call.from_user.id
    cursor.execute('''
        UPDATE users 
        SET current_question = NULL,
            correct_answer = NULL 
        WHERE user_id = ?
    ''', (user_id,))
    conn.commit()
    
    cursor.execute('SELECT score FROM users WHERE user_id = ?', (user_id,))
    score = cursor.fetchone()[0]
    
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, f"🛑 Игра остановлена. Твой счет: {score} баллов")

# Таблица лидеров
@bot.message_handler(commands=['leaderboard'])
def show_leaderboard(message):
    cursor.execute('''
        SELECT username, score 
        FROM users 
        WHERE score > 0 
        ORDER BY score DESC 
        LIMIT 10
    ''')
    leaders = cursor.fetchall()
    
    response = "🏆 Топ игроков:\n" if leaders else "Таблица лидеров пуста!"
    for i, (username, score) in enumerate(leaders, 1):
        response += f"{i}. {username if username else 'Anonymous'} - {score} баллов\n"
    
    bot.reply_to(message, response)

# Обработчик ответов
@bot.message_handler(func=lambda m: True)
def check_answer(message):
    user_id = message.from_user.id
    try:
        user_answer = int(message.text)
    except ValueError:
        bot.reply_to(message, "Пожалуйста, введи число!")
        return

    cursor.execute('SELECT correct_answer, difficulty, score FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if not result or result[0] is None:
        bot.reply_to(message, "Сначала начни игру через /startgame")
        return
    
    correct_answer, difficulty, score = result
    points = DIFFICULTIES[difficulty]['points']
    
    if user_answer == correct_answer:
        new_score = score + points
        cursor.execute('''
            UPDATE users 
            SET score = ?, 
                correct_answers = correct_answers + 1,
                current_question = NULL,
                correct_answer = NULL
            WHERE user_id = ?
        ''', (new_score, user_id))
        conn.commit()
        
        question, answer = generate_question(difficulty)
        cursor.execute('UPDATE users SET current_question = ?, correct_answer = ? WHERE user_id = ?',
                      (question, answer, user_id))
        conn.commit()
        
        bot.send_message(message.chat.id,
                        f"✅ Правильно! +{points} баллов\nСледующий вопрос: {question}",
                        reply_markup=get_stop_keyboard())
    else:
        bot.reply_to(message, f"❌ Неправильно. Попробуй ещё раз!")


if __name__ == '__main__':
    bot.polling(none_stop=True)