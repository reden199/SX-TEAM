import os
import asyncio
import discord
import datetime
import traceback
import httpx
import random
from discord import app_commands
from discord.ext import commands
from flask import Flask
from threading import Thread

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

# ================ Supabase via REST API ================
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

async def init_db():
    """Verifica se a conexão com Supabase está funcionando"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ ERRO: SUPABASE_URL ou SUPABASE_KEY não definidas!")
        return
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/counts?limit=1",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}"
                }
            )
            print(f"✅ Conectado ao Supabase via REST API! Status: {response.status_code}")
        except Exception as e:
            print(f"❌ ERRO ao conectar no Supabase: {e}")
            traceback.print_exc()

async def increment_count(guild_id: int, user_id: int):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/counts?guild_id=eq.{guild_id}&user_id=eq.{user_id}&select=count",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}"
                }
            )
            data = response.json()
            
            if data:
                current_count = data[0]['count']
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/counts?guild_id=eq.{guild_id}&user_id=eq.{user_id}",
                    headers={
                        "apikey": SUPABASE_KEY,
                        "Authorization": f"Bearer {SUPABASE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal"
                    },
                    json={"count": current_count + 1}
                )
            else:
                await client.post(
                    f"{SUPABASE_URL}/rest/v1/counts",
                    headers={
                        "apikey": SUPABASE_KEY,
                        "Authorization": f"Bearer {SUPABASE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal"
                    },
                    json={
                        "guild_id": guild_id,
                        "user_id": user_id,
                        "count": 1
                    }
                )
        except Exception as e:
            print(f"ERRO ao incrementar contagem: {e}")

async def get_count(guild_id: int, user_id: int) -> int:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return 0
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/counts?guild_id=eq.{guild_id}&user_id=eq.{user_id}&select=count",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}"
                }
            )
            data = response.json()
            return data[0]['count'] if data else 0
        except Exception as e:
            print(f"ERRO ao obter contagem: {e}")
            return 0

async def get_top_users(guild_id: int, limit: int = 5):
    """Retorna os top usuários por contagem"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/counts?guild_id=eq.{guild_id}&order=count.desc&limit={limit}",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}"
                }
            )
            return response.json()
        except Exception as e:
            print(f"ERRO ao buscar ranking: {e}")
            return []

# ================ Restrição de canal ================
CANAL_PERMITIDO = 1500291470530314331

@bot.tree.interaction_check
async def global_channel_restriction(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    if interaction.channel_id == CANAL_PERMITIDO:
        return True
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

@bot.check
async def global_text_channel_restriction(ctx):
    if ctx.author.guild_permissions.administrator:
        return True
    if ctx.channel.id == CANAL_PERMITIDO:
        return True
    await ctx.send(
        f"❌ Comandos só podem ser usados no canal <#{CANAL_PERMITIDO}>. "
        "Administradores podem usar em qualquer lugar.",
        delete_after=10
    )
    return False

# ================ Eventos ================
@bot.event
async def on_ready():
    await init_db()
    print(f'{bot.user} online')
    await bot.change_presence(activity=discord.Game("Use /comando"))
    try:
        synced = await bot.tree.sync()
        print(f"Slash commands sincronizados: {len(synced)} comandos")
        for cmd in synced:
            print(f"  - /{cmd.name}")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    await increment_count(message.guild.id, message.author.id)
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    cargo_verificado = member.guild.get_role(1500257493270401206)
    if cargo_verificado:
        try:
            await member.add_roles(cargo_verificado)
            print(f"Cargo Verificado atribuído a {member.display_name}")
        except Exception as e:
            print(f"Erro ao adicionar cargo Verificado: {e}")

    canal_boasvindas = member.guild.get_channel(1500236759693266985)
    if canal_boasvindas:
        embed = discord.Embed(
            title="👋 Seja bem vindo!",
            description=f"{member.mention} acabou de entrar no servidor.",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
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

import re

# ================ FUNÇÕES AUXILIARES PARA OS COMANDOS ================
def extrair_emoji_do_nome(nome_canal):
    """Extrai o emoji do início do nome do canal, se existir"""
    emoji_pattern = re.compile(
        "^[" 
        "\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF"
        "\U00002600-\U000026FF\U00002700-\U000027BF\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF\U00002B50\U00002764\U0000203C\U00002049"
        "\U000020E3\U00002934-\U00002935\U00003030\U0000303D\U00003297"
        "\U00003299\U0001F004\U0001F0CF\U0001F170-\U0001F171\U0001F17E"
        "\U0001F17F\U0001F18E\U0001F191-\U0001F19A\U0001F1E6-\U0001F1FF"
        "\U0001F201-\U0001F202\U0001F21A\U0001F22F\U0001F232-\U0001F23A"
        "\U0001F250-\U0001F251\U0001F300-\U0001F321\U0001F324-\U0001F393"
        "\U0001F396-\U0001F397\U0001F399-\U0001F39B\U0001F39E-\U0001F3F0"
        "\U0001F3F3-\U0001F3F5\U0001F3F7-\U0001F4FD\U0001F4FF-\U0001F53D"
        "\U0001F549-\U0001F54E\U0001F550-\U0001F567\U0001F56F-\U0001F570"
        "\U0001F573-\U0001F57A\U0001F587\U0001F58A-\U0001F58D\U0001F590"
        "\U0001F595-\U0001F596\U0001F5A4-\U0001F5A5\U0001F5A8\U0001F5B1"
        "\U0001F5B2\U0001F5BC\U0001F5C2-\U0001F5C4\U0001F5D1-\U0001F5D3"
        "\U0001F5DC-\U0001F5DE\U0001F5E1\U0001F5E3\U0001F5E8\U0001F5EF"
        "\U0001F5F3\U0001F5FA-\U0001F64F\U0001F680-\U0001F6C5\U0001F6CB"
        "\U0001F6D0-\U0001F6D2\U0001F6E0-\U0001F6E5\U0001F6E9\U0001F6EB"
        "\U0001F6EC\U0001F6F0\U0001F6F3-\U0001F6F9\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U0000231A-\U0000231B"
        "\U000023E9-\U000023F3\U000023F8-\U000023FA\U000023ED-\U000023EF"
        "\U0001F440-\U0001F441\U0001F442-\U0001F445\U0001F446-\U0001F450"
        "\U0001F46B-\U0001F46D\U0001F46E-\U0001F470\U0001F471-\U0001F478"
        "\U0001F479-\U0001F47B\U0001F47C-\U0001F480\U0001F481-\U0001F487"
        "\U0001F488-\U0001F48B\U0001F48C-\U0001F48F\U0001F490-\U0001F494"
        "\U0001F5FB-\U0001F5FF\U0001F9D0-\U0001F9E6\U0001F9B0-\U0001F9BB"
        "\U0001F9C0-\U0001F9C2\U0001F9E7-\U0001F9FF\U00002670-\U00002671"
        "\U0000267F\U00002692-\U00002693\U000026A0-\U000026A1\U000026AA"
        "\U000026AB\U000026BD-\U000026BE\U000026C4-\U000026C5\U000026CE"
        "\U000026D4\U000026EA\U000026F2-\U000026F3\U000026F5\U000026FA"
        "\U000026FD\U00002702\U00002708-\U0000270F\U00002712\U00002714"
        "\U00002716\U0000271D\U00002721\U00002733-\U00002734\U00002744"
        "\U00002747\U0000274C\U0000274E\U00002753-\U00002755\U00002757"
        "\U00002763-\U00002764\U00002795-\U00002797\U000027A1\U000027B0"
        "\U000027BF\U00002B05-\U00002B07\U00002B1B-\U00002B1C\U00002B50"
        "\U00002B55\U0001F321\U0001F336\U0001F37D\U0001F396-\U0001F397"
        "\U0001F399-\U0001F39B\U0001F39E-\U0001F39F\U0001F3CB-\U0001F3CE"
        "\U0001F3D4-\U0001F3DF\U0001F3F3-\U0001F3F5\U0001F3F8-\U0001F3F9"
        "\U0001F43F\U0001F441\U0001F4FD-\U0001F4FE\U0001F508-\U0001F50A"
        "\U0001F50C-\U0001F514\U0001F516-\U0001F53D\U0001F549-\U0001F54A"
        "\U0001F54B-\U0001F54E\U0001F56F-\U0001F570\U0001F573-\U0001F579"
        "\U0001F57A\U0001F587\U0001F58A-\U0001F58D\U0001F590\U0001F595"
        "\U0001F596\U0001F5A4\U0001F5A5-\U0001F5A8\U0001F5B1-\U0001F5B2"
        "\U0001F5BC\U0001F5C2-\U0001F5C4\U0001F5D1-\U0001F5D3\U0001F5DC"
        "\U0001F5DE\U0001F5E1\U0001F5E3\U0001F5E8\U0001F5EF\U0001F5F3"
        "\U0001F5FA\U0001F6CB\U0001F6CD-\U0001F6CF\U0001F6E0-\U0001F6E5"
        "\U0001F6E9\U0001F6F0\U0001F6F3\U0001F6F4-\U0001F6F6\U0001F6F7"
        "\U0001F6F8\U0001F6F9\U0001F6FA\u2600-\u27BF\u2B50\u2B55\u231A"
        "\u231B\u2328\u23CF\u23E9-\u23F3\u23F8-\u23FA\u24C2\u25AA\u25AB"
        "\u25B6\u25C0\u25FB-\u25FE\u2702\u2705\u2708-\u270D\u270F\u2712"
        "\u2714\u2716\u271D\u2721\u2728\u2733\u2734\u2744\u2747\u274C"
        "\u274E\u2753-\u2755\u2757\u2763\u2764\u2795-\u2797\u27A1\u27B0"
        "\u27BF\u2934\u2935\u2B05-\u2B07\u2B1B\u2B1C\u2B50\u2B55\u3030"
        "\u303D\u3297\u3299]|"
        r"<a?:\w+:\d+>"
        , flags=re.UNICODE
    )
    
    match = emoji_pattern.match(nome_canal)
    if match:
        return match.group(0)
    return None

def extrair_decoracao_do_nome(nome_canal):
    """Extrai a decoração do nome do canal (separador entre emoji e texto)"""
    import re
    
    emoji = extrair_emoji_do_nome(nome_canal)
    if emoji:
        nome_sem_emoji = nome_canal[len(emoji):]
    else:
        nome_sem_emoji = nome_canal
    
    decoracao_pattern = re.compile(r'^[^\w\s]{1,3}')
    match = decoracao_pattern.match(nome_sem_emoji)
    if match:
        return match.group(0)
    return None

def extrair_texto_puro(nome_canal):
    """Extrai apenas o texto do canal, removendo emoji e decoração"""
    emoji = extrair_emoji_do_nome(nome_canal)
    if emoji:
        nome_sem_emoji = nome_canal[len(emoji):]
    else:
        nome_sem_emoji = nome_canal
    
    decoracao = extrair_decoracao_do_nome(nome_canal)
    if decoracao:
        texto = nome_sem_emoji.strip()
        while texto and any(texto.startswith(d) for d in [decoracao]):
            texto = texto[len(decoracao):]
        while texto and any(texto.endswith(d) for d in [decoracao]):
            texto = texto[:-len(decoracao)]
        return texto.strip()
    
    return nome_sem_emoji.strip()

def extrair_emojis(texto):
    """Extrai emojis do texto, suportando emojis Unicode e personalizados do Discord"""
    import re
    
    custom_emoji_pattern = re.compile(r'<a?:\w+:\d+>')
    custom_emojis = custom_emoji_pattern.findall(texto)
    
    texto_sem_custom = custom_emoji_pattern.sub('', texto)
    
    todos_emojis = []
    
    for emoji in custom_emojis:
        idx = texto.find(emoji)
        if idx != -1:
            todos_emojis.append((idx, emoji))
    
    i = 0
    while i < len(texto_sem_custom):
        char = texto_sem_custom[i]
        
        if ord(char) > 127:
            emoji_inicio = i
            
            while i < len(texto_sem_custom) and (
                ord(texto_sem_custom[i]) > 127 or 
                texto_sem_custom[i] in ['\u200D', '\uFE0F', '\u20E3'] or
                (0x1F3FB <= ord(texto_sem_custom[i]) <= 0x1F3FF)
            ):
                i += 1
                if i > 0 and i-1 < len(texto_sem_custom) and texto_sem_custom[i-1] == '\u200D' and i < len(texto_sem_custom):
                    i += 1
            
            emoji_encontrado = texto_sem_custom[emoji_inicio:i]
            
            is_in_custom = False
            for custom_emoji in custom_emojis:
                custom_idx = texto.find(custom_emoji)
                if custom_idx != -1 and custom_idx <= texto.find(emoji_encontrado) < custom_idx + len(custom_emoji):
                    is_in_custom = True
                    break
            
            if not is_in_custom:
                pos_no_original = texto.find(emoji_encontrado)
                if pos_no_original != -1:
                    todos_emojis.append((pos_no_original, emoji_encontrado))
        else:
            i += 1
    
    todos_emojis.sort(key=lambda x: x[0])
    
    emojis_final = []
    posicoes_vistas = set()
    for pos, emoji in todos_emojis:
        if pos not in posicoes_vistas:
            emojis_final.append(emoji)
            posicoes_vistas.add(pos)
    
    return emojis_final

# ================ COMANDO /CRIAR ================
@bot.tree.command(name="criar", description="Cria canais com emoji e decoração (apenas ADMs)")
@app_commands.describe(
    canais="Nomes dos canais separados por vírgula (ex: games, geral, fut)",
    emoji="Emoji para colocar antes do nome (opicional)",
    decoracao="Decoração/divisor (opicional, ex: ・, ✧, |)"
)
@app_commands.default_permissions(administrator=True)
async def slash_criar(interaction: discord.Interaction, canais: str, emoji: str = None, decoracao: str = None):
    await interaction.response.defer()
    
    lista_canais = [c.strip() for c in canais.split(",") if c.strip()]
    
    if not lista_canais:
        await interaction.followup.send("❌ Você precisa informar pelo menos um nome de canal!", ephemeral=True)
        return
    
    emoji_final = None
    if emoji:
        emoji = emoji.strip()
        
        if decoracao:
            decoracao_limpa = decoracao.strip()
            if emoji.endswith(decoracao_limpa):
                emoji = emoji[:-len(decoracao_limpa)].strip()
            if emoji.startswith(decoracao_limpa):
                emoji = emoji[len(decoracao_limpa):].strip()
        
        emojis_extraidos = extrair_emojis(emoji)
        if emojis_extraidos:
            emoji_final = emojis_extraidos[0]
    
    decoracao_limpa = decoracao.strip() if decoracao else None
    
    canais_criados = []
    categoria = interaction.channel.category
    
    for nome_canal in lista_canais:
        partes_nome = []
        
        if emoji_final and decoracao_limpa:
            partes_nome.append(f"{emoji_final}{decoracao_limpa}{nome_canal}")
        elif emoji_final:
            partes_nome.append(f"{emoji_final}{nome_canal}")
        elif decoracao_limpa:
            partes_nome.append(f"{decoracao_limpa}{nome_canal}")
        else:
            partes_nome.append(nome_canal)
        
        nome_final = "".join(partes_nome)
        nome_final = nome_final.replace(" ", "-")
        
        try:
            novo_canal = await interaction.guild.create_text_channel(
                name=nome_final,
                category=categoria,
                reason=f"Criado por {interaction.user.display_name}"
            )
            canais_criados.append(novo_canal)
        except Exception as e:
            await interaction.followup.send(
                f"❌ Erro ao criar o canal `{nome_canal}`: {e}",
                ephemeral=True
            )
            return
    
    embed = discord.Embed(
        title="✅ Canais Criados com Sucesso!",
        description=f"Foram criados **{len(canais_criados)}** canal(is):",
        color=discord.Color.green()
    )
    
    for i, canal in enumerate(canais_criados):
        embed.add_field(
            name=f"Canal {i+1}",
            value=canal.mention,
            inline=False
        )
    
    embed.set_footer(text=f"Criado por {interaction.user.display_name}")
    await interaction.followup.send(embed=embed)

# ================ COMANDO /DECORAR (SLASH) ================
@bot.tree.command(name="decorar", description="Edita a decoração e emoji de canais existentes (apenas ADMs)")
@app_commands.describe(
    canal="Canal que será decorado (use 'all' para todos os canais de texto)",
    emoji="Novo emoji (opicional, substitui o atual se existir)",
    decoracao="Nova decoração (opicional, ex: ・, ✧, |)"
)
@app_commands.default_permissions(administrator=True)
async def slash_decorar(interaction: discord.Interaction, canal: str, emoji: str = None, decoracao: str = None):
    await interaction.response.defer()
    
    if not emoji and not decoracao:
        await interaction.followup.send("❌ Você precisa informar pelo menos um emoji ou uma decoração!", ephemeral=True)
        return
    
    canais_para_decorar = []
    
    if canal.lower() == "all":
        canais_para_decorar = interaction.guild.text_channels
        if not canais_para_decorar:
            await interaction.followup.send("❌ Nenhum canal de texto encontrado no servidor!", ephemeral=True)
            return
    else:
        try:
            canal_id = canal.strip().replace("<#", "").replace(">", "")
            canal_obj = interaction.guild.get_channel(int(canal_id))
            
            if not canal_obj:
                canal_obj = discord.utils.get(interaction.guild.text_channels, name=canal)
            
            if not canal_obj:
                await interaction.followup.send(f"❌ Canal `{canal}` não encontrado!", ephemeral=True)
                return
            
            canais_para_decorar = [canal_obj]
        except ValueError:
            canal_obj = discord.utils.get(interaction.guild.text_channels, name=canal)
            if not canal_obj:
                await interaction.followup.send(f"❌ Canal `{canal}` não encontrado!", ephemeral=True)
                return
            canais_para_decorar = [canal_obj]
        except Exception as e:
            await interaction.followup.send(f"❌ Erro ao buscar canal: {e}", ephemeral=True)
            return
    
    novo_emoji = None
    if emoji:
        emojis_extraidos = extrair_emojis(emoji)
        if emojis_extraidos:
            novo_emoji = emojis_extraidos[0]
        else:
            await interaction.followup.send("❌ Nenhum emoji válido encontrado!", ephemeral=True)
            return
    
    canais_modificados = []
    canais_com_erro = []
    
    for canal_obj in canais_para_decorar:
        try:
            nome_atual = canal_obj.name
            texto_puro = extrair_texto_puro(nome_atual)
            emoji_canal = novo_emoji if novo_emoji else extrair_emoji_do_nome(nome_atual)
            decoracao_canal = decoracao if decoracao else extrair_decoracao_do_nome(nome_atual)
            
            partes_nome = []
            if emoji_canal:
                partes_nome.append(emoji_canal)
            if decoracao_canal:
                partes_nome.append(f"{decoracao_canal}{texto_puro}{decoracao_canal}")
            else:
                partes_nome.append(texto_puro)
            
            novo_nome = "".join(partes_nome)
            
            if len(novo_nome) < 1 or len(novo_nome) > 100:
                canais_com_erro.append(f"{canal_obj.mention} (nome muito longo/curto)")
                continue
            
            if novo_nome != nome_atual:
                await canal_obj.edit(name=novo_nome, reason=f"Decorado por {interaction.user.display_name}")
                canais_modificados.append((canal_obj, nome_atual, novo_nome))
            
        except Exception as e:
            canais_com_erro.append(f"{canal_obj.mention}: {e}")
    
    if not canais_modificados and not canais_com_erro:
        await interaction.followup.send("ℹ️ Nenhum canal precisou ser modificado.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="✅ Canais Decorados!",
        color=discord.Color.green()
    )
    
    if canais_modificados:
        if len(canais_modificados) <= 10:
            for canal_obj, nome_antigo, nome_novo in canais_modificados:
                embed.add_field(
                    name=canal_obj.mention,
                    value=f"`{nome_antigo}` → `{nome_novo}`",
                    inline=False
                )
        else:
            embed.description = f"**{len(canais_modificados)}** canais foram modificados com sucesso!"
            embed.add_field(
                name="Exemplos:",
                value="\n".join([f"{c.mention}: `{a}` → `{n}`" for c, a, n in canais_modificados[:5]]),
                inline=False
            )
            if len(canais_modificados) > 5:
                embed.add_field(
                    name="...",
                    value=f"e mais {len(canais_modificados) - 5} canais",
                    inline=False
                )
    
    if canais_com_erro:
        embed.add_field(
            name="❌ Erros:",
            value="\n".join(canais_com_erro[:5]),
            inline=False
        )
    
    if novo_emoji:
        embed.add_field(name="Emoji aplicado", value=novo_emoji, inline=True)
    if decoracao:
        embed.add_field(name="Decoração aplicada", value=decoracao, inline=True)
    
    embed.set_footer(text=f"Decorado por {interaction.user.display_name}")
    await interaction.followup.send(embed=embed)

# ================ COMANDO /DECORAR (PREFIXO) ================
@bot.command(name='decorar')
@commands.has_permissions(administrator=True)
async def prefix_decorar(ctx, canal_str: str = None, *, args: str = None):
    if not canal_str:
        return await ctx.send("❌ Use: `/decorar <#canal ou all> [emoji] [decoração]`")
    
    if not args:
        return await ctx.send("❌ Informe pelo menos um emoji ou decoração!")
    
    partes = args.split()
    emoji_str = partes[0] if len(partes) > 0 else None
    decoracao = partes[1] if len(partes) > 1 else None
    
    canais_para_decorar = []
    
    if canal_str.lower() == "all":
        canais_para_decorar = ctx.guild.text_channels
        if not canais_para_decorar:
            return await ctx.send("❌ Nenhum canal de texto encontrado!")
    else:
        try:
            canal_id = canal_str.strip().replace("<#", "").replace(">", "")
            canal_obj = ctx.guild.get_channel(int(canal_id))
            
            if not canal_obj:
                canal_obj = discord.utils.get(ctx.guild.text_channels, name=canal_str)
            
            if not canal_obj:
                return await ctx.send(f"❌ Canal `{canal_str}` não encontrado!")
            
            canais_para_decorar = [canal_obj]
        except ValueError:
            canal_obj = discord.utils.get(ctx.guild.text_channels, name=canal_str)
            if not canal_obj:
                return await ctx.send(f"❌ Canal `{canal_str}` não encontrado!")
            canais_para_decorar = [canal_obj]
    
    novo_emoji = None
    if emoji_str:
        emojis_extraidos = extrair_emojis(emoji_str)
        if emojis_extraidos:
            novo_emoji = emojis_extraidos[0]
        else:
            return await ctx.send("❌ Emoji inválido!")
    
    canais_modificados = []
    canais_com_erro = []
    
    for canal_obj in canais_para_decorar:
        try:
            nome_atual = canal_obj.name
            texto_puro = extrair_texto_puro(nome_atual)
            emoji_canal = novo_emoji if novo_emoji else extrair_emoji_do_nome(nome_atual)
            decoracao_canal = decoracao if decoracao else extrair_decoracao_do_nome(nome_atual)
            
            partes_nome = []
            if emoji_canal:
                partes_nome.append(emoji_canal)
            if decoracao_canal:
                partes_nome.append(f"{decoracao_canal}{texto_puro}{decoracao_canal}")
            else:
                partes_nome.append(texto_puro)
            
            novo_nome = "".join(partes_nome)
            
            if len(novo_nome) < 1 or len(novo_nome) > 100:
                canais_com_erro.append(f"{canal_obj.mention} (nome inválido)")
                continue
            
            if novo_nome != nome_atual:
                await canal_obj.edit(name=novo_nome, reason=f"Decorado por {ctx.author.display_name}")
                canais_modificados.append((canal_obj, nome_atual, novo_nome))
            
        except Exception as e:
            canais_com_erro.append(f"{canal_obj.mention}: {e}")
    
    if not canais_modificados and not canais_com_erro:
        return await ctx.send("ℹ️ Nenhum canal precisou ser modificado.")
    
    embed = discord.Embed(
        title="✅ Canais Decorados!",
        color=discord.Color.green()
    )
    
    if canais_modificados:
        if len(canais_modificados) <= 10:
            for canal_obj, nome_antigo, nome_novo in canais_modificados:
                embed.add_field(
                    name=canal_obj.mention,
                    value=f"`{nome_antigo}` → `{nome_novo}`",
                    inline=False
                )
        else:
            embed.description = f"**{len(canais_modificados)}** canais modificados!"
            embed.add_field(
                name="Exemplos:",
                value="\n".join([f"{c.mention}: `{a}` → `{n}`" for c, a, n in canais_modificados[:5]]),
                inline=False
            )
            if len(canais_modificados) > 5:
                embed.add_field(
                    name="...",
                    value=f"e mais {len(canais_modificados) - 5} canais",
                    inline=False
                )
    
    if canais_com_erro:
        embed.add_field(
            name="❌ Erros:",
            value="\n".join(canais_com_erro[:5]),
            inline=False
        )
    
    if novo_emoji:
        embed.add_field(name="Emoji", value=novo_emoji, inline=True)
    if decoracao:
        embed.add_field(name="Decoração", value=decoracao, inline=True)
    
    embed.set_footer(text=f"Decorado por {ctx.author.display_name}")
    await ctx.send(embed=embed)

@bot.tree.command(name="sincronizar", description="Sincroniza os comandos slash (apenas ADM)")
@app_commands.default_permissions(administrator=True)
async def slash_sincronizar(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        synced = await bot.tree.sync()
        await interaction.followup.send(f"✅ Sincronizado! {len(synced)} comandos atualizados.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Erro ao sincronizar: {e}", ephemeral=True)

# ================ VERSÕES COM PREFIXO ================
@bot.command(name='criar')
@commands.has_permissions(administrator=True)
async def prefix_criar(ctx, *, args: str = None):
    if not args:
        return await ctx.send("❌ Use: `/criar nome1,nome2 [emoji] [decoração]`")
    
    partes = args.split()
    
    if ',' in partes[0]:
        canais = partes[0]
        resto = partes[1:] if len(partes) > 1 else []
    else:
        canais = partes[0]
        resto = partes[1:] if len(partes) > 1 else []
    
    emoji_str = resto[0] if len(resto) > 0 else None
    decoracao = resto[1] if len(resto) > 1 else None
    
    lista_canais = [c.strip() for c in canais.split(",") if c.strip()]
    
    if not lista_canais:
        return await ctx.send("❌ Informe pelo menos um nome de canal!")
    
    emoji_final = None
    if emoji_str:
        emoji_str = emoji_str.strip()
        if decoracao:
            decoracao_limpa = decoracao.strip()
            if emoji_str.endswith(decoracao_limpa):
                emoji_str = emoji_str[:-len(decoracao_limpa)].strip()
            if emoji_str.startswith(decoracao_limpa):
                emoji_str = emoji_str[len(decoracao_limpa):].strip()
        
        emojis_extraidos = extrair_emojis(emoji_str)
        if emojis_extraidos:
            emoji_final = emojis_extraidos[0]
    
    decoracao_limpa = decoracao.strip() if decoracao else None
    
    canais_criados = []
    categoria = ctx.channel.category
    
    for nome_canal in lista_canais:
        partes_nome = []
        
        if emoji_final and decoracao_limpa:
            partes_nome.append(f"{emoji_final}{decoracao_limpa}{nome_canal}")
        elif emoji_final:
            partes_nome.append(f"{emoji_final}{nome_canal}")
        elif decoracao_limpa:
            partes_nome.append(f"{decoracao_limpa}{nome_canal}")
        else:
            partes_nome.append(nome_canal)
        
        nome_final = "".join(partes_nome).replace(" ", "-")
        
        try:
            novo_canal = await ctx.guild.create_text_channel(
                name=nome_final,
                category=categoria,
                reason=f"Criado por {ctx.author.display_name}"
            )
            canais_criados.append(novo_canal)
        except Exception as e:
            return await ctx.send(f"❌ Erro ao criar `{nome_canal}`: {e}")
    
    embed = discord.Embed(
        title="✅ Canais Criados!",
        description=f"Criados **{len(canais_criados)}** canais:",
        color=discord.Color.green()
    )
    
    for canal in canais_criados:
        embed.add_field(name="Canal", value=canal.mention, inline=False)
    
    embed.set_footer(text=f"Criado por {ctx.author.display_name}")
    await ctx.send(embed=embed)

# ================ PPT COM BOTÕES ================
class PPTView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.finished = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Só quem iniciou o jogo pode jogar!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="🪨 Pedra", style=discord.ButtonStyle.gray)
    async def pedra(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.processar(interaction, "pedra")

    @discord.ui.button(label="📄 Papel", style=discord.ButtonStyle.gray)
    async def papel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.processar(interaction, "papel")

    @discord.ui.button(label="✂️ Tesoura", style=discord.ButtonStyle.gray)
    async def tesoura(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.processar(interaction, "tesoura")

    async def processar(self, interaction: discord.Interaction, escolha: str):
        if self.finished:
            await interaction.response.send_message("Jogo já finalizado! Use /ppt para jogar novamente.", ephemeral=True)
            return
        
        self.finished = True
        for child in self.children:
            child.disabled = True
        
        opcoes = ["pedra", "papel", "tesoura"]
        emojis = {"pedra": "🪨", "papel": "📄", "tesoura": "✂️"}
        bot_escolha = random.choice(opcoes)
        
        if escolha == bot_escolha:
            resultado = "🤝 **Empate!**"
            cor = discord.Color.greyple()
        elif (escolha == "pedra" and bot_escolha == "tesoura") or \
             (escolha == "papel" and bot_escolha == "pedra") or \
             (escolha == "tesoura" and bot_escolha == "papel"):
            resultado = "🎉 **Você ganhou!**"
            cor = discord.Color.green()
        else:
            resultado = "😢 **Você perdeu!**"
            cor = discord.Color.red()
        
        embed = discord.Embed(title="🪨 Pedra | 📄 Papel | ✂️ Tesoura", color=cor)
        embed.add_field(name="Você escolheu", value=f"{emojis[escolha]} {escolha.capitalize()}", inline=True)
        embed.add_field(name="Bot escolheu", value=f"{emojis[bot_escolha]} {bot_escolha.capitalize()}", inline=True)
        embed.add_field(name="Resultado", value=resultado, inline=False)
        embed.set_footer(text="Jogo finalizado! Use /ppt para jogar novamente.")
        
        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="ppt", description="🪨📄✂️ Joga Pedra, Papel e Tesoura contra o bot")
async def slash_ppt(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🪨📄✂️ Pedra, Papel e Tesoura",
        description="Clique em um dos botões abaixo para jogar!",
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Jogador: {interaction.user.display_name}")
    
    view = PPTView(interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view)

# ================ FORCA ================
jogos_forca = {}

@bot.tree.command(name="forca", description="🪢 Jogo da forca - adivinhe a palavra!")
async def slash_forca(interaction: discord.Interaction):
    palavras = [
        "python", "discord", "bot", "servidor", "comando",
        "jogador", "campeao", "teclado", "monitor", "programa",
        "internet", "codigo", "variavel", "funcao", "string",
        "numero", "lista", "dicionario", "loop", "condicao",
        "banana", "abacaxi", "morango", "laranja", "uva",
        "guitarra", "bateria", "violino", "piano", "flauta",
        "brasil", "argentina", "canada", "japao", "franca",
        "futebol", "basquete", "tenis", "natacao", "volei"
    ]
    
    user_id = interaction.user.id
    
    if user_id in jogos_forca:
        await interaction.response.send_message(
            "❌ Você já tem um jogo em andamento! Use `/tentar` para continuar ou `/desistir` para sair.",
            ephemeral=True
        )
        return
    
    palavra = random.choice(palavras)
    jogos_forca[user_id] = {
        "palavra": palavra,
        "tentadas": [],
        "erros": 0,
        "max_erros": 6
    }
    
    palavra_escondida = " ".join(["_" for _ in palavra])
    
    embed = discord.Embed(
        title="🪢 Jogo da Forca",
        description=f"**Palavra:** {palavra_escondida}\n**Letras tentadas:** Nenhuma\n**Erros:** 0/6",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="Como jogar",
        value="Use `/tentar <letra>` para chutar uma letra\nUse `/desistir` para sair do jogo",
        inline=False
    )
    embed.add_field(name="Forca", value=desenhar_forca(0), inline=False)
    embed.set_footer(text=f"Jogador: {interaction.user.display_name}")
    
    await interaction.response.send_message(embed=embed)

def desenhar_forca(erros):
    estagios = [
        "```\n  +---+\n  |   |\n      |\n      |\n      |\n      |\n=========\n```",
        "```\n  +---+\n  |   |\n  O   |\n      |\n      |\n      |\n=========\n```",
        "```\n  +---+\n  |   |\n  O   |\n  |   |\n      |\n      |\n=========\n```",
        "```\n  +---+\n  |   |\n  O   |\n /|   |\n      |\n      |\n=========\n```",
        "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n      |\n      |\n=========\n```",
        "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n /    |\n      |\n=========\n```",
        "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n / \\  |\n      |\n=========\n```"
    ]
    return estagios[min(erros, 6)]

@bot.tree.command(name="tentar", description="Tenta uma letra no jogo da forca")
@app_commands.describe(letra="Letra que você quer tentar")
async def slash_tentar(interaction: discord.Interaction, letra: str):
    user_id = interaction.user.id
    
    if user_id not in jogos_forca:
        await interaction.response.send_message(
            "❌ Você não tem um jogo em andamento! Use `/forca` para começar.",
            ephemeral=True
        )
        return
    
    letra = letra.lower().strip()
    
    if len(letra) != 1 or not letra.isalpha():
        await interaction.response.send_message("❌ Digite apenas **uma letra**!", ephemeral=True)
        return
    
    jogo = jogos_forca[user_id]
    
    if letra in jogo["tentadas"]:
        await interaction.response.send_message(f"⚠️ Você já tentou a letra **{letra}**!", ephemeral=True)
        return
    
    jogo["tentadas"].append(letra)
    
    if letra not in jogo["palavra"]:
        jogo["erros"] += 1
    
    palavra_escondida = " ".join([l if l in jogo["tentadas"] else "_" for l in jogo["palavra"]])
    letras_tentadas = ", ".join(sorted(jogo["tentadas"]))
    
    if "_" not in palavra_escondida:
        embed = discord.Embed(
            title="🎉 **VOCÊ GANHOU!**",
            description=f"A palavra era: **{jogo['palavra'].upper()}**",
            color=discord.Color.green()
        )
        embed.add_field(name="Erros", value=f"{jogo['erros']}/6", inline=True)
        embed.add_field(name="Tentativas", value=letras_tentadas, inline=False)
        embed.set_footer(text=f"Jogador: {interaction.user.display_name}")
        del jogos_forca[user_id]
        await interaction.response.send_message(embed=embed)
        return
    
    if jogo["erros"] >= jogo["max_erros"]:
        embed = discord.Embed(
            title="💀 **VOCÊ PERDEU!**",
            description=f"A palavra era: **{jogo['palavra'].upper()}**",
            color=discord.Color.red()
        )
        embed.add_field(name="Forca", value=desenhar_forca(6), inline=False)
        embed.set_footer(text=f"Jogador: {interaction.user.display_name}")
        del jogos_forca[user_id]
        await interaction.response.send_message(embed=embed)
        return
    
    if letra in jogo["palavra"]:
        mensagem = f"✅ Boa! A letra **{letra}** está na palavra!"
    else:
        mensagem = f"❌ A letra **{letra}** não está na palavra!"
    
    embed = discord.Embed(
        title="🪢 Jogo da Forca",
        description=f"{mensagem}\n\n**Palavra:** {palavra_escondida}\n**Letras tentadas:** {letras_tentadas}\n**Erros:** {jogo['erros']}/6",
        color=discord.Color.blue() if jogo["erros"] < 4 else discord.Color.orange() if jogo["erros"] < 6 else discord.Color.red()
    )
    embed.add_field(name="Forca", value=desenhar_forca(jogo["erros"]), inline=False)
    embed.set_footer(text=f"Jogador: {interaction.user.display_name}")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="desistir", description="Desiste do jogo da forca atual")
async def slash_desistir(interaction: discord.Interaction):
    user_id = interaction.user.id
    
    if user_id not in jogos_forca:
        await interaction.response.send_message("❌ Você não tem um jogo em andamento!", ephemeral=True)
        return
    
    palavra = jogos_forca[user_id]["palavra"]
    del jogos_forca[user_id]
    
    embed = discord.Embed(
        title="🏳️ Você desistiu!",
        description=f"A palavra era: **{palavra.upper()}**",
        color=discord.Color.light_grey()
    )
    await interaction.response.send_message(embed=embed)

# ================ CARA OU COROA COM BOTÕES ================
class CaraCoroaView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.finished = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Só quem iniciou o jogo pode jogar!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="👤 Cara", style=discord.ButtonStyle.gray)
    async def cara(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.processar(interaction, "cara")

    @discord.ui.button(label="🦅 Coroa", style=discord.ButtonStyle.gray)
    async def coroa(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.processar(interaction, "coroa")

    @discord.ui.button(label="🎲 Só Girar", style=discord.ButtonStyle.blurple)
    async def girar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.processar(interaction, None)

    async def processar(self, interaction: discord.Interaction, escolha: str):
        if self.finished:
            await interaction.response.send_message("Jogo já finalizado! Use /caracoroa para jogar novamente.", ephemeral=True)
            return
        
        self.finished = True
        for child in self.children:
            child.disabled = True
        
        resultado = random.choice(["cara", "coroa"])
        emoji_resultado = "👤" if resultado == "cara" else "🦅"
        
        if escolha:
            if escolha == resultado:
                mensagem = f"🎉 **Você acertou!** Deu **{emoji_resultado} {resultado.upper()}**!"
                cor = discord.Color.green()
            else:
                mensagem = f"😢 **Você errou!** Deu **{emoji_resultado} {resultado.upper()}**!"
                cor = discord.Color.red()
        else:
            mensagem = f"🪙 Deu **{emoji_resultado} {resultado.upper()}**!"
            cor = discord.Color.gold()
        
        embed = discord.Embed(title="🪙 Cara ou Coroa", description=mensagem, color=cor)
        if escolha:
            embed.add_field(name="Sua aposta", value=f"{'👤' if escolha == 'cara' else '🦅'} {escolha.upper()}", inline=True)
            embed.add_field(name="Resultado", value=f"{emoji_resultado} {resultado.upper()}", inline=True)
        embed.set_footer(text="Jogo finalizado! Use /caracoroa para jogar novamente.")
        
        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="caracoroa", description="🪙 Joga Cara ou Coroa")
async def slash_caracoroa(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🪙 Cara ou Coroa",
        description="Escolha uma opção ou só gire a moeda!",
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Jogador: {interaction.user.display_name}")
    
    view = CaraCoroaView(interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view)

# ================ DADO ================
@bot.tree.command(name="dado", description="🎲 Rola um dado com o número de lados que você escolher")
@app_commands.describe(lados="Número de lados do dado (padrão: 6)")
async def slash_dado(interaction: discord.Interaction, lados: int = 6):
    if lados < 2:
        await interaction.response.send_message("❌ O dado precisa ter pelo menos 2 lados!", ephemeral=True)
        return
    if lados > 1000:
        await interaction.response.send_message("❌ Máximo de 1000 lados!", ephemeral=True)
        return
    
    resultado = random.randint(1, lados)
    
    dados_especiais = {6: "🎲", 20: "🎯", 10: "🔟", 100: "💯"}
    emoji_dado = dados_especiais.get(lados, "🎲")
    
    embed = discord.Embed(
        title=f"{emoji_dado} D{lados}",
        description=f"## {resultado}",
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Rolado por {interaction.user.display_name} | 1-{lados}")
    
    await interaction.response.send_message(embed=embed)

# ================ SLOT ================
@bot.tree.command(name="slot", description="🎰 Joga na máquina caça-níquel")
async def slash_slot(interaction: discord.Interaction):
    emojis_slot = ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣", "🌟", "🔔"]
    
    col1 = random.choice(emojis_slot)
    col2 = random.choice(emojis_slot)
    col3 = random.choice(emojis_slot)
    
    resultado = f"{col1} | {col2} | {col3}"
    
    if col1 == col2 == col3:
        if col1 == "7️⃣":
            mensagem = "🎰 **JACKPOT!!!** 3x 7️⃣! Que sorte incrível!"
            cor = discord.Color.gold()
        elif col1 == "💎":
            mensagem = "💎 **Diamantes!** Que luxo!"
            cor = discord.Color.blue()
        else:
            mensagem = f"🎉 **TRÊS IGUAIS!** Muito bem!"
            cor = discord.Color.green()
    elif col1 == col2 or col2 == col3 or col1 == col3:
        if "7️⃣" in [col1, col2, col3] or "💎" in [col1, col2, col3]:
            mensagem = "👍 **Dupla com símbolo raro!** Quase lá!"
            cor = discord.Color.orange()
        else:
            mensagem = "👍 **Dois iguais!** Passou perto!"
            cor = discord.Color.orange()
    else:
        mensagem = "😢 **Nada dessa vez...** Tente novamente!"
        cor = discord.Color.red()
    
    embed = discord.Embed(
        title="🎰 Caça-Níquel",
        description=f"# {resultado}\n{mensagem}",
        color=cor
    )
    embed.set_footer(text=f"Jogado por {interaction.user.display_name}")
    
    await interaction.response.send_message(embed=embed)

# ================ PALAVRA EMBARALHADA COM BOTÕES ================
jogos_embaralhar = {}

class PalavraButtonView(discord.ui.View):
    def __init__(self, author_id, jogos_embaralhar_ref, user_id):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.jogos_ref = jogos_embaralhar_ref
        self.user_id = user_id
        self._criar_teclado()

    def _criar_teclado(self):
        linhas = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]
        for linha_idx, linha_texto in enumerate(linhas):
            for letra in linha_texto:
                btn = discord.ui.Button(label=letra, style=discord.ButtonStyle.gray, row=linha_idx)
                btn.callback = self.make_callback(letra)
                self.add_item(btn)

    def make_callback(self, letra):
        async def callback(interaction: discord.Interaction):
            await self.processar_letra(interaction, letra.lower())
        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Só quem iniciou pode jogar!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.user_id in self.jogos_ref:
            del self.jogos_ref[self.user_id]
        for child in self.children:
            child.disabled = True

    async def processar_letra(self, interaction: discord.Interaction, letra: str):
        jogo = self.jogos_ref.get(self.user_id)
        if not jogo:
            await interaction.response.send_message("Jogo não encontrado!", ephemeral=True)
            return
        
        if letra in jogo["tentadas"]:
            await interaction.response.send_message(f"⚠️ Você já tentou **{letra}**!", ephemeral=True)
            return
        
        jogo["tentadas"].append(letra)
        if letra not in jogo["palavra"]:
            jogo["erros"] += 1
        
        palavra_escondida = " ".join([l if l in jogo["tentadas"] else "_" for l in jogo["palavra"]])
        letras_tentadas = ", ".join(sorted(jogo["tentadas"]))
        
        if "_" not in palavra_escondida:
            embed = discord.Embed(
                title="🎉 **VOCÊ ACERTOU!**",
                description=f"**Palavra:** `{jogo['embaralhada']}`\n\n**Resposta:** **{jogo['palavra'].upper()}**\nTentativas: **{len(jogo['tentadas'])}**",
                color=discord.Color.green()
            )
            for child in self.children:
                child.disabled = True
            del self.jogos_ref[self.user_id]
            await interaction.response.edit_message(embed=embed, view=self)
            return
        
        if jogo["erros"] >= 5:
            embed = discord.Embed(
                title="😢 **VOCÊ PERDEU!**",
                description=f"**Palavra:** `{jogo['embaralhada']}`\n\n**Resposta:** **{jogo['palavra'].upper()}**\nTentativas: {len(jogo['tentadas'])}",
                color=discord.Color.red()
            )
            for child in self.children:
                child.disabled = True
            del self.jogos_ref[self.user_id]
            await interaction.response.edit_message(embed=embed, view=self)
            return
        
        if letra in jogo["palavra"]:
            msg_letra = f"✅ **{letra.upper()}** está na palavra!"
        else:
            msg_letra = f"❌ **{letra.upper()}** não está na palavra!"
        
        cor = discord.Color.blue() if jogo["erros"] < 3 else discord.Color.orange() if jogo["erros"] < 5 else discord.Color.red()
        embed = discord.Embed(
            title="📝 Palavra Embaralhada",
            description=f"**Palavra:** `{jogo['embaralhada']}`\n\n"
                        f"{msg_letra}\n\n"
                        f"`{palavra_escondida}`\n\n"
                        f"📏 **{len(jogo['palavra'])} letras**\n"
                        f"Letras tentadas: {letras_tentadas}\n"
                        f"Erros: **{jogo['erros']}/5**",
            color=cor
        )
        embed.set_footer(text=f"Jogador: {interaction.user.display_name}")
        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="embaralhar", description="📝 Adivinhe a palavra embaralhada!")
async def slash_embaralhar(interaction: discord.Interaction):
    palavras = [
        "amor", "paz", "luz", "sol", "ceu", "mar", "flor", "vida",
        "casa", "rato", "gato", "bola", "jogo", "fogo", "ouro",
        "porta", "mesa", "livro", "tempo", "noite", "agua", "feliz",
        "amizade", "cachorro", "guitarra", "abacaxi", "morango",
        "estrela", "dinheiro", "coragem", "fantasma", "girassol",
        "tesouro", "vampiro", "zumbi", "quebra", "floresta",
        "biblioteca", "tecnologia", "borboleta", "criatividade",
        "inteligente", "maravilhoso", "paralelepipedo"
    ]
    
    user_id = interaction.user.id
    
    if user_id in jogos_embaralhar:
        await interaction.response.send_message("❌ Você já tem um jogo em andamento!", ephemeral=True)
        return
    
    palavra = random.choice(palavras)
    letras = list(palavra)
    random.shuffle(letras)
    embaralhada = "".join(letras)
    while embaralhada == palavra:
        random.shuffle(letras)
        embaralhada = "".join(letras)
    
    jogos_embaralhar[user_id] = {
        "palavra": palavra,
        "embaralhada": embaralhada,
        "tentadas": [],
        "erros": 0
    }
    
    dica = "🟢 Fácil" if len(palavra) <= 5 else "🟡 Médio" if len(palavra) <= 7 else "🔴 Difícil"
    
    embed = discord.Embed(
        title="📝 Palavra Embaralhada",
        description=f"**Palavra:** `{embaralhada}`\n\n📏 **{len(palavra)} letras** | {dica}\n\n"
                    f"Clique nas letras abaixo para tentar!",
        color=discord.Color.purple()
    )
    embed.set_footer(text=f"Jogador: {interaction.user.display_name}")
    
    view = PalavraButtonView(interaction.user.id, jogos_embaralhar, user_id)
    await interaction.response.send_message(embed=embed, view=view)

# ================ JOGO DA VELHA COM BOTÕES ================
jogos_velha = {}

class VelhaView(discord.ui.View):
    def __init__(self, jogo_id, jogos_velha_ref):
        super().__init__(timeout=120)
        self.jogo_id = jogo_id
        self.jogos_velha_ref = jogos_velha_ref

    async def on_timeout(self):
        if self.jogo_id in self.jogos_velha_ref:
            del self.jogos_velha_ref[self.jogo_id]
        for child in self.children:
            child.disabled = True

    def get_jogo(self):
        return self.jogos_velha_ref.get(self.jogo_id)

    async def fazer_jogada(self, interaction: discord.Interaction, pos: int):
        jogo = self.get_jogo()
        if not jogo:
            await interaction.response.send_message("❌ Jogo não encontrado!", ephemeral=True)
            return
        
        if interaction.user.id != jogo["vez"]:
            await interaction.response.send_message("❌ Não é sua vez!", ephemeral=True)
            return
        
        if jogo["tabuleiro"][pos] in ["❌", "⭕"]:
            await interaction.response.send_message("❌ Essa posição já está ocupada!", ephemeral=True)
            return
        
        simbolo = jogo["simbolo_atual"]
        jogo["tabuleiro"][pos] = simbolo
        tab = jogo["tabuleiro"]
        
        combinacoes = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
        vitoria = any(tab[c[0]] == tab[c[1]] == tab[c[2]] == simbolo for c in combinacoes)
        
        if vitoria:
            guild = interaction.guild
            jogador_x = guild.get_member(jogo["jogador_x"])
            jogador_o = guild.get_member(jogo["jogador_o"])
            
            embed = discord.Embed(
                title="🎉 **TEMOS UM VENCEDOR!**",
                description=f"{'❌' if jogador_x else ''} **{jogador_x.display_name if jogador_x else 'Jogador X'}** VS "
                            f"{'⭕' if jogador_o else ''} **{jogador_o.display_name if jogador_o else 'Jogador O'}**\n\n"
                            f"{tab[0]} {tab[1]} {tab[2]}\n"
                            f"{tab[3]} {tab[4]} {tab[5]}\n"
                            f"{tab[6]} {tab[7]} {tab[8]}\n\n"
                            f"🏆 **{interaction.user.mention} venceu!**",
                color=discord.Color.green()
            )
            embed.set_footer(text="🏆 Jogo finalizado!")
            
            for child in self.children:
                child.disabled = True
            del self.jogos_velha_ref[self.jogo_id]
            await interaction.response.edit_message(embed=embed, view=self)
            return
        
        if all(p in ["❌", "⭕"] for p in tab):
            embed = discord.Embed(
                title="🤝 **EMPATE!**",
                description=f"{tab[0]} {tab[1]} {tab[2]}\n{tab[3]} {tab[4]} {tab[5]}\n{tab[6]} {tab[7]} {tab[8]}\n\nDeu velha!",
                color=discord.Color.orange()
            )
            for child in self.children:
                child.disabled = True
            del self.jogos_velha_ref[self.jogo_id]
            await interaction.response.edit_message(embed=embed, view=self)
            return
        
        if jogo["vez"] == jogo["jogador_x"]:
            jogo["vez"] = jogo["jogador_o"]
            jogo["simbolo_atual"] = "⭕"
        else:
            jogo["vez"] = jogo["jogador_x"]
            jogo["simbolo_atual"] = "❌"
        
        guild = interaction.guild
        proximo = guild.get_member(jogo["vez"])
        turno_emoji = jogo["simbolo_atual"]
        
        embed = discord.Embed(
            title="⭕❌ Jogo da Velha",
            description=f"Vez de: {proximo.mention if proximo else 'Alguém'} {turno_emoji}\n\n"
                        f"{tab[0]} {tab[1]} {tab[2]}\n"
                        f"{tab[3]} {tab[4]} {tab[5]}\n"
                        f"{tab[6]} {tab[7]} {tab[8]}",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"{interaction.user.display_name} jogou na posição {pos+1}")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="1️⃣", style=discord.ButtonStyle.gray, row=0)
    async def b1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.fazer_jogada(interaction, 0)
    @discord.ui.button(label="2️⃣", style=discord.ButtonStyle.gray, row=0)
    async def b2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.fazer_jogada(interaction, 1)
    @discord.ui.button(label="3️⃣", style=discord.ButtonStyle.gray, row=0)
    async def b3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.fazer_jogada(interaction, 2)
    @discord.ui.button(label="4️⃣", style=discord.ButtonStyle.gray, row=1)
    async def b4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.fazer_jogada(interaction, 3)
    @discord.ui.button(label="5️⃣", style=discord.ButtonStyle.gray, row=1)
    async def b5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.fazer_jogada(interaction, 4)
    @discord.ui.button(label="6️⃣", style=discord.ButtonStyle.gray, row=1)
    async def b6(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.fazer_jogada(interaction, 5)
    @discord.ui.button(label="7️⃣", style=discord.ButtonStyle.gray, row=2)
    async def b7(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.fazer_jogada(interaction, 6)
    @discord.ui.button(label="8️⃣", style=discord.ButtonStyle.gray, row=2)
    async def b8(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.fazer_jogada(interaction, 7)
    @discord.ui.button(label="9️⃣", style=discord.ButtonStyle.gray, row=2)
    async def b9(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.fazer_jogada(interaction, 8)
    
    @discord.ui.button(label="🏳️ Desistir", style=discord.ButtonStyle.red, row=3)
    async def desistir(self, interaction: discord.Interaction, button: discord.ui.Button):
        jogo = self.get_jogo()
        if not jogo:
            await interaction.response.send_message("Jogo não encontrado!", ephemeral=True)
            return
        
        if interaction.user.id not in jogo["jogadores"]:
            await interaction.response.send_message("Você não está neste jogo!", ephemeral=True)
            return
        
        guild = interaction.guild
        adversario_id = jogo["jogador_o"] if interaction.user.id == jogo["jogador_x"] else jogo["jogador_x"]
        adversario = guild.get_member(adversario_id)
        
        embed = discord.Embed(
            title="🏳️ Jogador desistiu!",
            description=f"{interaction.user.mention} desistiu!\n🏆 **{adversario.mention if adversario else 'Adversário'} venceu por W.O.!**",
            color=discord.Color.orange()
        )
        for child in self.children:
            child.disabled = True
        del self.jogos_velha_ref[self.jogo_id]
        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="velha", description="⭕❌ Jogo da velha contra outro membro")
@app_commands.describe(adversario="Quem vai jogar contra você")
async def slash_velha(interaction: discord.Interaction, adversario: discord.Member):
    if adversario.bot:
        await interaction.response.send_message("❌ Você não pode jogar contra bots!", ephemeral=True)
        return
    if adversario == interaction.user:
        await interaction.response.send_message("❌ Você não pode jogar contra si mesmo!", ephemeral=True)
        return
    
    for key, jogo in jogos_velha.items():
        if interaction.user.id in jogo["jogadores"] or adversario.id in jogo["jogadores"]:
            await interaction.response.send_message("❌ Um dos jogadores já está em um jogo!", ephemeral=True)
            return
    
    jogo_id = f"{interaction.user.id}_{adversario.id}"
    jogos_velha[jogo_id] = {
        "tabuleiro": ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"],
        "jogador_x": interaction.user.id,
        "jogador_o": adversario.id,
        "vez": interaction.user.id,
        "simbolo_atual": "❌",
        "jogadores": [interaction.user.id, adversario.id]
    }
    
    tab = jogos_velha[jogo_id]["tabuleiro"]
    embed = discord.Embed(
        title="⭕❌ Jogo da Velha",
        description=f"**{interaction.user.display_name}** ❌ VS **{adversario.display_name}** ⭕\n\n"
                    f"Vez de: {interaction.user.mention} ❌\n\n"
                    f"{tab[0]} {tab[1]} {tab[2]}\n"
                    f"{tab[3]} {tab[4]} {tab[5]}\n"
                    f"{tab[6]} {tab[7]} {tab[8]}",
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Jogo: {interaction.user.display_name} vs {adversario.display_name}")
    
    view = VelhaView(jogo_id, jogos_velha)
    await interaction.response.send_message(embed=embed, view=view)

# ================ MODERAÇÃO ================
@bot.tree.command(name="unban", description="Desbane um usuário pelo nome ou nome#tag")
@app_commands.describe(usuario="Nome do usuário banido")
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
        await interaction.response.send_message("Canal destravado.")
    except Exception as e:
        await interaction.response.send_message(f"Erro ao destravar canal: {e}", ephemeral=True)

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

# ================ XP/RANK ================
@bot.tree.command(name="xp", description="Mostra o perfil e progresso de XP de um usuário")
@app_commands.describe(membro="Usuário (deixe em branco para ver o seu)")
async def slash_xp(interaction: discord.Interaction, membro: discord.Member = None):
    await interaction.response.defer()
    if membro is None:
        membro = interaction.user
    total_mensagens = await get_count(interaction.guild.id, membro.id)
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
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="rank", description="Exibe o top 5 usuários com mais XP do servidor")
async def slash_rank(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        rows = await get_top_users(interaction.guild.id, 5)
        if not rows:
            await interaction.followup.send("Nenhum dado de XP registrado ainda!", ephemeral=True)
            return
        embed = discord.Embed(title="Ranking - Top 5", description="Os membros com mais XP do servidor", color=discord.Color.gold())
        posicoes = {0: "1.", 1: "2.", 2: "3.", 3: "4.", 4: "5."}
        count = 0
        for i, row in enumerate(rows):
            user_id = row['user_id']
            total_mensagens = row['count']
            xp = get_xp(total_mensagens)
            nivel = get_level(xp)
            member = interaction.guild.get_member(user_id)
            if member is None:
                continue
            count += 1
            embed.add_field(
                name=f"{posicoes[i]} {member.display_name}",
                value=f"XP: **{xp}** | Nível: **{nivel}** | Mensagens: {total_mensagens}",
                inline=False
            )
        if count == 0:
            await interaction.followup.send("Nenhum membro encontrado no ranking.", ephemeral=True)
            return
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"Erro ao gerar ranking: {e}", ephemeral=True)

# ================ PREFIX COMMANDS ================
@bot.command(name='ban')
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
@commands.has_permissions(moderate_members=True)
async def prefix_unmute(ctx, membro: discord.Member):
    try:
        if membro.timed_out_until is None:
            return await ctx.send(f"{membro.mention} não está mutado.")
        await membro.timeout(None)
        await ctx.send(f"{membro.mention} foi desmutado.")
    except Exception as e:
        await ctx.send(f"Erro: {e}")

@bot.command(name='lock')
@commands.has_permissions(manage_channels=True)
async def prefix_lock(ctx):
    channel = ctx.channel
    guild = ctx.guild
    try:
        await channel.set_permissions(guild.default_role, send_messages=False)
        await channel.set_permissions(guild.owner, send_messages=True)
        await ctx.send("Canal travado.")
    except Exception as e:
        await ctx.send(f"Erro: {e}")

@bot.command(name='unlock')
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

@bot.command(name='delete')
@commands.has_permissions(manage_messages=True)
async def prefix_delete(ctx, quantidade: int):
    if quantidade < 1 or quantidade > 100:
        return await ctx.send("Número inválido (mín 1, máx 100).")
    try:
        deleted = await ctx.channel.purge(limit=quantidade)
        await ctx.send(f"{len(deleted)} mensagens apagadas.", delete_after=5)
    except Exception as e:
        await ctx.send(f"Erro: {e}")

@bot.command(name='xp')
async def prefix_xp(ctx, membro: discord.Member = None):
    if membro is None:
        membro = ctx.author
    total_mensagens = await get_count(ctx.guild.id, membro.id)
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
async def prefix_rank(ctx):
    try:
        rows = await get_top_users(ctx.guild.id, 5)
        if not rows:
            return await ctx.send("Nenhum dado de XP registrado ainda!")
        embed = discord.Embed(title="Ranking - Top 5", color=discord.Color.gold())
        count = 0
        for i, row in enumerate(rows):
            user_id = row['user_id']
            total = row['count']
            xp = get_xp(total)
            nivel = get_level(xp)
            member = ctx.guild.get_member(user_id)
            if member is None:
                continue
            count += 1
            embed.add_field(
                name=f"{i+1}. {member.display_name}",
                value=f"XP: **{xp}** | Nível: **{nivel}** | Mensagens: {total}",
                inline=False
            )
        if count == 0:
            return await ctx.send("Nenhum membro encontrado no ranking.")
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Erro ao gerar ranking: {e}")

# ================ Inicialização ================
if __name__ == '__main__':
    keep_alive()
    TOKEN = os.environ.get('DISCORD_TOKEN')
    if not TOKEN:
        print("Token não definido!")
    else:
        bot.run(TOKEN)
