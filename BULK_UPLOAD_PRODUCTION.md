# Carga Masiva desde Local conectado a Base de Datos de Producción

## Contexto

Como PythonAnywhere no soporta Celery, la carga masiva de productos se ejecuta **desde tu máquina local** pero conectándose a la **base de datos de producción**. De esta forma:

- Los archivos se suben al mismo S3 compartido (ya configurado)
- Los registros se crean directamente en la BD de producción
- No necesitas Celery en producción
- Puedes procesar muchos archivos cómodamente desde local

## Pasos para Hacer Carga Masiva

### 1. Obtener Credenciales de Base de Datos de PythonAnywhere

1. Inicia sesión en PythonAnywhere
2. Ve a la pestaña **"Databases"**
3. Anota los siguientes datos:
   - `Host`: ejemplo: `tunombreusuario.mysql.pythonanywhere-services.com`
   - `Database name`: ejemplo: `tunombreusuario$nombre_bd`
   - `Username`: ejemplo: `tunombreusuario`
   - `Password`: tu contraseña de MySQL

### 2. Configurar Variables de Entorno Locales

Crea o edita tu archivo `.env` local con estas variables:

```env
# Base de datos de PRODUCCIÓN (para bulk upload)
USE_PRODUCTION_DB=True
PROD_DB_NAME=tunombreusuario$nombre_bd
PROD_DB_USER=tunombreusuario
PROD_DB_PASSWORD=tu_password_mysql
PROD_DB_HOST=tunombreusuario.mysql.pythonanywhere-services.com
PROD_DB_PORT=3306

# Gemini API (para extracción de IA)
GEMINI_API_KEY=tu_api_key_de_gemini

# AWS S3 (ya debería estar configurado igual que producción)
AWS_ACCESS_KEY_ID=tu_aws_key
AWS_SECRET_ACCESS_KEY=tu_aws_secret
AWS_STORAGE_BUCKET_NAME=tu_bucket_nombre
AWS_S3_REGION_NAME=us-east-2
```

### 3. Modificar settings.py Temporalmente

Agrega esto a tu `config/settings.py` (al final del archivo):

```python
# =================================================================================
# CONFIGURACIÓN PARA BULK UPLOAD CON BD DE PRODUCCIÓN
# =================================================================================
if os.getenv('USE_PRODUCTION_DB', 'False') == 'True':
    print("⚠️  USANDO BASE DE DATOS DE PRODUCCIÓN ⚠️")
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('PROD_DB_NAME'),
            'USER': os.getenv('PROD_DB_USER'),
            'PASSWORD': os.getenv('PROD_DB_PASSWORD'),
            'HOST': os.getenv('PROD_DB_HOST'),
            'PORT': os.getenv('PROD_DB_PORT', '3306'),
            'OPTIONS': {
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'"
            }
        }
    }
```

### 4. Instalar Driver de MySQL (si no lo tienes)

```bash
pip install mysqlclient
```

O si da problemas en Windows:
```bash
pip install pymysql
```

Y agrega esto al inicio de `config/__init__.py`:
```python
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pass
```

### 5. Ejecutar el Servidor Local con BD de Producción

**IMPORTANTE**: Antes de ejecutar, asegúrate de que el `.env` tiene `USE_PRODUCTION_DB=True`

```bash
python manage.py runserver
```

Deberías ver en la consola:
```
⚠️  USANDO BASE DE DATOS DE PRODUCCIÓN ⚠️
```

### 6. Hacer la Carga Masiva

1. Abre el navegador en: `http://localhost:8000/panel/productos/bulk-upload/`
2. Selecciona tus archivos PDF/PNG (hasta 50 a la vez)
3. Haz clic en "Iniciar Carga"
4. Espera a que termine el procesamiento (se hace síncronamente)
5. Verifica los productos creados

### 7. Desconectar de Producción

**IMPORTANTE**: Cuando termines, edita tu `.env` y cambia:

```env
USE_PRODUCTION_DB=False
```

O simplemente comenta la línea:
```env
# USE_PRODUCTION_DB=True
```

Y reinicia el servidor para volver a usar la BD local.

## Verificación en Producción

Después de hacer la carga masiva:

1. Ve a tu sitio de producción en PythonAnywhere
2. Accede al panel de productos: `https://tusitio.com/panel/productos/`
3. Verifica que los productos aparecen
4. Los archivos estarán en S3 (compartido)
5. Edita los productos para:
   - Asignar categorías
   - Poner en línea los que quieras mostrar
   - Ajustar precios si es necesario

## Seguridad

⚠️ **NUNCA** subas el archivo `.env` con credenciales de producción a Git

Agrega esto a `.gitignore`:
```
.env
.env.production
*.env.local
```

## Solución de Problemas

### Error: "Access denied for user"
- Verifica las credenciales en tu `.env`
- Asegúrate de que la contraseña de MySQL sea correcta
- En PythonAnywhere, ve a "Databases" y resetea la contraseña si es necesario

### Error: "Can't connect to MySQL server"
- Verifica que tu IP esté en la whitelist de PythonAnywhere
- O usa una conexión VPN si es necesario
- PythonAnywhere permite conexiones externas solo para cuentas de pago

### Los archivos no suben a S3
- Verifica que las credenciales AWS en `.env` sean las mismas que en producción
- Verifica que el bucket name sea correcto

### La IA no genera descripciones
- Verifica que `GEMINI_API_KEY` esté configurada en tu `.env`
- Prueba la API key en: https://aistudio.google.com/

## Flujo Recomendado

```
┌─────────────────────┐
│  Tu Computadora     │
│  (Local + Gemini)   │
│                     │
│  1. Procesa PDFs    │
│  2. Extrae con IA   │
│  3. Genera imágenes │
└──────────┬──────────┘
           │
           ├────────────► AWS S3 (Compartido)
           │              - source_files/
           │              - products_img/
           │
           └────────────► PythonAnywhere MySQL
                          - Tabla products
                          - Tabla bulkuploadbatch
                          - Tabla bulkuploaditem
```

## Alternativa: Si PythonAnywhere bloquea acceso externo

Si no puedes conectarte externamente a MySQL de PythonAnywhere:

1. **Opción A**: Exporta los productos creados localmente:
   ```bash
   python manage.py dumpdata products.Product products.ProductVariant --indent 2 > products_export.json
   ```

   Luego en PythonAnywhere:
   ```bash
   python manage.py loaddata products_export.json
   ```

2. **Opción B**: Actualiza tu plan de PythonAnywhere para permitir acceso externo a MySQL

3. **Opción C**: Usa SSH tunnel:
   ```bash
   ssh -L 3306:localhost:3306 tunombreusuario@ssh.pythonanywhere.com
   ```
   Y conecta a `localhost:3306` en tu `.env`
