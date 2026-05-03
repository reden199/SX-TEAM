import os
import sqlite3
import asyncio
import discord
import datetime
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
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

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
            print("Banco sincronizado com Google Drive.")
        except Exception as e:
            print(f"Erro no upload para Drive: {e}")

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
            print(f"Banco baixado do Drive ({file_drive['fileSize']} bytes).")
        else:
            print("Nenhum banco encontrado no Drive, iniciando zerado.")
    except Exception as e:
        print(f"Erro ao baixar do Drive: {e}")

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
    print(f'{bot.user} online')
    await bot.change_presence(activity=discord.Game("!help ou / | Comandos"))
    bot.loop.create_task(sync_loop())

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    
    # Se a mensagem for apenas "/" mostra os comandos
    if message.content.strip() == "/":
        embed = discord.Embed(
            title="Lista de Comandos",
            description="Prefixo: `!`\nUse `!comando` para executar",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Moderacao",
            value=(
                "`!ban @usuario [motivo]` - Bane um usuario\n"
                "`!unban Nome#1234` - Desbane um usuario\n"
                "`!kick @usuario [motivo]` - Expulsa um usuario\n"
                "`!mute @usuario [minutos]` - Muta um usuario\n"
                "`!unmute @usuario` - Desmuta um usuario\n"
                "`!lock` - Trava o canal\n"
                "`!unlock` - Destrava o canal\n"
                "`!delete <quantidade>` - Apaga mensagens"
            ),
            inline=False
        )
        
        embed.add_field(
            name="XP e Ranking",
            value=(
                "`!xp` - Mostra seu perfil\n"
                "`!xp @usuario` - Mostra perfil de alguem\n"
                "`!perfil` - Igual ao !xp\n"
                "`!rank` - Top 5 do servidor\n"
                "`!help` - Mostra esta lista"
            ),
            inline=False
        )
        
        embed.set_footer(text="SX Team Bot - Sistema de Moderacao e XP")
        
        await message.channel.send(embed=embed)
        return
    
    # Contagem de XP normal
    increment_count(message.guild.id, message.author.id)
    await bot.process_commands(message)

# ================ Cálculo de XP e Nível ================
def get_xp(total):
    return (total // 5) * 3

def get_level(xp):
    return xp // 10

# ================ Comando HELP ================
@bot.command()
async def help(ctx):
    """Mostra todos os comandos do bot."""
    embed = discord.Embed(
        title="Lista de Comandos",
        description="Prefixo: `!`\nUse `!comando` para executar",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="Moderacao",
        value=(
            "`!ban @usuario [motivo]` - Bane um usuario\n"
            "`!unban Nome#1234` - Desbane um usuario\n"
            "`!kick @usuario [motivo]` - Expulsa um usuario\n"
            "`!mute @usuario [minutos]` - Muta um usuario\n"
            "`!unmute @usuario` - Desmuta um usuario\n"
            "`!lock` - Trava o canal\n"
            "`!unlock` - Destrava o canal\n"
            "`!delete <quantidade>` - Apaga mensagens"
        ),
        inline=False
    )
    
    embed.add_field(
        name="XP e Ranking",
        value=(
            "`!xp` - Mostra seu perfil\n"
            "`!xp @usuario` - Mostra perfil de alguem\n"
            "`!perfil` - Igual ao !xp\n"
            "`!rank` - Top 5 do servidor\n"
            "`!help` - Mostra esta lista"
        ),
        inline=False
    )
    
    embed.set_footer(text="SX Team Bot - Sistema de Moderacao e XP")
    
    await ctx.send(embed=embed)

# ================ Comandos de Moderacao ================
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="Nao especificado"):
    if member == ctx.author:
        await ctx.send("Voce nao pode se banir.")
        return
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("Voce nao pode banir alguem com cargo superior ou igual ao seu.")
        return
    try:
        await member.ban(reason=reason)
        await ctx.send(f"{member.mention} foi banido. Motivo: {reason}")
    except Exception as e:
        await ctx.send(f"Erro ao banir: {e}")

@ban.error
async def ban_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Voce precisa da permissao Banir membros.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Membro nao encontrado.")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, *, user):
    try:
        banned = [entry async for entry in ctx.guild.bans()]
        for ban_entry in banned:
            if str(ban_entry.user) == user:
                await ctx.guild.unban(ban_entry.user)
                await ctx.send(f"{ban_entry.user} foi desbanido.")
                return
        await ctx.send("Usuario nao encontrado na lista de bans.")
    except Exception as e:
        await ctx.send(f"Erro ao desbanir: {e}")

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="Nao especificado"):
    if member == ctx.author:
        await ctx.send("Voce nao pode se expulsar.")
        return
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("Voce nao pode expulsar alguem com cargo superior ou igual ao seu.")
        return
    try:
        await member.kick(reason=reason)
        await ctx.send(f"{member.mention} foi expulso. Motivo: {reason}")
    except Exception as e:
        await ctx.send(f"Erro ao expulsar: {e}")

@kick.error
async def kick_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Voce precisa da permissao Expulsar membros.")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, minutes: int = 60, *, reason="Nao especificado"):
    if member == ctx.author:
        await ctx.send("Voce nao pode se mutar.")
        return
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("Voce nao pode mutar alguem com cargo superior ou igual ao seu.")
        return
    try:
        duration = minutes * 60
        await member.timeout(discord.utils.utcnow() + datetime.timedelta(seconds=duration), reason=reason)
        await ctx.send(f"{member.mention} foi mutado por {minutes} minuto(s). Motivo: {reason}")
    except Exception as e:
        await ctx.send(f"Erro ao mutar: {e}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    try:
        if member.timed_out_until is None:
            await ctx.send(f"{member.mention} nao esta mutado.")
            return
        await member.timeout(None)
        await ctx.send(f"{member.mention} foi desmutado.")
    except Exception as e:
        await ctx.send(f"Erro ao desmutar: {e}")

# ================ Comandos de Canal ================
@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    try:
        guild = ctx.guild
        channel = ctx.channel
        await channel.set_permissions(guild.default_role, send_messages=False)
        await channel.set_permissions(guild.owner, send_messages=True)
        await ctx.send("Canal travado. Apenas o dono do servidor pode enviar mensagens agora.")
    except Exception as e:
        await ctx.send(f"Erro ao travar canal: {e}")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    try:
        guild = ctx.guild
        channel = ctx.channel
        await channel.set_permissions(guild.default_role, send_messages=None)
        await channel.set_permissions(guild.owner, send_messages=None)
        await ctx.send("Canal destravado. Todos podem voltar a enviar mensagens.")
    except Exception as e:
        await ctx.send(f"Erro ao destravar canal: {e}")

# ================ Comando Delete ================
@bot.command(name='delete')
@commands.has_permissions(manage_messages=True)
async def delete_messages(ctx, amount: int):
    if amount < 1:
        return await ctx.send("Numero invalido.")
    if amount > 100:
        amount = 100
    try:
        deleted = await ctx.channel.purge(limit=amount)
        msg = await ctx.send(f"{len(deleted)} mensagens apagadas.")
        await asyncio.sleep(3)
        await msg.delete()
    except Exception as e:
        await ctx.send(f"Erro ao apagar mensagens: {e}")

# ================ Comandos de XP / Perfil / Rank ================
@bot.command(aliases=['perfil'])
async def xp(ctx, member: discord.Member = None):
    """Mostra o perfil com nome, avatar, XP e nivel."""
    if member is None:
        member = ctx.author
    
    total_mensagens = get_count(ctx.guild.id, member.id)
    xp = get_xp(total_mensagens)
    nivel = get_level(xp)
    
    embed = discord.Embed(
        title=f"Perfil de {member.display_name}",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Mensagens", value=total_mensagens, inline=True)
    embed.add_field(name="XP", value=f"{xp}", inline=True)
    embed.add_field(name="Nivel", value=f"{nivel}", inline=True)
    
    # Barra de progresso para o proximo nivel
    xp_atual = xp % 10
    xp_necessario = 10
    progresso = int((xp_atual / xp_necessario) * 10)
    barra = "[" + "#" * progresso + "-" * (10 - progresso) + "]"
    embed.add_field(
        name=f"Progresso para nivel {nivel + 1}",
        value=f"{barra} ({xp_atual}/{xp_necessario} XP)",
        inline=False
    )
    
    await ctx.send(embed=embed)

@bot.command()
async def rank(ctx):
    """Mostra o top 5 usuarios com mais XP no servidor."""
    
    conn = sqlite3.connect(DB_FILENAME)
    c = conn.cursor()
    c.execute('SELECT user_id, count FROM counts WHERE guild_id = ? ORDER BY count DESC', (str(ctx.guild.id),))
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        await ctx.send("Nenhum dado de XP registrado ainda!")
        return
    
    embed = discord.Embed(
        title="Ranking - Top 5",
        description="Os membros com mais XP do servidor",
        color=discord.Color.gold()
    )
    
    posicoes = {1: "1.", 2: "2.", 3: "3.", 4: "4.", 5: "5."}
    
    count = 0
    for row in rows:
        user_id = int(row[0])
        total_mensagens = row[1]
        xp = get_xp(total_mensagens)
        nivel = get_level(xp)
        
        member = ctx.guild.get_member(user_id)
        
        if member:
            count += 1
            if count > 5:
                break
            
            nome = member.display_name
            
            embed.add_field(
                name=f"{posicoes[count]} {nome}",
                value=f"XP: **{xp}** | Nivel: **{nivel}** | Mensagens: {total_mensagens}",
                inline=False
            )
    
    if count == 0:
        await ctx.send("Nenhum membro encontrado no ranking.")
        return
    
    await ctx.send(embed=embed)

# ================ Inicializacao ================
if __name__ == '__main__':
    keep_alive()
    TOKEN = os.environ.get('DISCORD_TOKEN')
    if not TOKEN:
        print("Token nao definido!")
    else:
        bot.run(TOKEN)
