import discord
from discord.ext import commands
from discord import app_commands
import json, os, random

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
registro_file = "registro.json"

# 🔐 Registro
if not os.path.exists(registro_file):
    with open(registro_file, "w") as f:
        json.dump({}, f)

def salva_registro(data):
    with open(registro_file, "w") as f:
        json.dump(data, f, indent=4)

def carica_registro():
    with open(registro_file, "r") as f:
        return json.load(f)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot attivo come {bot.user}")

# 👋 Welcome
@bot.event
async def on_member_join(member):
    registro = carica_registro()
    guild_data = registro.get(str(member.guild.id), {})
    benvenuto = guild_data.get("benvenuto")
    if benvenuto:
        canale = member.guild.get_channel(int(benvenuto))
        if canale:
            await canale.send(f"👋 Benvenuto {member.mention} nel server!")

@bot.tree.command(name="setwelcome", description="Imposta il canale di benvenuto")
@app_commands.describe(channel_id="ID del canale")
async def setwelcome(interaction: discord.Interaction, channel_id: str):
    registro = carica_registro()
    registro.setdefault(str(interaction.guild.id), {})["benvenuto"] = channel_id
    salva_registro(registro)
    await interaction.response.send_message("✅ Canale benvenuto impostato", ephemeral=True)

# 🎟️ Ticket
class TicketModal(discord.ui.Modal, title="Apri un Ticket"):
    descrizione = discord.ui.TextInput(label="Descrivi il tuo problema", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        registro = carica_registro()
        guild_data = registro.get(str(interaction.guild.id), {})
        cat_id = guild_data.get("ticket_category")
        log_id = guild_data.get("ticket_log")

        if not cat_id:
            await interaction.response.send_message("⚠️ Categoria ticket non impostata.", ephemeral=True)
            return

        category = discord.utils.get(interaction.guild.categories, id=int(cat_id))
        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=category,
            overwrites={
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }
        )
        await channel.send(f"🎫 Ticket aperto da {interaction.user.mention}\n**Descrizione:** {self.descrizione}")
        await interaction.response.send_message(f"✅ Ticket creato: {channel.mention}", ephemeral=True)

        if log_id:
            log_channel = interaction.guild.get_channel(int(log_id))
            if log_channel:
                await log_channel.send(f"📥 Ticket da {interaction.user.mention}:\n{self.descrizione}")

class TicketPanel(discord.ui.View):
    @discord.ui.button(label="🎟️ Apri Ticket", style=discord.ButtonStyle.primary)
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketModal())

@bot.tree.command(name="ticketpanel", description="Invia il pannello per aprire ticket")
async def ticketpanel(interaction: discord.Interaction):
    await interaction.channel.send("📩 Clicca per aprire un ticket:", view=TicketPanel())
    await interaction.response.send_message("✅ Pannello inviato", ephemeral=True)

@bot.tree.command(name="setticket", description="Imposta categoria e log ticket")
@app_commands.describe(category_id="ID categoria", log_channel_id="ID canale log")
async def setticket(interaction: discord.Interaction, category_id: str, log_channel_id: str):
    registro = carica_registro()
    registro.setdefault(str(interaction.guild.id), {})["ticket_category"] = category_id
    registro[str(interaction.guild.id)]["ticket_log"] = log_channel_id
    salva_registro(registro)
    await interaction.response.send_message("✅ Ticket configurato", ephemeral=True)

# 🔨 Moderazione
@bot.tree.command(name="ban", description="Banna un utente")
@app_commands.describe(user="Utente da bannare")
async def ban(interaction: discord.Interaction, user: discord.Member):
    await user.ban()
    await interaction.response.send_message(f"🔨 {user} è stato bannato.")

@bot.tree.command(name="kick", description="Espelli un utente")
@app_commands.describe(user="Utente da espellere")
async def kick(interaction: discord.Interaction, user: discord.Member):
    await user.kick()
    await interaction.response.send_message(f"👢 {user} è stato espulso.")

@bot.tree.command(name="warn", description="Avvisa un utente")
@app_commands.describe(user="Utente da avvisare", motivo="Motivo dell'avviso")
async def warn(interaction: discord.Interaction, user: discord.Member, motivo: str):
    registro = carica_registro()
    guild_id = str(interaction.guild.id)
    registro.setdefault(guild_id, {}).setdefault("warns", {}).setdefault(str(user.id), []).append(motivo)
    salva_registro(registro)
    await interaction.response.send_message(f"⚠️ {user.mention} è stato avvisato per: {motivo}")

@bot.tree.command(name="mute", description="Mutare un utente")
@app_commands.describe(user="Utente da mutare")
async def mute(interaction: discord.Interaction, user: discord.Member):
    await user.edit(mute=True)
    await interaction.response.send_message(f"🔇 {user} è stato mutato.")

# 🤝 Partnership
class PartnershipView(discord.ui.View):
    def __init__(self, user, descrizione):
        super().__init__(timeout=None)
        self.user = user
        self.descrizione = descrizione

    @discord.ui.button(label="✅ Approva", style=discord.ButtonStyle.success)
    async def approva(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"🤝 Partnership approvata per {self.user.mention}")
        await self.user.send(f"🎉 La tua partnership è stata approvata!\n{self.descrizione}")
        self.stop()

    @discord.ui.button(label="❌ Rifiuta", style=discord.ButtonStyle.danger)
    async def rifiuta(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"❌ Partnership rifiutata per {self.user.mention}")
        await self.user.send("😔 La tua partnership è stata rifiutata.")
        self.stop()

@bot.tree.command(name="partnership", description="Richiedi una partnership")
@app_commands.describe(descrizione="Descrivi la tua proposta")
async def partnership(interaction: discord.Interaction, descrizione: str):
    registro = carica_registro()
    guild_data = registro.get(str(interaction.guild.id), {})
    log_id = guild_data.get("partnership_log")

    if not log_id:
        await interaction.response.send_message("⚠️ Canale partnership non impostato.", ephemeral=True)
        return

    log_channel = interaction.guild.get_channel(int(log_id))
    if log_channel:
        await log_channel.send(
            f"📩 Richiesta partnership da {interaction.user.mention}:\n{descrizione}",
            view=PartnershipView(interaction.user, descrizione)
        )
        await interaction.response.send_message("✅ Richiesta inviata!", ephemeral=True)

@bot.tree.command(name="setpartnership", description="Imposta canale log partnership")
@app_commands.describe(channel_id="ID del canale")
async def setpartnership(interaction: discord.Interaction, channel_id: str):
    registro = carica_registro()
    registro.setdefault(str(interaction.guild.id), {})["partnership_log"] = channel_id
    salva_registro(registro)
    await interaction.response.send_message("✅ Canale partnership impostato", ephemeral=True)

# 🔗 Chain
@bot.tree.command(name="chain", description="Invia una serie di messaggi collegati")
@app_commands.describe(testo="Testo separato da |")
async def chain(interaction: discord.Interaction, testo: str):
    messaggi = testo.split("|")
    for msg in messaggi:
        await interaction.channel.send(msg.strip())
    await interaction.response.send_message("✅ Messaggi inviati", ephemeral=True)

# 🎮 Minigiochi
@bot.tree.command(name="guess", description="Indovina un numero tra 1 e 10")
@app_commands.describe(numero="Il tuo numero")
async def guess(interaction:

# 🔑 Avvia il bot
bot.run("MTQwMTg1MjYzMDk3OTg0MjEyOQ.G5ZUvV.qrDJyMiVvUYRwBzF1Q9nAH2GoKrP6zbs77HcaM")
