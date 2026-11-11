import os
import random
import asyncio
import discord
from discord.ext import commands
from flask import Flask
from dotenv import load_dotenv
from config import configserver, historia
from db import db

# Carrega as variáveis do arquivo .env
load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///configserver.db'
app.config['SQLALCHEMY_BINDS'] = {
    'historia_db': 'sqlite:///hinstorias.db'
}
db.init_app(app)

async def obter_prefixo(bot, message):
    # Se a mensagem foi enviada no chat privado (DM), usa um prefixo padrão
    if not message.guild:
        return "@-"

    # Abre o contexto do Flask para conseguir consultar o SQLAlchemy
    with app.app_context():
        guild_id_str = str(message.guild.id)
        config = configserver.query.filter_by(guild_id=guild_id_str).first()

        if config and config.prefixo:
            return config.prefixo
        
        return "@-"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=obter_prefixo, intents=intents)

# Dicionário para controlar as partidas ativas por canal
jogos_canal = {}

@bot.event
async def on_guild_join(guild):
    print(f"[LOG] O bot entrou no servidor: {guild.name} (ID: {guild.id})")
    
    # 1. Cria a configuração padrão no banco de dados se não existir
    with app.app_context():
        config = configserver.query.filter_by(guild_id=str(guild.id)).first()
        if not config:
            nova_config = configserver(
                guild_id=str(guild.id),
                canal_jogo_id=None,
                prefixo='@-'
            )
            db.session.add(nova_config)
            db.session.commit()
            print("[LOG] Configuração padrão salva no banco com sucesso!")

    # 2. Mensagem do Quicksetup Opcional
    mensagem_quicksetup = (
        f"🎮 **Um por Um!** foi adicionado ao servidor **{guild.name}**!\n\n"
        f"Por padrão, o bot já está pronto para rodar em **qualquer canal** com o prefixo `@-`.\n"
        f"Se quiser personalizar o prefixo, acesse o dashboard:\n"
        f"http://localhost:5000/dashboard"
    )

    # 3. Vai buscar todos os membros diretamente à API do Discord
    print(f"[LOG] A descarregar a lista de membros da guilda...")
    try:
        async for member in guild.fetch_members():
            if not member.bot and member.guild_permissions.administrator:
                print(f"[LOG] Administrador encontrado: {member.name}")
                try:
                    await member.send(mensagem_quicksetup)
                    print(f"[SUCESSO] DM enviada para o adm: {member.name}")
                except Exception as e:
                    print(f"[AVISO] Não foi possível enviar DM para {member.name}. Erro: {e}")
    except Exception as e:
        print(f"[ERRO] Falha ao carregar os membros do servidor: {e}")

@bot.event
async def on_ready():
    print(f"[LOG] Bot conectado com sucesso como {bot.user}!")

@bot.command(name="prefixo")
async def teste(ctx):
    await ctx.send(f"Opa! O prefixo funcionando neste servidor é: `{ctx.prefix}`")

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send('pong🏓')

# --- LÓGICA DO JOGO "UM POR UM" ---

@bot.command(name="jogar")
async def jogar(ctx):
    canal_id = ctx.channel.id
    with app.app_context():
        guild_id_str = str(ctx.guild.id)
        config = configserver.query.filter_by(guild_id=guild_id_str).first()

        # Se o servidor tem um canal de jogo específico configurado
        if config and config.canal_jogo_id:
            if str(ctx.channel.id) != str(config.canal_jogo_id):
                await ctx.send("⚠️ Este canal não é permitido para jogar!")
                print("[ERRO] o usuario tentou jogar em um canal indisponivel!")
                return
    
    if canal_id in jogos_canal:
        await ctx.send("⚠️ Já existe uma partida a decorrer neste canal!")
        print("[ERRO] o usuario tentou jogar em um canal que ja tinha um jogo!")
        return

    # Painel de reação por 30 segundos
    embed = discord.Embed(
        title="🎮 Jogo 'Um por Um' Iniciado!",
        description="Reaja com 🎮 abaixo para entrar na partida!\n⏳ Tem **30 segundos**.",
        color=0x8c52ff
    )
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("🎮")
    print("[LOG] jogo iniciando com sucesso!")

    await asyncio.sleep(30)

    msg_atualizada = await ctx.channel.fetch_message(msg.id)
    reaction = discord.utils.get(msg_atualizada.reactions, emoji="🎮")
    
    participantes = []
    if reaction:
        async for user in reaction.users():
            if not user.bot:
                participantes.append(user)

    if len(participantes) < 2:
        await ctx.send("❌ Não houve jogadores suficientes (mínimo de 2) para iniciar a partida.")
        print("[ERRO] falta de jogadores!")
        return

    # Sorteio aleatório da ordem
    random.shuffle(participantes)
    
    jogos_canal[canal_id] = {
        "jogadores": participantes,
        "turno": 0,
        "historico": []
    }

    ordem_str = " ➔ ".join([p.mention for p in participantes])
    await ctx.send(
        f"🎲 **Inscrições encerradas! Ordem sorteada:**\n{ordem_str}\n\n"
        f"👉 **{participantes[0].mention}**, é a sua vez de digitar **uma palavra** para começar a história!"
    )
    print("[LOG] jogo iniciado com sucesso!")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    canal_id = message.channel.id
    
    if canal_id in jogos_canal:
        jogo = jogos_canal[canal_id]
        jogadores = jogo["jogadores"]
        jogador_atual = jogadores[jogo["turno"]]

        # CASO 1: É a vez do jogador correto
        if message.author == jogador_atual:
            palavra = message.content.strip()

            # Validação: apenas uma palavra e apenas letras
            if " " in palavra or not palavra.isalpha():
                await message.add_reaction("❎")
                jogadores.pop(jogo["turno"])
                
                texto_erro = f"❌ **{jogador_atual.mention} errou!** A palavra deve conter apenas letras e ser apenas **uma** palavra."
                
                if len(jogadores) == 0:
                    await message.channel.send(f"{texto_erro}\n\n🏁 Todos foram eliminados. Fim de jogo!")
                    del jogos_canal[canal_id]
                    return

                if jogo["turno"] >= len(jogadores):
                    jogo["turno"] = 0

                proximo = jogadores[jogo["turno"]]
                nova_ordem = " ➔ ".join([p.mention for p in jogadores])
                
                await message.channel.send(
                    f"{texto_erro}\n🔄 **Nova ordem após eliminação:** {nova_ordem}\n"
                    f"👉 Continua com {proximo.mention}!"
                )
                return

            # Acertou
            await message.add_reaction("✅")
            jogo["historico"].append(palavra)
            jogo["turno"] = (jogo["turno"] + 1) % len(jogadores)

            # Condição de vitória (resta apenas 1)
            if len(jogadores) == 1:
                vencedor = jogadores[0]
                texto_completo = " ".join(jogo["historico"])
                
                with app.app_context():
                    if texto_completo != "":
                        nova_historia = historia(
                            guild_id=str(message.guild.id),
                            vencedor_id=str(vencedor.id),
                            texto_completo=texto_completo
                        )
                        db.session.add(nova_historia)
                        db.session.commit()

                        await message.channel.send(
                                            f"🏆 **FIM DE JOGO!** O grande vencedor é {vencedor.mention} por ser o único sobrevivente!\n"
                                            f"📜 **História finalizada:** *\"{texto_completo}\"*.\n"
                                            f"✨ Essa história já foi salva e está disponível no dashboard do site!"
                                        )
                        del jogos_canal[canal_id]
                        print("[LOG] jogo finalizado!")
                        return
                    else:
                        await message.channel.send(
                            "jogo finalizado! mas não a jogadas então sem ganhadores!"
                            "tente fazer outra partida!"
                        )
                        return

            proximo = jogadores[jogo["turno"]]
            historia_parcial = " ".join(jogo["historico"])
            await message.channel.send(
                f"👉 **{proximo.mention}**, sua vez! "
                f"(História até agora: *`{historia_parcial}`*)"
            )

        # CASO 2: Alguém falou fora da vez
        elif message.author in jogadores:
            await message.add_reaction("❎")
            
            idx = jogadores.index(message.author)
            jogadores.pop(idx)
            
            texto_aviso = f"❌ **{message.author.mention} falou fora da vez e foi eliminado da partida!**"

            if len(jogadores) == 1:
                vencedor = jogadores[0]
                texto_completo = " ".join(jogo["historico"])
                
                with app.app_context():
                    if texto_completo != "":
                        nova_historia = historia(
                            guild_id=str(message.guild.id),
                            vencedor_id=str(vencedor.id),
                            texto_completo=texto_completo
                        )
                        db.session.add(nova_historia)
                        db.session.commit()

                        await message.channel.send(
                        f"{texto_aviso}\n🏆 **FIM DE JOGO!** O vencedor é {vencedor.mention}!\n"
                        f"📜 **História:** *\"{texto_completo}\"*."
                        )
                        del jogos_canal[canal_id]
                        print("[LOG] finalizado!")
                        return
                    else:
                        await message.channel.send(
                            "jogo finalizado! mas não há jogadas então sem ganhadores!"
                            "tente fazer outra partida!"
                            )
                        return

            if jogo["turno"] >= len(jogadores):
                jogo["turno"] = 0

            proximo = jogadores[jogo["turno"]]
            nova_ordem = " ➔ ".join([p.mention for p in jogadores])

            await message.channel.send(
                f"{texto_aviso}\n🔄 **Nova ordem:** {nova_ordem}\n"
                f"👉 Retoma com {proximo.mention}!"
            )

    await bot.process_commands(message)

@bot.command(name="historias")
async def ver_historias_bot(ctx):
    with app.app_context():
        guild_id_str = str(ctx.guild.id)
        # Busca as últimas 5 histórias deste servidor específico
        historias_servidor = historia.query.filter_by(guild_id=guild_id_str).order_by(historia.data_criacao.desc()).limit(5).all()
        
        if not historias_servidor:
            await ctx.send("📜 Ainda não há histórias salvas neste servidor!")
            return
        
        embed = discord.Embed(title="📜 Últimas Histórias do Servidor", color=0x8c52ff)
        for h in historias_servidor:
            embed.add_field(
                name=f"Vencedor ID: {h.vencedor_id}",
                value=f'"{h.texto_completo}"',
                inline=False
            )
        await ctx.send(embed=embed)

# Executa o bot utilizando a variável BOT_TOKEN protegida no arquivo .env
bot.run(os.getenv("BOT_TOKEN"))