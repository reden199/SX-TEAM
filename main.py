import os
import sqlite3
import asyncio
import discord
import datetime
from discord import app_commands
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
bot = commands.Bot(command_prefix='/', intents=intents, help_command=None)

# ================ Restrição de canal ================
CANAL_PERMITIDO = 1500291470530314331  # ID do canal onde os comandos são liberados para todos

@bot.tree.interaction_check
async def global_channel_restriction(interaction: discord.Interaction) -> bool:
    # Administradores passam direto
    if interaction.user.guild_permissions.administrator:
        return True

    # Canal permitido
    if interaction.channel_id == CANAL_PERMITIDO:
        return True

    # Bloqueio – garante que a resposta seja enviada apenas uma vez
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                f"❌ Comandos só podem ser usados no canal <#{CANAL_PERMITIDO}>. "
                "Administradores podem usar em qualquer lugar.",
                ephemeral=True
            )
    except:
        pass
    return False

# ================ Check de canal para prefix commands ================
def canal_restrito_texto():
    async def predicate(ctx):
        # Administradores podem usar em qualquer lugar
        if ctx.author.guild_permissions.administrator:
            return True
        # Canal permitido
        if ctx.channel.id == CANAL_PERMITIDO:
            return True
        # Bloqueia e avisa
        await ctx.send(
            f"❌ Comandos só podem ser usados no canal <#{CANAL_PERMITIDO}>. "
            "Administradores podem usar em qualquer lugar.",
            delete_after=10
        )
        return False
    return commands.check(predicate)
    
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
    await bot.change_presence(activity=discord.Game("Use /comando"))
    try:
        synced = await bot.tree.sync()
        print(f"Slash commands sincronizados: {len(synced)} comandos")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")
    bot.loop.create_task(sync_loop())

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    increment_count(message.guild.id, message.author.id)
    await bot.process_commands(message)

# ================ Novo evento: boas-vindas e cargo automático ================
@bot.event
async def on_member_join(member):
    # Cargo "Verificado" (ID fornecido)
    cargo_verificado = member.guild.get_role(1500257493270401206)
    if cargo_verificado:
        try:
            await member.add_roles(cargo_verificado)
            print(f"Cargo Verificado atribuído a {member.display_name}")
        except Exception as e:
            print(f"Erro ao adicionar cargo Verificado: {e}")

    # Canal de boas-vindas (ID fornecido)
    canal_boasvindas = member.guild.get_channel(1500236759693266985)
    if canal_boasvindas:
        embed = discord.Embed(
            title="👋 Seja bem vindo!",
            description=f"{member.mention} acabou de entrar no servidor.",
            color=discord.Color.green()
        )
        # Avatar do usuário como thumbnail (quadrado)
        embed.set_thumbnail(url=member.display_avatar.url)
        # Se quiser o avatar redondo, seria necessário usar Pillow para criar uma imagem circular.
        # No Discord o thumbnail sempre aparece quadrado.
        try:
            await canal_boasvindas.send(embed=embed)
        except Exception as e:
            print(f"Erro ao enviar mensagem de boas-vindas: {e}")

# ================ Cálculo de XP e Nível ================
def get_xp(total):
    return (total // 5) * 3

def get_level(xp):
    return xp // 10

# ================ SLASH COMMANDS ================

# --- MODERAÇÃO ---

@bot.tree.command(name="ban", description="Bane um usuário do servidor")
@app_commands.describe(membro="Usuário a ser banido", motivo="Motivo do banimento")
@app_commands.default_permissions(ban_members=True)
async def slash_ban(interaction: discord.Interaction, membro: discord.Member, motivo: str = "Não especificado"):
    if membro == interaction.user:
        await interaction.response.send_message("Você não pode se banir.", ephemeral=True)
        return
    if membro.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("Você não pode banir alguém com cargo superior ou igual ao seu.", ephemeral=True)
        return
    try:
        await membro.ban(reason=motivo)
        await interaction.response.send_message(f"{membro.mention} foi banido. Motivo: {motivo}")
    except Exception as e:
        await interaction.response.send_message(f"Erro ao banir: {e}", ephemeral=True)

@bot.tree.command(name="unban", description="Desbane um usuário pelo nome ou nome#tag")
@app_commands.describe(usuario="Nome do usuário banido (ex: Fulano ou Fulano#1234)")
@app_commands.default_permissions(ban_members=True)
async def slash_unban(interaction: discord.Interaction, usuario: str):
    try:
        bans = [entry async for entry in interaction.guild.bans()]
        if not bans:
            await interaction.response.send_message("Não há usuários banidos neste servidor.", ephemeral=True)
            return

        encontrados = []
        for entry in bans:
            if str(entry.user) == usuario:
                encontrados.append(entry.user)

        if not encontrados:
            usuario_lower = usuario.lower()
            for entry in bans:
                if usuario_lower in entry.user.name.lower() or usuario_lower in str(entry.user).lower():
                    encontrados.append(entry.user)

        if not encontrados:
            await interaction.response.send_message("Nenhum usuário banido corresponde a esse nome.", ephemeral=True)
            return

        if len(encontrados) > 1:
            nomes = "\n".join(f"• {str(u)}" for u in encontrados[:10])
            await interaction.response.send_message(
                f"Vários usuários correspondem. Seja mais específico:\n{nomes}",
                ephemeral=True
            )
            return

        user_to_unban = encontrados[0]
        await interaction.guild.unban(user_to_unban)
        await interaction.response.send_message(f"{user_to_unban} foi desbanido com sucesso!")
    except Exception as e:
        await interaction.response.send_message(f"Erro ao desbanir: {e}", ephemeral=True)

@bot.tree.command(name="kick", description="Expulsa um usuário do servidor")
@app_commands.describe(membro="Usuário a ser expulso", motivo="Motivo da expulsão")
@app_commands.default_permissions(kick_members=True)
async def slash_kick(interaction: discord.Interaction, membro: discord.Member, motivo: str = "Não especificado"):
    if membro == interaction.user:
        await interaction.response.send_message("Você não pode se expulsar.", ephemeral=True)
        return
    if membro.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("Você não pode expulsar alguém com cargo superior ou igual ao seu.", ephemeral=True)
        return
    try:
        await membro.kick(reason=motivo)
        await interaction.response.send_message(f"{membro.mention} foi expulso. Motivo: {motivo}")
    except Exception as e:
        await interaction.response.send_message(f"Erro ao expulsar: {e}", ephemeral=True)

@bot.tree.command(name="mute", description="Muta um usuário temporariamente")
@app_commands.describe(membro="Usuário a ser mutado", minutos="Duração em minutos (padrão 60)", motivo="Motivo do mute")
@app_commands.default_permissions(moderate_members=True)
async def slash_mute(interaction: discord.Interaction, membro: discord.Member, minutos: int = 60, motivo: str = "Não especificado"):
    if membro == interaction.user:
        await interaction.response.send_message("Você não pode se mutar.", ephemeral=True)
        return
    if membro.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("Você não pode mutar alguém com cargo superior ou igual ao seu.", ephemeral=True)
        return
    try:
        duration = minutos * 60
        await membro.timeout(discord.utils.utcnow() + datetime.timedelta(seconds=duration), reason=motivo)
        await interaction.response.send_message(f"{membro.mention} foi mutado por {minutos} minuto(s). Motivo: {motivo}")
    except Exception as e:
        await interaction.response.send_message(f"Erro ao mutar: {e}", ephemeral=True)

@bot.tree.command(name="unmute", description="Desmuta um usuário")
@app_commands.describe(membro="Usuário a ser desmutado")
@app_commands.default_permissions(moderate_members=True)
async def slash_unmute(interaction: discord.Interaction, membro: discord.Member):
    try:
        if membro.timed_out_until is None:
            await interaction.response.send_message(f"{membro.mention} não está mutado.", ephemeral=True)
            return
        await membro.timeout(None)
        await interaction.response.send_message(f"{membro.mention} foi desmutado.")
    except Exception as e:
        await interaction.response.send_message(f"Erro ao desmutar: {e}", ephemeral=True)

# --- GERENCIAMENTO DE CANAL ---

@bot.tree.command(name="lock", description="Trava o canal atual")
@app_commands.default_permissions(manage_channels=True)
async def slash_lock(interaction: discord.Interaction):
    channel = interaction.channel
    guild = interaction.guild
    try:
        await channel.set_permissions(guild.default_role, send_messages=False)
        await channel.set_permissions(guild.owner, send_messages=True)
        await interaction.response.send_message("Canal travado. Apenas o dono do servidor pode enviar mensagens agora.")
    except Exception as e:
        await interaction.response.send_message(f"Erro ao travar canal: {e}", ephemeral=True)

@bot.tree.command(name="unlock", description="Destrava o canal atual")
@app_commands.default_permissions(manage_channels=True)
async def slash_unlock(interaction: discord.Interaction):
    channel = interaction.channel
    guild = interaction.guild
    try:
        await channel.set_permissions(guild.default_role, send_messages=None)
        await channel.set_permissions(guild.owner, send_messages=None)
        await interaction.response.send_message("Canal destravado. Todos podem voltar a enviar mensagens.")
    except Exception as e:
        await interaction.response.send_message(f"Erro ao destravar canal: {e}", ephemeral=True)

# --- LIMPEZA ---

@bot.tree.command(name="delete", description="Apaga uma quantidade de mensagens do canal")
@app_commands.describe(quantidade="Número de mensagens a apagar (1-100)")
@app_commands.default_permissions(manage_messages=True)
async def slash_delete(interaction: discord.Interaction, quantidade: int):
    if quantidade < 1 or quantidade > 100:
        await interaction.response.send_message("Número inválido (mín 1, máx 100).", ephemeral=True)
        return
    try:
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=quantidade)
        await interaction.followup.send(f"{len(deleted)} mensagens apagadas.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Erro ao apagar mensagens: {e}", ephemeral=True)

# --- XP / PERFIL / RANK ---

@bot.tree.command(name="xp", description="Mostra o perfil e progresso de XP de um usuário")
@app_commands.describe(membro="Usuário (deixe em branco para ver o seu)")
async def slash_xp(interaction: discord.Interaction, membro: discord.Member = None):
    if membro is None:
        membro = interaction.user
    total_mensagens = get_count(interaction.guild.id, membro.id)
    xp = get_xp(total_mensagens)
    nivel = get_level(xp)
    embed = discord.Embed(title=f"Perfil de {membro.display_name}", color=discord.Color.blue())
    embed.set_thumbnail(url=membro.display_avatar.url)
    embed.add_field(name="Mensagens", value=total_mensagens, inline=True)
    embed.add_field(name="XP", value=f"{xp}", inline=True)
    embed.add_field(name="Nível", value=f"{nivel}", inline=True)
    xp_atual = xp % 10
    xp_necessario = 10
    progresso = int((xp_atual / xp_necessario) * 10)
    barra = "[" + "#" * progresso + "-" * (10 - progresso) + "]"
    embed.add_field(
        name=f"Progresso para nível {nivel + 1}",
        value=f"{barra} ({xp_atual}/{xp_necessario} XP)",
        inline=False
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rank", description="Exibe o top 5 usuários com mais XP do servidor")
async def slash_rank(interaction: discord.Interaction):
    conn = sqlite3.connect(DB_FILENAME)
    c = conn.cursor()
    c.execute('SELECT user_id, count FROM counts WHERE guild_id = ? ORDER BY count DESC', (str(interaction.guild.id),))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await interaction.response.send_message("Nenhum dado de XP registrado ainda!", ephemeral=True)
        return
    embed = discord.Embed(title="Ranking - Top 5", description="Os membros com mais XP do servidor", color=discord.Color.gold())
    posicoes = {1: "1.", 2: "2.", 3: "3.", 4: "4.", 5: "5."}
    count = 0
    for row in rows:
        user_id = int(row[0])
        total_mensagens = row[1]
        xp = get_xp(total_mensagens)
        nivel = get_level(xp)
        member = interaction.guild.get_member(user_id)
        if member is None:
            continue
        count += 1
        if count > 5:
            break
        embed.add_field(
            name=f"{posicoes[count]} {member.display_name}",
            value=f"XP: **{xp}** | Nível: **{nivel}** | Mensagens: {total_mensagens}",
            inline=False
        )
    if count == 0:
        await interaction.response.send_message("Nenhum membro encontrado no ranking.", ephemeral=True)
        return
    await interaction.response.send_message(embed=embed)

# ================ PREFIX COMMANDS (comandos por texto) ================

# --- MODERAÇÃO ---

@bot.command(name='ban')
@canal_restrito_texto()
@commands.has_permissions(ban_members=True)
async def prefix_ban(ctx, membro: discord.Member, *, motivo: str = "Não especificado"):
    if membro == ctx.author:
        return await ctx.send("Você não pode se banir.")
    if membro.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        return await ctx.send("Você não pode banir alguém com cargo superior ou igual ao seu.")
    try:
        await membro.ban(reason=motivo)
        await ctx.send(f"{membro.mention} foi banido. Motivo: {motivo}")
    except Exception as e:
        await ctx.send(f"Erro ao banir: {e}")

@bot.command(name='unban')
@canal_restrito_texto()
@commands.has_permissions(ban_members=True)
async def prefix_unban(ctx, *, usuario: str):
    try:
        bans = [entry async for entry in ctx.guild.bans()]
        if not bans:
            return await ctx.send("Não há usuários banidos.")

        encontrados = [entry.user for entry in bans if str(entry.user) == usuario]
        if not encontrados:
            usuario_lower = usuario.lower()
            encontrados = [entry.user for entry in bans if usuario_lower in entry.user.name.lower() or usuario_lower in str(entry.user).lower()]

        if not encontrados:
            return await ctx.send("Nenhum usuário banido corresponde a esse nome.")
        if len(encontrados) > 1:
            nomes = "\n".join(f"• {u}" for u in encontrados[:10])
            return await ctx.send(f"Vários usuários correspondem. Seja mais específico:\n{nomes}")

        user_to_unban = encontrados[0]
        await ctx.guild.unban(user_to_unban)
        await ctx.send(f"{user_to_unban} foi desbanido.")
    except Exception as e:
        await ctx.send(f"Erro: {e}")

@bot.command(name='kick')
@canal_restrito_texto()
@commands.has_permissions(kick_members=True)
async def prefix_kick(ctx, membro: discord.Member, *, motivo: str = "Não especificado"):
    if membro == ctx.author:
        return await ctx.send("Você não pode se expulsar.")
    if membro.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        return await ctx.send("Você não pode expulsar alguém com cargo superior ou igual ao seu.")
    try:
        await membro.kick(reason=motivo)
        await ctx.send(f"{membro.mention} foi expulso. Motivo: {motivo}")
    except Exception as e:
        await ctx.send(f"Erro: {e}")

@bot.command(name='mute')
@canal_restrito_texto()
@commands.has_permissions(moderate_members=True)
async def prefix_mute(ctx, membro: discord.Member, minutos: int = 60, *, motivo: str = "Não especificado"):
    if membro == ctx.author:
        return await ctx.send("Você não pode se mutar.")
    if membro.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        return await ctx.send("Você não pode mutar alguém com cargo superior ou igual ao seu.")
    try:
        duration = minutos * 60
        await membro.timeout(discord.utils.utcnow() + datetime.timedelta(seconds=duration), reason=motivo)
        await ctx.send(f"{membro.mention} mutado por {minutos} minuto(s). Motivo: {motivo}")
    except Exception as e:
        await ctx.send(f"Erro: {e}")

@bot.command(name='unmute')
@canal_restrito_texto()
@commands.has_permissions(moderate_members=True)
async def prefix_unmute(ctx, membro: discord.Member):
    try:
        if membro.timed_out_until is None:
            return await ctx.send(f"{membro.mention} não está mutado.")
        await membro.timeout(None)
        await ctx.send(f"{membro.mention} foi desmutado.")
    except Exception as e:
        await ctx.send(f"Erro: {e}")

# --- GERENCIAMENTO DE CANAL ---

@bot.command(name='lock')
@canal_restrito_texto()
@commands.has_permissions(manage_channels=True)
async def prefix_lock(ctx):
    channel = ctx.channel
    guild = ctx.guild
    try:
        await channel.set_permissions(guild.default_role, send_messages=False)
        await channel.set_permissions(guild.owner, send_messages=True)
        await ctx.send("Canal travado. Apenas o dono do servidor pode enviar mensagens agora.")
    except Exception as e:
        await ctx.send(f"Erro: {e}")

@bot.command(name='unlock')
@canal_restrito_texto()
@commands.has_permissions(manage_channels=True)
async def prefix_unlock(ctx):
    channel = ctx.channel
    guild = ctx.guild
    try:
        await channel.set_permissions(guild.default_role, send_messages=None)
        await channel.set_permissions(guild.owner, send_messages=None)
        await ctx.send("Canal destravado.")
    except Exception as e:
        await ctx.send(f"Erro: {e}")

# --- LIMPEZA ---

@bot.command(name='delete')
@canal_restrito_texto()
@commands.has_permissions(manage_messages=True)
async def prefix_delete(ctx, quantidade: int):
    if quantidade < 1 or quantidade > 100:
        return await ctx.send("Número inválido (mín 1, máx 100).")
    try:
        deleted = await ctx.channel.purge(limit=quantidade)
        await ctx.send(f"{len(deleted)} mensagens apagadas.", delete_after=5)
    except Exception as e:
        await ctx.send(f"Erro: {e}")

# --- XP / PERFIL / RANK ---

@bot.command(name='xp')
@canal_restrito_texto()
async def prefix_xp(ctx, membro: discord.Member = None):
    if membro is None:
        membro = ctx.author
    total_mensagens = get_count(ctx.guild.id, membro.id)
    xp = get_xp(total_mensagens)
    nivel = get_level(xp)
    embed = discord.Embed(title=f"Perfil de {membro.display_name}", color=discord.Color.blue())
    embed.set_thumbnail(url=membro.display_avatar.url)
    embed.add_field(name="Mensagens", value=total_mensagens, inline=True)
    embed.add_field(name="XP", value=xp, inline=True)
    embed.add_field(name="Nível", value=nivel, inline=True)
    xp_atual = xp % 10
    progresso = int((xp_atual / 10) * 10)
    barra = "[" + "#" * progresso + "-" * (10 - progresso) + "]"
    embed.add_field(name=f"Progresso para nível {nivel + 1}", value=f"{barra} ({xp_atual}/10 XP)", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='rank')
@canal_restrito_texto()
async def prefix_rank(ctx):
    conn = sqlite3.connect(DB_FILENAME)
    c = conn.cursor()
    c.execute('SELECT user_id, count FROM counts WHERE guild_id = ? ORDER BY count DESC', (str(ctx.guild.id),))
    rows = c.fetchall()
    conn.close()
    if not rows:
        return await ctx.send("Nenhum dado de XP registrado ainda!")

    embed = discord.Embed(title="Ranking - Top 5", color=discord.Color.gold())
    count = 0
    for row in rows:
        user_id = int(row[0])
        total = row[1]
        xp = get_xp(total)
        nivel = get_level(xp)
        member = ctx.guild.get_member(user_id)
        if member is None:
            continue
        count += 1
        if count > 5:
            break
        embed.add_field(
            name=f"{count}. {member.display_name}",
            value=f"XP: **{xp}** | Nível: **{nivel}** | Mensagens: {total}",
            inline=False
        )
    if count == 0:
        return await ctx.send("Nenhum membro encontrado no ranking.")
    await ctx.send(embed=embed)

# ================ Inicialização ================
if __name__ == '__main__':
    keep_alive()
    TOKEN = os.environ.get('DISCORD_TOKEN')
    if not TOKEN:
        print("Token não definido!")
    else:
        bot.run(TOKEN)
