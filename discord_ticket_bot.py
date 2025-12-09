# ======================
# IMPORTS & SETUP
# ======================
import discord
from discord.ext import commands
from discord.ui import View
from discord import app_commands
# Necessario per la riproduzione audio (la classe è inclusa in discord.py)
from discord import FFmpegPCMAudio 
import asyncio
import json
import os
import datetime

# ======================
# CONFIGURAZIONE
# ======================
# Nome del ruolo Staff per i controlli di permesso
STAFF_ROLE_NAME = "Ruolo Test Bot"
# Nome del canale di log (deve esistere sul tuo server)
LOG_CHANNEL_NAME = "bot-logs"
# Nome o ID del canale di benvenuto (se è un ID numerico, verrà cercato come ID)
WELCOME_CHANNEL_NAME = "1445058859495329905" 

# Necessario per accedere a membri, ruoli, e per gli eventi vocali
intents = discord.Intents.default()
intents.members = True
intents.message_content = True # Obbligatorio per i comandi prefix e per on_message_delete
intents.guilds = True
intents.voice_states = True # ESSENZIALE per la musica

bot = commands.Bot(command_prefix="!", intents=intents)

# ======================
# DATABASE JSON
# Struttura: {"claimed": {}, "warnings": { "guild_id": { "user_id": [{"mod": "id", "reason": "text", "ts": "iso_date"}] } } }
# ======================
DB_FILE = "database.json"

def load_db():
    """Carica il database JSON. Crea il file se non esiste."""
    if not os.path.exists(DB_FILE):
        data = {"claimed": {}, "warnings": {}}
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=4)
        return data
    
    try:
        with open(DB_FILE, "r") as f:
            data = json.load(f)
            if "warnings" not in data:
                 data["warnings"] = {}
                 save_db(data)
            return data
    except json.JSONDecodeError:
        print(f"ATTENZIONE: Il file {DB_FILE} è corrotto. Reinizializzo il database.")
        data = {"claimed": {}, "warnings": {}}
        save_db(data)
        return data

def save_db(data):
    """Salva i dati nel database JSON."""
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ======================
# FUNZIONI DI LOGGING & CANALI
# ======================

async def get_log_channel(guild):
    """Trova il canale di log nel server."""
    return discord.utils.get(guild.channels, name=LOG_CHANNEL_NAME)

async def get_welcome_channel(guild):
    """Trova il canale di benvenuto per nome o ID."""
    try:
        channel_id = int(WELCOME_CHANNEL_NAME)
        return guild.get_channel(channel_id)
    except ValueError:
        return discord.utils.get(guild.text_channels, name=WELCOME_CHANNEL_NAME)

async def send_log_embed(guild, title, description, color):
    """Invia un messaggio embed nel canale di log."""
    log_channel = await get_log_channel(guild)
    if log_channel:
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.datetime.now()
        )
        await log_channel.send(embed=embed)
    else:
        print(f"AVVISO: Canale di log '{LOG_CHANNEL_NAME}' non trovato in {guild.name}.")


# ======================
# TICKET CONTROL PANEL
# ======================

class TicketControlPanel(View):
    """View con i bottoni Claim, Unclaim e Close, usata all'interno del canale ticket."""
    def __init__(self):
        super().__init__(timeout=None)
        self.staff_role_name = STAFF_ROLE_NAME
        self.custom_id = "persistent_ticket_control_panel"

    async def get_staff_role(self, guild):
        return discord.utils.get(guild.roles, name=self.staff_role_name)

    @discord.ui.button(label="📌 Claim", style=discord.ButtonStyle.primary, custom_id="claim_ticket")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff_role = await self.get_staff_role(interaction.guild)
        
        if staff_role not in interaction.user.roles:
            return await interaction.response.send_message("Non hai i permessi per claimare.", ephemeral=True)

        db = load_db()
        channel_id_str = str(interaction.channel.id)

        if channel_id_str in db["claimed"]:
            claimed_user_id = db["claimed"][channel_id_str]
            if claimed_user_id == interaction.user.id:
                 return await interaction.response.send_message("Hai già claimato questo ticket.", ephemeral=True)
            else:
                 return await interaction.response.send_message(f"Questo ticket è già claimato da <@{claimed_user_id}>.", ephemeral=True)
            
        
        db["claimed"][channel_id_str] = interaction.user.id
        save_db(db)

        await send_log_embed(
            interaction.guild,
            "📌 Ticket Claimato",
            f"Il ticket {interaction.channel.mention} è stato claimato da {interaction.user.mention}.",
            discord.Color.blue()
        )
        await interaction.response.send_message(f"📌 Ticket claimato da {interaction.user.mention}!", ephemeral=False)

    @discord.ui.button(label="❎ Unclaim", style=discord.ButtonStyle.secondary, custom_id="unclaim_ticket")
    async def unclaim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff_role = await self.get_staff_role(interaction.guild)
        
        if staff_role not in interaction.user.roles:
            return await interaction.response.send_message("Non hai i permessi.", ephemeral=True)

        db = load_db()
        channel_id_str = str(interaction.channel.id)
        
        if channel_id_str in db["claimed"]:
            claimed_user_id = db["claimed"][channel_id_str]

            if claimed_user_id != interaction.user.id and interaction.user != interaction.guild.owner:
                 return await interaction.response.send_message("Puoi unclaimare solo i ticket che hai claimato tu.", ephemeral=True)

            del db["claimed"][channel_id_str]
            save_db(db)
            
            await send_log_embed(
                interaction.guild,
                "❎ Ticket Unclaimato",
                f"Il ticket {interaction.channel.mention} è stato unclaimato da {interaction.user.mention}.",
                discord.Color.light_grey()
            )

            return await interaction.response.send_message("❎ Ticket unclaimato!", ephemeral=False)
        else:
            return await interaction.response.send_message("Questo ticket non era claimato.", ephemeral=True)

    @discord.ui.button(label="🔒 Close", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith("ticket-"):
            return await interaction.response.send_message("Questo non è un ticket.", ephemeral=True)

        staff_role = await self.get_staff_role(interaction.guild)
        if staff_role not in interaction.user.roles and not interaction.user.guild_permissions.administrator:
             return await interaction.response.send_message("Non hai i permessi per chiudere questo ticket.", ephemeral=True)

        transcript_filename = f"transcript-{interaction.channel.id}.txt"
        
        await interaction.response.send_message("🔒 Ticket chiuso tra 3 secondi. Generazione del transcript in corso...")
        
        messages = [msg async for msg in interaction.channel.history(limit=None, oldest_first=True)]
        
        transcript_text = "--- TRANSCRIPT TICKET ---\n"
        transcript_text += f"Canale: {interaction.channel.name}\n"
        transcript_text += f"Chiuso da: {interaction.user.name} ({interaction.user.id})\n"
        transcript_text += "--- MESSAGGI ---\n\n"
        
        for m in messages:
             transcript_text += f"[{m.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {m.author.display_name}: {m.content}\n"

        try:
            with open(transcript_filename, "w", encoding="utf-8") as f:
                f.write(transcript_text)
            
            await interaction.edit_original_response(
                 content="✅ Transcript generato! Eliminazione del canale in corso...",
                 file=discord.File(transcript_filename)
            )

        except Exception as e:
            print(f"Errore nella generazione del transcript: {e}")
            await interaction.edit_original_response(content="❌ Errore durante la generazione del transcript. Eliminazione del canale tra 3 secondi...")
        finally:
            log_channel = await get_log_channel(interaction.guild)
            if log_channel:
                 embed = discord.Embed(
                    title="🔒 Ticket Chiuso",
                    description=f"Il ticket `{interaction.channel.name}` (creato da <@{interaction.channel.name.split('-')[1]}>) è stato chiuso da {interaction.user.mention}.",
                    color=discord.Color.dark_red(),
                    timestamp=datetime.datetime.now()
                )
                 await log_channel.send(embed=embed, file=discord.File(transcript_filename, filename=transcript_filename))
            
            db = load_db()
            channel_id_str = str(interaction.channel.id)
            if channel_id_str in db["claimed"]:
                del db["claimed"][channel_id_str]
                save_db(db)
            
            await asyncio.sleep(3)
            await interaction.channel.delete()
            
            if os.path.exists(transcript_filename):
                os.remove(transcript_filename)


class TicketOpenPanel(View):
    """View con il bottone 'Apri Ticket', usata nel canale principale."""
    def __init__(self):
        super().__init__(timeout=None)
        self.custom_id = "persistent_ticket_open_panel"
        self.staff_role_name = STAFF_ROLE_NAME

    async def get_staff_role(self, guild):
        return discord.utils.get(guild.roles, name=self.staff_role_name)

    @discord.ui.button(label="🎫 Apri Ticket", style=discord.ButtonStyle.success, custom_id="open_ticket_btn")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        existing_ticket = discord.utils.get(interaction.guild.channels, name=f"ticket-{interaction.user.id}")
        if existing_ticket:
            return await interaction.response.send_message(
                f"Hai già un ticket aperto: {existing_ticket.mention}", ephemeral=True
            )
            
        staff_role = await self.get_staff_role(interaction.guild)
        if not staff_role:
             return await interaction.response.send_message(
                 f"Errore: Il ruolo '{STAFF_ROLE_NAME}' non è stato trovato. Contatta un amministratore.", ephemeral=True
            )

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            staff_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }

        ticket_channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.id}",
            overwrites=overwrites,
            category=interaction.channel.category
        )

        await ticket_channel.send(
            f"🎟 **Nuovo ticket aperto da {interaction.user.mention}**\nLo staff è stato notificato, attendi la risposta.",
            view=TicketControlPanel()
        )
        
        await send_log_embed(
            interaction.guild,
            "🎫 Nuovo Ticket Aperto",
            f"{interaction.user.mention} ha aperto un nuovo ticket: {ticket_channel.mention}",
            discord.Color.green()
        )

        await interaction.response.send_message(
            f"Ticket creato: {ticket_channel.mention}", ephemeral=True
        )

# ======================
# EVENTI DI SISTEMA (WELCOME & LOGGING)
# ======================

@bot.event
async def on_member_join(member):
    """Gestisce l'evento di un nuovo membro che si unisce al server (Welcome)."""
    if member.id == bot.user.id:
        return

    # 1. Log dell'azione
    await send_log_embed(
        member.guild,
        "👋 Membro Entrato",
        f"L'utente {member.mention} ({member.id}) si è unito al server.\n**Membri totali:** {member.guild.member_count}",
        discord.Color.lighter_grey()
    )

    # 2. Messaggio di Benvenuto
    welcome_channel = await get_welcome_channel(member.guild)
    if welcome_channel:
        embed = discord.Embed(
            title=f"Benvenuto/a, {member.name}!",
            description=f"Siamo felici di averti a bordo! Sei il **{member.guild.member_count}°** membro. Dai un'occhiata alle regole e goditi la community!",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await welcome_channel.send(f"Benvenuto/a {member.mention}!", embed=embed)


@bot.event
async def on_member_remove(member):
    """Gestisce l'evento di un membro che lascia il server."""
    await send_log_embed(
        member.guild,
        "🚪 Membro Uscito",
        f"L'utente `{member.name}` ({member.id}) ha lasciato il server.",
        discord.Color.red()
    )

@bot.event
async def on_message_delete(message):
    """Gestisce l'evento di eliminazione di un messaggio. (Versione anti-troncamento)"""
    if message.author.bot or not message.guild:
        return

    description = (
        "**Autore:** {author_mention}\n"
        "**Canale:** {channel_mention}\n"
        "**Contenuto:** \n"
        "```\n{content}\n```"
    ).format(
        author_mention=message.author.mention,
        channel_mention=message.channel.mention,
        content=message.content[:1000] if message.content else "(Contenuto non disponibile)"
    )

    await send_log_embed(
        message.guild,
        "🗑️ Messaggio Eliminato",
        description,
        discord.Color.orange()
    )

# ======================
# COMANDI SLASH (GENERALI)
# ======================

@bot.event
async def on_ready():
    """Viene eseguito all'avvio del bot."""
    print(f'Bot loggato come {bot.user}')
    
    # 1. Carica le View persistenti
    bot.add_view(TicketOpenPanel())
    bot.add_view(TicketControlPanel())
    print("Viste persistenti caricate.")
    
    # 2. Sincronizza i comandi slash
    try:
        synced = await bot.tree.sync()
        print(f"Sincronizzati {len(synced)} comandi slash: {[s.name for s in synced]}")
    except Exception as e:
        print(f"Errore durante la sincronizzazione dei comandi slash: {e}")

# Gestore globale degli errori
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingRole):
        await interaction.response.send_message(
            f"❌ Non hai i permessi sufficienti (ruolo richiesto: **{STAFF_ROLE_NAME}**).",
            ephemeral=True
        )
    elif isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            f"❌ Non hai i permessi necessari per eseguire questo comando: `{error.missing_permissions}`",
            ephemeral=True
        )
    else:
        print(f"Errore nel comando slash: {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Si è verificato un errore sconosciuto durante l'esecuzione del comando.", ephemeral=True)


# ======================
# COMANDI TICKET
# ======================

@bot.tree.command(name="setticket", description="Invia il pannello per l'apertura dei ticket. (Solo Staff)")
@app_commands.checks.has_role(STAFF_ROLE_NAME)
async def setticket_slash(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎫 Sistema di Supporto",
        description="Clicca sul bottone qui sotto per aprire un nuovo ticket di supporto.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, view=TicketOpenPanel())


@bot.tree.command(name="staffpanel", description="Visualizza i ticket attualmente claimati. (Solo Staff)")
@app_commands.checks.has_role(STAFF_ROLE_NAME)
async def staffpanel_slash(interaction: discord.Interaction):
    db = load_db()

    if not db["claimed"]:
        return await interaction.response.send_message("Nessun ticket claimato al momento.", ephemeral=True)

    msg = "**📋 Ticket Claimati:**\n\n"
    for channel_id, user_id in db["claimed"].items():
        msg += f"• Ticket <#{channel_id}> – Claimato da <@{user_id}>\n"
        
    await interaction.response.send_message(msg)


# ======================
# COMANDI DI MODERAZIONE
# ======================

@bot.tree.command(name="warn", description="Aggiunge un avvertimento a un utente. (Solo Staff)")
@app_commands.describe(
    membro="L'utente da ammonire.",
    motivo="Il motivo dell'ammonizione."
)
@app_commands.checks.has_role(STAFF_ROLE_NAME)
async def warn_slash(interaction: discord.Interaction, membro: discord.Member, motivo: str):
    if membro.id == interaction.user.id or membro.bot:
        return await interaction.response.send_message("Non puoi ammonire te stesso o un bot.", ephemeral=True)

    db = load_db()
    guild_id_str = str(interaction.guild.id)
    user_id_str = str(membro.id)

    if guild_id_str not in db["warnings"]:
        db["warnings"][guild_id_str] = {}
    if user_id_str not in db["warnings"][guild_id_str]:
        db["warnings"][guild_id_str][user_id_str] = []

    warning = {
        "moderator": str(interaction.user.id),
        "reason": motivo,
        "timestamp": datetime.datetime.now().isoformat()
    }
    db["warnings"][guild_id_str][user_id_str].append(warning)
    save_db(db)
    
    warn_count = len(db["warnings"][guild_id_str][user_id_str])

    try:
        await membro.send(
            f"Sei stato ammonito sul server **{interaction.guild.name}**.\n"
            f"Motivo: **{motivo}**\n"
            f"Totale ammonimenti: **{warn_count}**"
        )
    except discord.Forbidden:
        pass

    await interaction.response.send_message(f"✅ Ammonimento aggiunto a {membro.mention}. Ha ora **{warn_count}** ammonimenti.", ephemeral=False)
    
    await send_log_embed(
        interaction.guild,
        "⚠️ Utente Ammonito",
        f"**Utente:** {membro.mention} ({membro.id})\n"
        f"**Moderatore:** {interaction.user.mention}\n"
        f"**Motivo:** {motivo}\n"
        f"**Totale Warns:** {warn_count}",
        discord.Color.yellow()
    )


@bot.tree.command(name="warnings", description="Visualizza gli ammonimenti di un utente. (Solo Staff)")
@app_commands.describe(
    membro="L'utente di cui visualizzare gli ammonimenti."
)
@app_commands.checks.has_role(STAFF_ROLE_NAME)
async def warnings_slash(interaction: discord.Interaction, membro: discord.Member):
    db = load_db()
    guild_id_str = str(interaction.guild.id)
    user_id_str = str(membro.id)

    warnings = db["warnings"].get(guild_id_str, {}).get(user_id_str, [])

    if not warnings:
        return await interaction.response.send_message(f"{membro.display_name} non ha ammonimenti.", ephemeral=True)

    embed = discord.Embed(
        title=f"⚠️ Ammonimenti di {membro.display_name}",
        color=discord.Color.yellow()
    )
    
    for i, w in enumerate(warnings, 1):
        mod = interaction.guild.get_member(int(w["moderator"]))
        mod_name = mod.display_name if mod else "Utente Sconosciuto"
        timestamp = datetime.datetime.fromisoformat(w["timestamp"]).strftime('%Y-%m-%d %H:%M')
        
        embed.add_field(
            name=f"Warn #{i} - {timestamp}",
            value=f"**Motivo:** {w['reason']}\n**Moderatore:** {mod_name}",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=False)


@bot.tree.command(name="mute", description="Mutea un utente. (Necessita di un ruolo 'Muted'.)")
@app_commands.describe(
    membro="L'utente da mutare.",
    durata_minuti="Durata del mute in minuti.",
    motivo="Motivo del mute."
)
@app_commands.checks.has_role(STAFF_ROLE_NAME)
async def mute_slash(interaction: discord.Interaction, membro: discord.Member, durata_minuti: int, motivo: str):
    if not interaction.user.guild_permissions.kick_members:
        return await interaction.response.send_message("Non hai i permessi 'Kick Members' necessari per mutare.", ephemeral=True)
        
    if membro.id == interaction.user.id or membro.bot:
        return await interaction.response.send_message("Non puoi mutare te stesso o un bot.", ephemeral=True)

    muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not muted_role:
        return await interaction.response.send_message(
            "❌ Errore: Il ruolo **'Muted'** non è stato trovato. Crealo e configura i permessi nei canali.", 
            ephemeral=True
        )

    try:
        await membro.add_roles(muted_role, reason=f"Mute: {motivo} da {interaction.user.name}")
        
        await interaction.response.send_message(
            f"✅ {membro.mention} è stato mutato per {durata_minuti} minuti. Motivo: `{motivo}`", 
            ephemeral=False
        )

        await send_log_embed(
            interaction.guild,
            "🔇 Utente Mutato",
            f"**Utente:** {membro.mention}\n**Moderatore:** {interaction.user.mention}\n"
            f"**Durata:** {durata_minuti} minuti\n**Motivo:** {motivo}",
            discord.Color.dark_magenta()
        )
        
        # Schedule Unmute
        await asyncio.sleep(durata_minuti * 60)
        
        # Ricarica il membro per assicurarsi che i ruoli siano aggiornati
        try:
             updated_member = await interaction.guild.fetch_member(membro.id)
        except discord.NotFound:
             # L'utente ha lasciato il server
             return

        if muted_role in updated_member.roles:
            await updated_member.remove_roles(muted_role, reason="Unmute automatico (durata scaduta)")
            try:
                await updated_member.send(f"Il tuo mute sul server **{interaction.guild.name}** è terminato.")
            except discord.Forbidden:
                pass
            
            await send_log_embed(
                interaction.guild,
                "🔊 Unmute Automatico",
                f"{updated_member.mention} è stato smuteato automaticamente dopo {durata_minuti} minuti.",
                discord.Color.teal()
            )

    except Exception as e:
        await interaction.response.send_message(f"❌ Impossibile mutare l'utente: {e}", ephemeral=True)


@bot.tree.command(name="unmute", description="Rimuove il mute da un utente.")
@app_commands.describe(
    membro="L'utente da smutare."
)
@app_commands.checks.has_role(STAFF_ROLE_NAME)
async def unmute_slash(interaction: discord.Interaction, membro: discord.Member):
    if not interaction.user.guild_permissions.kick_members:
        return await interaction.response.send_message("Non hai i permessi 'Kick Members' necessari per smutare.", ephemeral=True)

    muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not muted_role:
        return await interaction.response.send_message(
            "❌ Errore: Il ruolo **'Muted'** non è stato trovato.", 
            ephemeral=True
        )

    if muted_role in membro.roles:
        await membro.remove_roles(muted_role, reason=f"Unmute manuale da {interaction.user.name}")
        
        await interaction.response.send_message(
            f"✅ Mute rimosso da {membro.mention}.", 
            ephemeral=False
        )

        await send_log_embed(
            interaction.guild,
            "🔊 Unmute Manuale",
            f"**Utente:** {membro.mention}\n**Moderatore:** {interaction.user.mention}",
            discord.Color.teal()
        )
    else:
        await interaction.response.send_message(f"🤔 {membro.mention} non risulta mutato.", ephemeral=True)


# ======================
# COMANDI MUSICA/VOCE
# ======================

@bot.tree.command(name="join", description="Il bot si unisce al tuo canale vocale.")
async def join_slash(interaction: discord.Interaction):
    if not interaction.user.voice:
        return await interaction.response.send_message("Devi essere in un canale vocale per usare questo comando.", ephemeral=True)

    voice_channel = interaction.user.voice.channel
    
    if interaction.guild.voice_client:
        if interaction.guild.voice_client.channel == voice_channel:
            return await interaction.response.send_message("Sono già in questo canale vocale.", ephemeral=True)
        else:
            await interaction.guild.voice_client.move_to(voice_channel)
    else:
        await voice_channel.connect()

    await interaction.response.send_message(f"🎶 Mi sono unito a {voice_channel.mention}!", ephemeral=False)


@bot.tree.command(name="leave", description="Il bot lascia il canale vocale.")
async def leave_slash(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        # Ferma la riproduzione prima di disconnettersi
        if interaction.guild.voice_client.is_playing():
             interaction.guild.voice_client.stop()
        
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("👋 Ho lasciato il canale vocale.", ephemeral=False)
    else:
        await interaction.response.send_message("Non sono in nessun canale vocale.", ephemeral=True)


@bot.tree.command(name="play", description="Riproduce un brano (RICHIESTA FFmpeg esterno).")
@app_commands.describe(
    source="Il percorso locale o URL (richiede yt-dlp) del brano da riprodurre."
)
async def play_slash(interaction: discord.Interaction, source: str):
    await interaction.response.defer() 

    if not interaction.user.voice:
        return await interaction.followup.send("Devi essere in un canale vocale per riprodurre musica.")

    # Connessione al canale vocale
    voice_channel = interaction.user.voice.channel
    voice_client = interaction.guild.voice_client

    if not voice_client:
        # Se non è connesso, si connette
        voice_client = await voice_channel.connect()
    elif voice_client.channel != voice_channel:
        # Se è in un altro canale, si sposta
        await voice_client.move_to(voice_channel)

    if voice_client.is_playing():
        voice_client.stop()

    try:
        # --- ATTENZIONE: NECESSITA FFmpeg ESTERNO ---
        # Questa sezione del codice *funzionerà* solo se:
        # 1. Hai installato il programma FFmpeg sul tuo sistema e si trova nel PATH.
        # 2. La 'source' è un percorso valido a un file audio locale (es. 'canzone.mp3')
        #    oppure, se è un URL, hai installato anche 'yt-dlp' e la sorgente è gestibile.
        
        # Opzioni di base per FFmpeg
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn' # -vn ignora i dati video
        }
        
        # Crea la sorgente audio
        audio_source = FFmpegPCMAudio(source, **ffmpeg_options)
        
        voice_client.play(audio_source, after=lambda e: print(f'Errore stream: {e}') if e else None)

        await interaction.followup.send(
            f"▶️ Avvio riproduzione di `{source}` in {voice_channel.mention}."
            "\n**ATTENZIONE:** Se non senti nulla, il tuo sistema deve avere `FFmpeg` installato."
        )

    except Exception as e:
        print(f"Errore di riproduzione audio: {e}")
        await interaction.followup.send(
            f"❌ Errore durante l'avvio della riproduzione.\n"
            f"Causa: `{e}`\n"
            "Verifica che `FFmpeg` sia installato e che la sorgente sia valida (es. un percorso locale .mp3)."
        )


@bot.tree.command(name="stop", description="Ferma la riproduzione in corso.")
async def stop_slash(interaction: discord.Interaction):
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("⏹ Riproduzione interrotta.", ephemeral=False)
    else:
        await interaction.response.send_message("Nessuna riproduzione in corso.", ephemeral=True)


# ======================
# COMANDI GENERALI AGGIUNTIVI
# ======================

@bot.tree.command(name="message", description="Invia un messaggio embed senza bordo colorato. (Solo Staff)")
@app_commands.describe(
    titolo="Il titolo del messaggio embed.",
    messaggio="Il contenuto principale del messaggio."
)
@app_commands.checks.has_role(STAFF_ROLE_NAME)
async def message_slash(interaction: discord.Interaction, titolo: str, messaggio: str):
    embed = discord.Embed(
        title=titolo,
        description=messaggio,
        color=discord.Color.default()
    )

    await interaction.response.send_message("✅ Messaggio inviato!", ephemeral=True)
    await interaction.channel.send(embed=embed)


# ======================
# COMANDI PREFIX (LEGACY)
# ======================

@bot.command(name="asas", help="Comando segreto che rivela un messaggio a sorpresa.")
async def asas_command(ctx):
    """
    Gestisce il comando prefix !asas e risponde con un messaggio innocuo.
    """
    if ctx.author.bot:
        return # Ignora i messaggi dai bot
        
    # Risposta innocua e scherzosa
    await ctx.send(f"Comando segreto `!asas` attivato. Benvenuto nella zona misteriosa, {ctx.author.mention}! 🕵️")


# ======================
# BOT RUN
# ======================

try:
    bot.run("MTQ0NzU2MDAwOTE1MDg4OTk4NA.G0blwK.5_UWlEf-TZLITyq3YXApmci2zoqiMiRSz7XvpI")
except Exception as e:
    print(f"\nERRORE: Impossibile avviare il bot.")
    print(f"Dettaglio errore: {e}")