import os
import asyncio
import discord
import datetime
import traceback
import httpx
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
            # Primeiro, busca o valor atual
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/counts?guild_id=eq.{guild_id}&user_id=eq.{user_id}&select=count",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}"
                }
            )
            data = response.json()
            
            if data:
                # Atualiza existente
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
                # Insere novo
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

@bot.tree.command(name="canais", description="Cria canais com nomes e emojis personalizados (apenas ADMs)")
@app_commands.describe(
    canais="Nomes dos canais separados por vírgula (ex: games, geral, fut)",
    emojis="Emojis para cada canal na mesma ordem (ex: 💛💚💞 ou :emoji1: :emoji2:)",
    decoracao="Decoração/divisor para o nome do canal (ex: ✧, -, |)"
)
@app_commands.default_permissions(administrator=True)
async def slash_canais(interaction: discord.Interaction, canais: str, emojis: str, decoracao: str):
    await interaction.response.defer()
    
    # Processa os nomes dos canais
    lista_canais = [c.strip() for c in canais.split(",") if c.strip()]
    
    def extrair_emojis(texto_emojis):
        """Extrai emojis do texto, suportando emojis Unicode e personalizados do Discord"""
        emojis_encontrados = []
        
        # Primeiro, procura por emojis personalizados do Discord
        import re
        custom_emoji_pattern = re.compile(r'<a?:\w+:\d+>')
        custom_emojis = custom_emoji_pattern.findall(texto_emojis)
        
        # Remove os emojis personalizados do texto para não duplicar
        texto_sem_custom = custom_emoji_pattern.sub('', texto_emojis)
        
        # Procura por emojis Unicode no texto restante
        emoji_pattern = re.compile(
            "[" 
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # símbolos & pictogramas
            "\U0001F680-\U0001F6FF"  # transporte & símbolos
            "\U0001F1E0-\U0001F1FF"  # bandeiras
            "\U00002702-\U000027B0"  # dingbats
            "\U000024C2-\U0001F251"  # misc
            "\U0001F900-\U0001F9FF"  # símbolos suplementares
            "\U0001FA00-\U0001FA6F"  # chess symbols
            "\U0001FA70-\U0001FAFF"  # symbols extended-A
            "\U00002600-\U000026FF"  # misc symbols
            "\U00002700-\U000027BF"  # dingbats
            "\U0001F780-\U0001F7FF"  # geometric shapes ext
            "\U0001F800-\U0001F8FF"  # supplemental arrows-c
            "\U00002B50"              # star
            "\U00002764"              # heart
            "\U0000203C"              # !! 
            "\U00002049"              # !?
            "\U000020E3"              # combining enclosing keycap
            "\U00002934-\U00002935"   # arrows
            "\U00003030"              # wavy dash
            "\U0000303D"              # part alternation mark
            "\U00003297"              # circled ideograph secret
            "\U00003299"              # circled ideograph congratulations
            "\U0001F004"              # mahjong
            "\U0001F0CF"              # playing card black joker
            "\U0001F170-\U0001F171"   # A, B buttons
            "\U0001F17E-\U0001F17F"   # O, P buttons
            "\U0001F18E"              # AB button
            "\U0001F191-\U0001F19A"   # CL, COOL, FREE, ID, NEW, NG, OK, SOS, UP, VS
            "\U0001F1E6-\U0001F1FF"   # regional indicators (flags)
            "\U0001F201-\U0001F202"   # Japanese symbols
            "\U0001F21A"              # Chinese symbol
            "\U0001F22F"              # Chinese symbol
            "\U0001F232-\U0001F23A"   # symbols
            "\U0001F250-\U0001F251"   # Chinese symbols
            "\U0001F300-\U0001F321"   # misc symbols
            "\U0001F324-\U0001F393"   # misc symbols
            "\U0001F396-\U0001F397"   # misc symbols
            "\U0001F399-\U0001F39B"   # misc symbols
            "\U0001F39E-\U0001F3F0"   # misc symbols
            "\U0001F3F3-\U0001F3F5"   # flags
            "\U0001F3F7-\U0001F4FD"   # misc symbols
            "\U0001F4FF-\U0001F53D"   # misc symbols
            "\U0001F549-\U0001F54E"   # misc symbols
            "\U0001F550-\U0001F567"   # clock faces
            "\U0001F56F-\U0001F570"   # misc symbols
            "\U0001F573-\U0001F57A"   # misc symbols
            "\U0001F587"              # misc symbols
            "\U0001F58A-\U0001F58D"   # misc symbols
            "\U0001F590"              # misc symbols
            "\U0001F595-\U0001F596"   # misc symbols
            "\U0001F5A4-\U0001F5A5"   # misc symbols
            "\U0001F5A8"              # misc symbols
            "\U0001F5B1-\U0001F5B2"   # misc symbols
            "\U0001F5BC"              # misc symbols
            "\U0001F5C2-\U0001F5C4"   # misc symbols
            "\U0001F5D1-\U0001F5D3"   # misc symbols
            "\U0001F5DC-\U0001F5DE"   # misc symbols
            "\U0001F5E1"              # misc symbols
            "\U0001F5E3"              # misc symbols
            "\U0001F5E8"              # misc symbols
            "\U0001F5EF"              # misc symbols
            "\U0001F5F3"              # misc symbols
            "\U0001F5FA-\U0001F64F"   # misc symbols
            "\U0001F680-\U0001F6C5"   # transport symbols
            "\U0001F6CB-\U0001F6D2"   # transport symbols
            "\U0001F6E0-\U0001F6E5"   # transport symbols
            "\U0001F6E9"              # transport symbols
            "\U0001F6EB-\U0001F6EC"   # transport symbols
            "\U0001F6F0"              # transport symbols
            "\U0001F6F3-\U0001F6F9"   # transport symbols
            "\U0001F900-\U0001F9FF"   # supplemental symbols
            "\U0001FA00-\U0001FA6F"   # chess symbols
            "\U0001FA70-\U0001FAFF"   # symbols extended-A
            "\U00002764"              # heart
            "\U0001F495-\U0001F49F"   # hearts
            "\U0001F4A0-\U0001F4A9"   # misc symbols
            "\U0001F4AB-\U0001F4AF"   # misc symbols
            "\U0001F4B0-\U0001F4BF"   # money symbols
            "\U0001F4C0-\U0001F4CF"   # office symbols
            "\U0001F4D0-\U0001F4D9"   # communication symbols
            "\U0000231A-\U0000231B"   # watch, hourglass
            "\U000023E9-\U000023F3"   # various
            "\U000023F8-\U000023FA"   # various
            "\U000023ED-\U000023EF"   # various
            "\U0001F440-\U0001F441"   # eyes
            "\U0001F442-\U0001F445"   # body parts
            "\U0001F446-\U0001F450"   # hands
            "\U0001F46B-\U0001F46D"   # couples
            "\U0001F46E-\U0001F470"   # people
            "\U0001F471-\U0001F478"   # people
            "\U0001F479-\U0001F47B"   # fantasy
            "\U0001F47C-\U0001F480"   # people/symbols
            "\U0001F481-\U0001F487"   # gestures
            "\U0001F488-\U0001F48B"   # love/mail
            "\U0001F48C-\U0001F48F"   # kiss/couple
            "\U0001F490-\U0001F494"   # hearts/objects
            "\U0001F5FB-\U0001F5FF"   # various
            "\U0001F9D0-\U0001F9E6"   # various
            "\U0001F9B0-\U0001F9BB"   # animals/nature
            "\U0001F9C0-\U0001F9C2"   # food/drink
            "\U0001F9E7-\U0001F9FF"   # objects
            "\U00002670-\U00002671"   # misc
            "\U0000267F"              # wheelchair
            "\U00002692-\U00002693"   # anchor/ferry
            "\U000026A0-\U000026A1"   # warning/high voltage
            "\U000026AA-\U000026AB"   # circles
            "\U000026BD-\U000026BE"   # sports
            "\U000026C4-\U000026C5"   # snowman/sun
            "\U000026CE"              # ophiuchus
            "\U000026D4"              # no entry
            "\U000026EA"              # church
            "\U000026F2-\U000026F3"   # fountain/golf
            "\U000026F5"              # sailboat
            "\U000026FA"              # tent
            "\U000026FD"              # fuel pump
            "\U00002702"              # scissors
            "\U00002708-\U0000270F"   # plane/envelope/hand
            "\U00002712"              # black nib
            "\U00002714"              # check mark
            "\U00002716"              # cross mark
            "\U0000271D"              # latin cross
            "\U00002721"              # star of david
            "\U00002733-\U00002734"   # symbols
            "\U00002744"              # snowflake
            "\U00002747"              # sparkle
            "\U0000274C"              # cross mark
            "\U0000274E"              # cross mark
            "\U00002753-\U00002755"   # question marks
            "\U00002757"              # exclamation mark
            "\U00002763-\U00002764"   # heart symbols
            "\U00002795-\U00002797"   # math symbols
            "\U000027A1"              # right arrow
            "\U000027B0"              # curly loop
            "\U000027BF"              # double curly loop
            "\U00002B05-\U00002B07"   # arrows
            "\U00002B1B-\U00002B1C"   # squares
            "\U00002B50"              # star
            "\U00002B55"              # circle
            "\U0001F321"              # thermometer
            "\U0001F336"              # hot pepper
            "\U0001F37D"              # fork and knife
            "\U0001F396-\U0001F397"   # military/reminder
            "\U0001F399-\U0001F39B"   # audio/control
            "\U0001F39E-\U0001F39F"   # film/symbols
            "\U0001F3CB-\U0001F3CE"   # sports
            "\U0001F3D4-\U0001F3DF"   # places
            "\U0001F3F3-\U0001F3F5"   # flags
            "\U0001F3F8-\U0001F3F9"   # sports/activities
            "\U0001F43F"              # chipmunk
            "\U0001F441"              # eye
            "\U0001F4FD-\U0001F4FE"   # film/video
            "\U0001F508-\U0001F50A"   # speaker
            "\U0001F50C-\U0001F514"   # various
            "\U0001F516-\U0001F53D"   # various
            "\U0001F549-\U0001F54A"   # symbols
            "\U0001F54B-\U0001F54E"   # various
            "\U0001F56F-\U0001F570"   # various
            "\U0001F573-\U0001F579"   # various
            "\U0001F57A"              # various
            "\U0001F587"              # various
            "\U0001F58A-\U0001F58D"   # various
            "\U0001F590"              # various
            "\U0001F595-\U0001F596"   # various
            "\U0001F5A4"              # mountain
            "\U0001F5A5-\U0001F5A8"   # various
            "\U0001F5B1-\U0001F5B2"   # various
            "\U0001F5BC"              # various
            "\U0001F5C2-\U0001F5C4"   # various
            "\U0001F5D1-\U0001F5D3"   # various
            "\U0001F5DC-\U0001F5DE"   # various
            "\U0001F5E1"              # various
            "\U0001F5E3"              # various
            "\U0001F5E8"              # various
            "\U0001F5EF"              # various
            "\U0001F5F3"              # various
            "\U0001F5FA"              # various
            "\U0001F6CB"              # various
            "\U0001F6CD-\U0001F6CF"   # various
            "\U0001F6E0-\U0001F6E5"   # various
            "\U0001F6E9"              # various
            "\U0001F6F0"              # various
            "\U0001F6F3"              # various
            "\U0001F6F4-\U0001F6F6"   # various
            "\U0001F6F7-\U0001F6F8"   # various
            "\U0001F6F9"              # various
            "\U0001F6FA"              # various
            "]",
            flags=re.UNICODE
        )
        
        unicode_emojis = emoji_pattern.findall(texto_sem_custom)
        
        # Combina os emojis Unicode e personalizados na ordem que aparecem
        # Mas precisamos intercalar corretamente
        texto_completo = texto_emojis
        pos_custom = {texto_completo.find(emoji): emoji for emoji in custom_emojis}
        
        # Procura por todos os emojis na string original, na ordem
        todo_texto = texto_emojis
        pos = 0
        
        # Cria uma lista de (posição, emoji) para todos os emojis
        todos_emojis = []
        
        # Adiciona emojis customizados
        for emoji in custom_emojis:
            idx = todo_texto.find(emoji)
            if idx != -1:
                todos_emojis.append((idx, emoji))
        
        # Adiciona emojis Unicode
        for emoji in unicode_emojis:
            idx = todo_texto.find(emoji)
            if idx != -1:
                # Verifica se não é parte de um emoji customizado
                is_part_of_custom = False
                for custom_emoji in custom_emojis:
                    custom_idx = todo_texto.find(custom_emoji)
                    if custom_idx != -1 and custom_idx <= idx < custom_idx + len(custom_emoji):
                        is_part_of_custom = True
                        break
                
                if not is_part_of_custom:
                    todos_emojis.append((idx, emoji))
        
        # Ordena por posição e remove duplicatas
        todos_emojis.sort(key=lambda x: x[0])
        emojis_final = []
        posicoes_vistas = set()
        
        for pos, emoji in todos_emojis:
            if pos not in posicoes_vistas:
                emojis_final.append(emoji)
                posicoes_vistas.add(pos)
        
        return emojis_final
    
    # Extrai os emojis
    lista_emojis = extrair_emojis(emojis)
    
    # Verifica se há emojis suficientes
    if len(lista_emojis) < len(lista_canais):
        await interaction.followup.send(
            f"❌ Você precisa fornecer pelo menos **{len(lista_canais)}** emoji(s)!\n"
            f"Você forneceu apenas **{len(lista_emojis)}** emoji(s).\n\n"
            f"**Dica:** Você pode usar emojis Unicode (💛, 🎮, etc) ou emojis personalizados do Discord!",
            ephemeral=True
        )
        return
    
    # Verifica se a decoração não está vazia
    if not decoracao.strip():
        await interaction.followup.send("❌ A decoração não pode estar vazia!", ephemeral=True)
        return
    
    canais_criados = []
    categoria = interaction.channel.category
    
    for i, nome_canal in enumerate(lista_canais):
        nome_formatado = f"{decoracao}{nome_canal}{decoracao}"
        emoji = lista_emojis[i]
        nome_final = f"{emoji}{nome_formatado}"
        
        try:
            novo_canal = await interaction.guild.create_text_channel(
                name=nome_final,
                category=categoria,
                reason=f"Canal criado por {interaction.user.display_name}"
            )
            canais_criados.append((emoji, novo_canal))
        except Exception as e:
            await interaction.followup.send(
                f"❌ Erro ao criar o canal `{nome_canal}`: {e}",
                ephemeral=True
            )
            return
    
    # Confirmação
    embed = discord.Embed(
        title="✅ Canais Criados com Sucesso!",
        description=f"Foram criados **{len(canais_criados)}** canal(is):",
        color=discord.Color.green()
    )
    
    for i, (emoji, canal) in enumerate(canais_criados):
        embed.add_field(
            name=f"Canal {i+1}",
            value=f"{emoji} {canal.mention}",
            inline=False
        )
    
    embed.set_footer(text=f"Criado por {interaction.user.display_name}")
    await interaction.followup.send(embed=embed)

# Versão com prefixo atualizada também
@bot.command(name='canais')
@commands.has_permissions(administrator=True)
async def prefix_canais(ctx, canais: str, *, args: str = None):
    """
    Cria canais com emojis e decoração
    Uso: /canais nome1,nome2,nome3 emoji1,emoji2,emoji3 decoração
    Exemplo: /canais games,geral 💛💚 ✧
    Exemplo: /canais vip,mod :star: :crown: |
    """
    if not args:
        return await ctx.send("❌ Use: `/canais nomes emojis decoração`\nExemplo: `/canais games,geral 💛💚 ✧`")
    
    # Divide os argumentos restantes
    import shlex
    try:
        partes = shlex.split(args)
    except:
        partes = args.split()
    
    if len(partes) < 2:
        return await ctx.send("❌ Faltam argumentos! Use: `/canais nomes emojis decoração`")
    
    emojis_str = partes[0]
    decoracao = ' '.join(partes[1:])
    
    # Processa os nomes dos canais
    lista_canais = [c.strip() for c in canais.split(",") if c.strip()]
    
    # Mesma função de extrair emojis
    def extrair_emojis_prefix(texto_emojis):
        import re
        emojis_encontrados = []
        
        # Emojis personalizados do Discord
        custom_emoji_pattern = re.compile(r'<a?:\w+:\d+>')
        custom_emojis = custom_emoji_pattern.findall(texto_emojis)
        texto_sem_custom = custom_emoji_pattern.sub('', texto_emojis)
        
        # Emojis Unicode
        emoji_pattern = re.compile(
            "[" 
            "\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251"
            "\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF"
            "\U00002600-\U000026FF\U00002700-\U000027BF\U0001F780-\U0001F7FF"
            "\U00002B50\U00002764\U0000203C\U00002049\U000020E3\U0001F004"
            "\U0001F0CF\u23F0\u23F3\u2600-\u27BF\u2B50\u2B55\u231A\u231B"
            "\u2328\u23CF\u23E9-\u23F3\u23F8-\u23FA\u24C2\u25AA\u25AB"
            "\u25B6\u25C0\u25FB-\u25FE\u2600-\u2B55\u2702\u2705\u2708-\u270D"
            "\u270F\u2712\u2714\u2716\u271D\u2721\u2728\u2733\u2734\u2744"
            "\u2747\u274C\u274E\u2753-\u2755\u2757\u2763\u2764\u2795-\u2797"
            "\u27A1\u27B0\u27BF\u2934\u2935\u2B05-\u2B07\u2B1B\u2B1C\u2B50"
            "\u2B55\u3030\u303D\u3297\u3299\U0001F004\U0001F0CF\U0001F170"
            "\U0001F171\U0001F17E\U0001F17F\U0001F18E\U0001F191-\U0001F19A"
            "\U0001F1E6-\U0001F1FF\U0001F201\U0001F202\U0001F21A\U0001F22F"
            "\U0001F232-\U0001F23A\U0001F250\U0001F251\U0001F300-\U0001F6F9"
            "\U0001F7E0-\U0001F7EB\U0001F90D-\U0001F93A\U0001F93C-\U0001F945"
            "\U0001F947-\U0001F971\U0001F973-\U0001F976\U0001F97A-\U0001F9A2"
            "\U0001F9A5-\U0001F9AA\U0001F9AE-\U0001F9CA\U0001F9CD-\U0001F9FF"
            "\U0001FA00-\U0001FA6F\U0001FA70-\U0001FA73\U0001FA78-\U0001FA7A"
            "\U0001FA80-\U0001FA82\U0001FA90-\U0001FA95" 
            "]",
            flags=re.UNICODE
        )
        
        unicode_emojis = emoji_pattern.findall(texto_sem_custom)
        
        # Ordena por posição no texto original
        todos_emojis = []
        for emoji in custom_emojis:
            idx = texto_emojis.find(emoji)
            if idx != -1:
                todos_emojis.append((idx, emoji))
        
        for emoji in unicode_emojis:
            idx = texto_emojis.find(emoji)
            if idx != -1:
                is_in_custom = False
                for custom_emoji in custom_emojis:
                    custom_idx = texto_emojis.find(custom_emoji)
                    if custom_idx != -1 and custom_idx <= idx < custom_idx + len(custom_emoji):
                        is_in_custom = True
                        break
                if not is_in_custom:
                    todos_emojis.append((idx, emoji))
        
        todos_emojis.sort()
        return [emoji for _, emoji in todos_emojis]
    
    lista_emojis = extrair_emojis_prefix(emojis_str)
    
    if len(lista_emojis) < len(lista_canais):
        return await ctx.send(
            f"❌ Você precisa de **{len(lista_canais)}** emoji(s), mas só forneceu **{len(lista_emojis)}**!\n"
            f"Dica: Use emojis Unicode ou emojis personalizados do Discord."
        )
    
    if not decoracao.strip():
        return await ctx.send("❌ A decoração não pode estar vazia!")
    
    canais_criados = []
    categoria = ctx.channel.category
    
    for i, nome_canal in enumerate(lista_canais):
        nome_formatado = f"{decoracao}{nome_canal}{decoracao}"
        emoji = lista_emojis[i]
        nome_final = f"{emoji}{nome_formatado}"
        
        try:
            novo_canal = await ctx.guild.create_text_channel(
                name=nome_final,
                category=categoria,
                reason=f"Criado por {ctx.author.display_name}"
            )
            canais_criados.append((emoji, novo_canal))
        except Exception as e:
            return await ctx.send(f"❌ Erro ao criar `{nome_canal}`: {e}")
    
    embed = discord.Embed(
        title="✅ Canais Criados!",
        description=f"Criados **{len(canais_criados)}** canais:",
        color=discord.Color.green()
    )
    
    for i, (emoji, canal) in enumerate(canais_criados):
        embed.add_field(name=f"Canal {i+1}", value=f"{emoji} {canal.mention}", inline=False)
    
    embed.set_footer(text=f"Criado por {ctx.author.display_name}")
    await ctx.send(embed=embed)

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
