import os
import sqlite3
import asyncio
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
FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID')
DRIVE_FILE_NAME = 'xp_data.db'

def get_drive():
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
    if not FOLDER_ID:
        return
    global db_changed
    async with db_lock:
        try:
            drive = get_drive()
            file_list = drive.ListFile({
                'q': f"'{FOLDER_ID}' in parents and title='{DRIVE_FILE_NAME}' and trashed=false"
            }).GetList()
            for f in file_list:
                f.Delete()
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
    await download_from_drive()
    init_db()
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

# ================ Cálculo de XP ================
def get_xp(total):
    return (total // 5) * 3

# ================ Comandos de Moderação ================
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="Não especificado"):
    """Bane um membro do servidor."""
    if member == ctx.author:
        await ctx.send("❌ Você não pode se banir.")
        return
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("❌ Você não pode banir alguém com cargo superior ou igual ao seu.")
        return
    await member.ban(reason=reason)
    await ctx.send(f"✅ {member.mention} foi banido. Motivo: {reason}")

@ban.error
async def ban_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Você precisa da permissão **Banir membros**.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Membro não encontrado.")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, *, user):
    """Desbane um usuário pelo nome#discriminador."""
    banned = [entry async for entry in ctx.guild.bans()]
    for ban_entry in banned:
        if str(ban_entry.user) == user:
            await ctx.guild.unban(ban_entry.user)
            await ctx.send(f"✅ {ban_entry.user} foi desbanido.")
            return
    await ctx.send("❌ Usuário não encontrado na lista de bans.")

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="Não especificado"):
    """Expulsa um membro do servidor."""
    if member == ctx.author:
        await ctx.send("❌ Você não pode se expulsar.")
        return
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("❌ Você não pode expulsar alguém com cargo superior ou igual ao seu.")
        return
    await member.kick(reason=reason)
    await ctx.send(f"✅ {member.mention} foi expulso. Motivo: {reason}")

@kick.error
async def kick_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Você precisa da permissão **Expulsar membros**.")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, minutes: int = 60, *, reason="Não especificado"):
    """Aplica timeout (castigo) em um membro."""
    if member == ctx.author:
        await ctx.send("❌ Você não pode se mutar.")
        return
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("❌ Você não pode mutar alguém com cargo superior ou igual ao seu.")
        return
    duration = minutes * 60
    await member.timeout(discord.utils.utcnow() + discord.timedelta(seconds=duration), reason=reason)
    await ctx.send(f"🔇 {member.mention} foi mutado por {minutes} minuto(s). Motivo: {reason}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    """Remove o timeout do membro."""
    if member.timed_out_until is None:
        await ctx.send(f"❌ {member.mention} não está mutado.")
        return
    await member.timeout(None)
    await ctx.send(f"🔊 {member.mention} foi desmutado.")

# ================ Comandos de Canal ================
@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    """Trava o canal para apenas o dono falar."""
    guild = ctx.guild
    channel = ctx.channel
    await channel.set_permissions(guild.default_role, send_messages=False)
    await channel.set_permissions(guild.owner, send_messages=True)
    await ctx.send("🔒 Canal travado. Apenas o dono do servidor pode enviar mensagens agora.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    """Destrava o canal."""
    guild = ctx.guild
    channel = ctx.channel
    await channel.set_permissions(guild.default_role, send_messages=None)
    await channel.set_permissions(guild.owner, send_messages=None)
    await ctx.send("🔓 Canal destravado. Todos podem voltar a enviar mensagens.")

# ================ Comando Delete ================
@bot.command(name='delete')
@commands.has_permissions(manage_messages=True)
async def delete_messages(ctx, amount: int):
    """Apaga uma quantidade de mensagens (máximo 100)."""
    if amount < 1:
        return await ctx.send("❌ Número inválido.")
    if amount > 100:
        amount = 100
    deleted = await ctx.channel.purge(limit=amount)
    msg = await ctx.send(f"🧹 {len(deleted)} mensagens apagadas.")
    await asyncio.sleep(3)
    await msg.delete()

# ================ Comandos de XP / Perfil ================
@bot.command(aliases=['perfil'])
async def xp(ctx, member: discord.Member = None):
    """Mostra o perfil com nome, avatar e XP."""
    if member is None:
        member = ctx.author
    total = get_count(ctx.guild.id, member.id)
    xp = get_xp(total)
    embed = discord.Embed(title=f"Perfil de {member.display_name}", color=discord.Color.blue())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Mensagens enviadas", value=total, inline=True)
    embed.add_field(name="XP", value=xp, inline=True)
    await ctx.send(embed=embed)

# ================ Inicialização ================
if __name__ == '__main__':
    keep_alive()
    TOKEN = os.environ.get('DISCORD_TOKEN')
    if not TOKEN:
        print("❌ Token não definido!")
    else:
        bot.run(TOKEN)
