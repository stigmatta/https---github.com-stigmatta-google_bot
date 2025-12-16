import json
import urllib.request
import urllib.parse
import boto3 

TELEGRAM_TOKEN = "8462530999:AAGYpgPTFW9AnbOa1AcHtYI46O4Fqi3ERq0"
CHAT_ID = "2047506345"

S3_BUCKET_NAME = 's3-odintsov-3c2'
rekognition_client = boto3.client('rekognition')

def send_telegram(chat_id, message, parse_mode=None):
    """Надсилає повідомлення користувачу."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    params = {
        "chat_id": chat_id,
        "text": message
    }
    
    if parse_mode:
        params["parse_mode"] = parse_mode
        
    data = urllib.parse.urlencode(params).encode("utf-8") 

    try:
        urllib.request.urlopen(url, data, timeout=5)
    except Exception as e:
        print(f"Ошибка Telegram: {e}")

def get_file_url(file_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
    response = urllib.request.urlopen(url)
    data = json.loads(response.read())
    if data['ok']:
        file_path = data['result']['file_path']
        return f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    return None

def handle_photo(chat_id, photo_array):
    """Handles an incoming photo: OCR + product search (no brands, no stop-words)."""

    # 1. Pick the largest available photo
    largest_photo = photo_array[-1]
    file_id = largest_photo['file_id']

    send_telegram(chat_id, "🔍 Photo received. Starting recognition...")

    # 2. Get Telegram file URL
    file_url = get_file_url(file_id)
    if not file_url:
        send_telegram(chat_id, "❗️Failed to get file URL.")
        return

    search_query = "product"
    s3_key = f"telegram_images/{file_id}.jpg"

    try:
        # 3. Download image and upload to S3
        image_data = urllib.request.urlopen(file_url).read()
        s3 = boto3.client("s3")
        s3.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            Body=image_data,
            ContentType="image/jpeg"
        )

        # 4. Detect text using AWS Rekognition
        text_response = rekognition_client.detect_text(
            Image={"S3Object": {"Bucket": S3_BUCKET_NAME, "Name": s3_key}}
        )

        # 5. Collect high-confidence words
        detected_words = [
            t["DetectedText"]
            for t in text_response["TextDetections"]
            if t["Type"] == "WORD"
            and t["Confidence"] > 85
            and t["DetectedText"].isalpha()
        ]

        # 6. Build search query (NO brands, NO stop-words)
        if detected_words:
            # longest word is usually the product/brand name
            search_query = max(detected_words, key=len)
        else:
            search_query = "product"

        # Notify user
        send_telegram(
            chat_id,
            f"✅ Recognized as: *{search_query}*\nSearching for offers...",
            parse_mode="Markdown"
        )

    except Exception as e:
        error_msg = f"❗️Recognition error: {e}"
        print(error_msg)
        send_telegram(chat_id, error_msg)
        return

    # 7. Generate Google Shopping link (safe fallback)
    try:
        encoded_query = urllib.parse.quote(f"{search_query} buy price")
        google_shopping_link = (
            f"https://www.google.com/search?q={encoded_query}&tbm=shop"
        )

        result_message = (
            f"🛍️ *Found offers for {search_query}:*\n\n"
            f"🔗 [View on Google Shopping]({google_shopping_link})"
        )

        send_telegram(chat_id, result_message, parse_mode="Markdown")

    except Exception as e:
        error_msg = f"❗️Search error: {e}"
        print(error_msg)
        send_telegram(chat_id, error_msg)
    """Обробляє отримане фото: розпізнає та шукає пропозиції."""
    
    # 1. Вибираємо найбільшу доступну версію фото
    largest_photo = photo_array[-1]
    file_id = largest_photo['file_id']
    
    # Виклик send_telegram без parse_mode, щоб не ламати код
    send_telegram(chat_id, "🔍 Фото отримано. Розпочинаю розпізнавання...")
    
    # Отримуємо URL файлу
    file_url = get_file_url(file_id)
    if not file_url:
        send_telegram(chat_id, "❗️ Не вдалося отримати посилання на файл.")
        return
        
    # --- Етап 2: Завантаження та Розпізнавання (Rekognition DetectText) ---
    search_query = "невідомий товар"
    s3_key = f"telegram_images/{file_id}.jpg"
    
    try:
        # 2a. Завантаження з Telegram та зберігання в S3
        image_data = urllib.request.urlopen(file_url).read()
        s3 = boto3.client('s3')
        s3.put_object(Bucket=S3_BUCKET_NAME, Key=s3_key, Body=image_data)
        
        # 3. Розпізнавання ТЕКСТУ (DetectText) для точнішого пошуку бренду
        text_response = rekognition_client.detect_text(
            Image={'S3Object': {'Bucket': S3_BUCKET_NAME, 'Name': s3_key}}
        )

        # 3a. Вилучення тексту з високою впевненістю
        found_text = [
            t['DetectedText'] for t in text_response['TextDetections'] 
            if t['Type'] == 'WORD' and t['Confidence'] > 85 # Збільшили впевненість
        ]
        
        # 3b. Пошук відомих брендів або найдовшого слова
        known_brands = ['TEREA', 'ILUMA', 'IQOS', 'HEETS']
        
        for word in found_text:
            upper_word = word.upper()
            if upper_word in known_brands:
                search_query = upper_word
                break
            # Якщо не знайшли бренду, беремо найдовше слово (краще, ніж "Box")
            if len(upper_word) > len(search_query) and upper_word.isalpha():
                 search_query = upper_word
        
        if search_query == "невідомий товар" and found_text:
             search_query = found_text[0] # Беремо перше слово, якщо нічого кращого не знайшли

        # Повідомлення про успішне розпізнавання (тепер з parse_mode!)
        send_telegram(
            chat_id, 
            f"✅ Розпізнано як: *{search_query}*.\nШукаю пропозиції...", 
            parse_mode='Markdown'
        )
        
    except Exception as e:
        error_msg = f"❗️ Помилка розпізнавання або S3: {e}"
        print(error_msg)
        send_telegram(chat_id, error_msg)
        return

    # --- Етап 4: Пошук найкращих пропозицій ---
    
    try:
        # ЗАГЛУШКА ДЛЯ ПОШУКУ
        base_search_url = "https://www.google.com/search?q="
        
        # 1. Генерація посилання на Google Shopping Search
        encoded_query = urllib.parse.quote(f"{search_query} купити ціна")
        google_shopping_link = f"{base_search_url}{encoded_query}&tbm=shop"
        
        # 2. Формування результату для клієнта
        
        result_message = f"🛍️ *Знайдені пропозиції для {search_query}:*\n\n"
        
        result_message += f"🔗 [Переглянути пропозиції в Google Shopping]({google_shopping_link})\n\n"
        
        # Надсилаємо фінальний результат (з parse_mode!)
        send_telegram(chat_id, result_message, parse_mode='Markdown')
        
    except Exception as e:
        error_msg = f"❗️ Помилка пошуку пропозицій: {e}"
        print(error_msg)
        send_telegram(chat_id, error_msg)

# --- Головний обробник Lambda (для API Gateway/Webhook) ---

def lambda_handler(event, context):
    try:
        print("===== ПОВНИЙ ВХІДНИЙ EVENT З API GATEWAY =====")
        print(event) 
        print("==============================================")
        body = json.loads(event['body'])
        message = body['message']
        chat_id = message['chat']['id']
        
        if 'body' not in event or event['body'] is None:
            # Це може бути тестовий GET-запит або проблема з налаштуванням API Gateway.
            print("Помилка: Відсутнє тіло запиту ('body' key is missing or None).")
            return {'statusCode': 400, 'body': 'Bad Request: Missing body'}
        body = json.loads(event['body'])
        
        # Перевірка, чи є оновлення повідомлення
        if 'message' not in body:
            return {'statusCode': 200, 'body': 'No message object'}

        message = body['message']
        chat_id = message['chat']['id']
        
        # Перевірка, чи є фото
        if 'photo' in message:
            handle_photo(chat_id, message['photo'])
        
        # Обробка текстових команд (наприклад, /start)
        elif 'text' in message:
            text = message['text']
            if text == '/start':
                send_telegram(chat_id, "👋 Привіт! Надішліть мені фотографію товару, і я знайду найкращі ціни в Інтернеті.")
        
        return {'statusCode': 200, 'body': 'OK'}

    except Exception as e:
        print(f"Головна помилка обробки: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}