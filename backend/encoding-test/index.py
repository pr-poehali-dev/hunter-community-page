import json
import os
import psycopg2

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Admin-Token',
}


def handler(event: dict, context) -> dict:
    """
    Тестирование совместимости кодировок при импорте данных из легаси систем (CP1251/LATIN1).
    Режимы:
      - text=<строка> — анализирует текст через length() и octet_length()
      - hex=<hex-строка> — декодирует hex в bytea, конвертирует из LATIN1 и применяет length(), octet_length(), substring(... from 1 for 5)
    Требует заголовок X-Admin-Token.
    """
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': ''}

    token = event.get('headers', {}).get('X-Admin-Token', '')
    if token != os.environ.get('ADMIN_TOKEN', ''):
        return {
            'statusCode': 403,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Forbidden'}),
        }

    params = event.get('queryStringParameters') or {}
    text_param = params.get('text')
    hex_param = params.get('hex')

    if not text_param and not hex_param:
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Укажите параметр text= или hex='}),
        }

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()

    if text_param:
        cur.execute(
            "SELECT length(%s), octet_length(%s)",
            (text_param, text_param),
        )
        row = cur.fetchone()
        result = {
            'mode': 'text',
            'input': text_param,
            'length': row[0],
            'octet_length': row[1],
        }
    else:
        cur.execute(
            "SELECT length(convert_from(decode(%s, 'hex'), 'LATIN1')),"
            "       octet_length(convert_from(decode(%s, 'hex'), 'LATIN1')),"
            "       substring(convert_from(decode(%s, 'hex'), 'LATIN1') from 1 for 5)",
            (hex_param, hex_param, hex_param),
        )
        row = cur.fetchone()
        result = {
            'mode': 'hex',
            'input': hex_param,
            'length': row[0],
            'octet_length': row[1],
            'substring_1_5': row[2],
        }

    cur.close()
    conn.close()

    return {
        'statusCode': 200,
        'headers': CORS_HEADERS,
        'body': json.dumps(result, ensure_ascii=False),
    }
