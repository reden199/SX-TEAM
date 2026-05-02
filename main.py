import os
import sqlite3
import asyncio
import json
import discord
from discord.ext import commands
from flask import Flask
from threading import Thread
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials

# ================ Keep-alive no Render ================
app = Flask('')
@app.route('/')
def home():
    return "Bot está online!"
def run():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 3000)))
def keep_alive():
    Thread(target=run).start()

# ================ Configurações do bot ================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ================ SQLite local ================
DB_FILENAME = 'xp_data.db'
db_changed = False
db_lock = asyncio.Lock()

def init_db():
    conn = sqlite3.connect(DB_FILENAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS counts (
        guild_id TEXT, user_id TEXT, count INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id))''')
    conn.commit()
    conn.close()

def increment_count(guild_id, user_id):
    global db_changed
    conn = sqlite3.connect(DB_FILENAME)
    c = conn.cursor()
    c.execute('''INSERT INTO counts (guild_id, user_id, count) VALUES (?,?,1)
                 ON CONFLICT(guild_id, user_id) DO UPDATE SET count = count + 1''',
              (str(guild_id), str(user_id)))
    conn.commit()
    conn.close()
    db_changed = True

def get_count(guild_id, user_id):
    conn = sqlite3.connect(DB_FILENAME)
    c = conn.cursor()
    c.execute('SELECT count FROM counts WHERE guild_id=? AND user_id=?',
              (str(guild_id), str(user_id)))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

# ================ Google Drive ================
FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID')  # ID da pasta que você criou
DRIVE_FILE_NAME = 'xp_data.db'

def get_drive():
    """Autentica no Google Drive usando conta de serviço via variáveis de ambiente."""
    # Monta o JSON de credenciais a partir das variáveis
    creds_dict = {
        "type": "service_account",
        "project_id": os.environ.get("GDRIVE_PROJECT_ID"),
        "private_key_id": os.environ.get("GDRIVE_PRIVATE_KEY_ID", ""),
        "private_key": os.environ.get("GDRIVE_PRIVATE_KEY").replace('\\n', '\n'),
        "client_email": os.environ.get("GDRIVE_CLIENT_EMAIL"),
        "client_id": os.environ.get("GDRIVE_CLIENT_ID", ""),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": os.environ.get("GDRIVE_CLIENT_CERT_URL", "")
    }
    scope = ['https://www.googleapis.com/auth/drive.file']
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    gauth = GoogleAuth()
    gauth.credentials = credentials
    return GoogleDrive(gauth)

async def upload_to_drive():
    """Envia o arquivo local para a pasta, substituindo o anterior."""
    if not FOLDER_ID:
        return
    global db_changed
    async with db_lock:
        try:
            drive = get_drive()
            # Procura arquivo com o mesmo nome na pasta
            file_list = drive.ListFile({
                'q': f"'{FOLDER_ID}' in parents and title='{DRIVE_FILE_NAME}' and trashed=false"
            }).GetList()
            # Deleta os antigos
            for f in file_list:
                f.Delete()
            # Faz upload do novo
            file_drive = drive.CreateFile({
                'title': DRIVE_FILE_NAME,
                'parents': [{'id': FOLDER_ID}]
            })
            file_drive.SetContentFile(DB_FILENAME)
            file_drive.Upload()
            db_changed = False
            print("✅ Banco sincronizado com Google Drive.")
        except Exception as e:
            print(f"❌ Erro no upload para Drive: {e}")

async def download_from_drive():
    """Baixa o banco mais recente da pasta, se existir."""
    if not FOLDER_ID:
        return
    try:
        drive = get_drive()
        file_list = drive.ListFile({
            'q': f"'{FOLDER_ID}' in parents and title='{DRIVE_FILE_NAME}' and trashed=false",
            'orderBy': 'modifiedDate desc',
            'maxResults': 1
        }).GetList()
        if file_list:
            file_drive = file_list[0]
            file_drive.GetContentFile(DB_FILENAME)
            print(f"✅ Banco baixado do Drive ({file_drive['fileSize']} bytes).")
        else:
            print("ℹ️ Nenhum banco encontrado no Drive, iniciando zerado.")
    except Exception as e:
        print(f"❌ Erro ao baixar do Drive: {e}")

async def sync_loop():
    await bot.wait_until_ready()
    # Restaura banco na inicialização
    await download_from_drive()
    init_db()  # garante a tabela
    # Loop de sincronização a cada 30s se houve mudança
    while not bot.is_closed():
        await asyncio.sleep(30)
        if db_changed:
            await upload_to_drive()

# ================ Eventos ================
@bot.event
async def on_ready():
    print(f'🤖 {bot.user} online')
    await bot.change_presence(activity=discord.Game("!help | XP e Mod"))
    bot.loop.create_task(sync_loop())

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    increment_count(message.guild.id, message.author.id)
    await bot.process_commands(message)

# ================ Comandos ================
# (todos os comandos de moderação e xp permanecem IDÊNTICOS aos que você já tem)
# Apenas adaptei a função de XP para buscar do SQLite local

def get_xp(total):
    return (total // 5) * 3

# Exemplo do comando !xp / !perfil
@bot.command(aliases=['perfil'])
async def xp(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    total = get_count(ctx.guild.id, member.id)
    xp = get_xp(total)
    embed = discord.Embed(title=f"Perfil de {member.display_name}", color=0x3498db)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Mensagens", value=total, inline=True)
    embed.add_field(name="XP", value=xp, inline=True)
    await ctx.send(embed=embed)

# Comandos de moderação: !ban, !kick, !mute, !unmute, !lock, !unlock, !delete
# (copie os mesmos códigos anteriores que estavam funcionando, sem alterações)

# ================ Inicialização ================
if __name__ == '__main__':
    keep_alive()
    TOKEN = os.environ.get('DISCORD_TOKEN')
    if not TOKEN:
        print("❌ Token não definido!")
    else:
        bot.run(TOKEN)
