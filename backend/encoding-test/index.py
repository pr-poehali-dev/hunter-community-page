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
    Тестирование совместимости кодировок при импорте данных из легаси систем.
    Режимы:
      - text=<строка> — анализирует текст через length() и octet_length()
      - hex=<hex-строка> — декодирует hex в bytea, конвертирует из указанной кодировки (encoding=, по умолчанию LATIN1)
        и применяет length(), octet_length(), substring(... from 1 for 5)
    Параметр encoding: LATIN1 | UTF8 | SQL_ASCII | WIN1251 и др. (любая кодировка PostgreSQL)
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

    ALLOWED_ENCODINGS = {
        'LATIN1', 'UTF8', 'SQL_ASCII', 'WIN1251', 'WIN866',
        'KOI8R', 'KOI8U', 'ISO_8859_5', 'WIN1252',
    }

    params = event.get('queryStringParameters') or {}
    text_param = params.get('text')
    hex_param = params.get('hex')
    encoding = params.get('encoding', 'LATIN1').upper()

    if encoding not in ALLOWED_ENCODINGS:
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': f'Недопустимая кодировка: {encoding}. Допустимые: {sorted(ALLOWED_ENCODINGS)}'}),
        }

    if not text_param and not hex_param:
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Укажите параметр text= или hex='}),
        }

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    dsn_params = conn.get_dsn_parameters()
    connection_info = {
        'host': conn.info.host,
        'port': conn.info.port,
        'dbname': conn.info.dbname,
        'user': conn.info.user,
        'server_version': conn.info.server_version,
        'dsn_parameters': dsn_params,
    }
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
            'connection_info': connection_info,
        }
    else:
        sql = (
            f"SELECT length(convert_from(decode(%s, 'hex'), '{encoding}')),"
            f"       octet_length(convert_from(decode(%s, 'hex'), '{encoding}')),"
            f"       substring(convert_from(decode(%s, 'hex'), '{encoding}') from 1 for 5)"
        )
        cur.execute(sql, (hex_param, hex_param, hex_param))
        row = cur.fetchone()
        result = {
            'mode': 'hex',
            'encoding': encoding,
            'input': hex_param,
            'length': row[0],
            'octet_length': row[1],
            'substring_1_5': row[2],
            'connection_info': connection_info,
        }

    cur.close()
    conn.close()

    return {
        'statusCode': 200,
        'headers': CORS_HEADERS,
        'body': json.dumps(result, ensure_ascii=False),
    }