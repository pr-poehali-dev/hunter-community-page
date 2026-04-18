import json
import os
import re
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
        'KOI8R', 'KOI8U', 'ISO_8859_5', 'WIN1252', 'GB18030',
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

    db_url = os.environ.get('DATABASE_URL', '')
    db_url_safe = re.sub(r'://[^@]+@', '://<credentials>@', db_url)
    env_check = {
        'DATABASE_URL': bool(db_url),
        'ADMIN_TOKEN': bool(os.environ.get('ADMIN_TOKEN')),
        'db_url_preview': db_url_safe[:80] + ('...' if len(db_url_safe) > 80 else ''),
    }

    conn = psycopg2.connect(db_url)
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
    cur.execute("SELECT version()")
    connection_info['pg_version'] = cur.fetchone()[0]

    cur.execute("SELECT lanname FROM pg_catalog.pg_language")
    available_languages = [row[0] for row in cur.fetchall()]

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
            'env_check': env_check,
            'available_languages': available_languages,
        }
    else:
        t = f"convert_from(decode(%s, 'hex'), '{encoding}')"
        sql = (
            f"SELECT length({t}),"
            f"       octet_length({t}),"
            f"       substring({t} from 1 for 5),"
            f"       overlay({t} placing 'X' from 2 for 1),"
            f"       replace({t}, substring({t} from 1 for 1), 'Y'),"
            f"       translate({t}, substring({t} from 1 for 1), 'Z')"
        )
        cur.execute(sql, (hex_param,) * 9)
        row = cur.fetchone()
        result = {
            'mode': 'hex',
            'encoding': encoding,
            'input': hex_param,
            'length': row[0],
            'octet_length': row[1],
            'substring_1_5': row[2],
            'overlay_test': row[3],
            'replace_test': row[4],
            'translate_test': row[5],
            'connection_info': connection_info,
            'env_check': env_check,
            'available_languages': available_languages,
        }

    cur.close()
    conn.close()

    return {
        'statusCode': 200,
        'headers': CORS_HEADERS,
        'body': json.dumps(result, ensure_ascii=False),
    }