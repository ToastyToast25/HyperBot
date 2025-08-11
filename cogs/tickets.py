# cogs/tickets.py - Enhanced for dual business models
import discord
from discord.ext import commands
from discord import ui
import datetime
import asyncio
import io
import json
from typing import Optional, Dict, Any

class TicketModal(ui.Modal):
    """Enhanced ticket creation modal with business model validation"""
    
    def __init__(self, category: str, tickets_cog):
        super().__init__(title=f"Create {category} Ticket")
        self.category = category
        self.tickets_cog = tickets_cog
        
        # Dynamic form based on category
        if category.lower() in ["bug report", "bug"]:
            self.title_input = ui.TextInput(
                label="Bug Title",
                placeholder="Brief description of the bug...",
                max_length=100,
                required=True
            )
            self.description_input = ui.TextInput(
                label="Bug Description",
                placeholder="Detailed description of the bug, steps to reproduce, expected vs actual behavior...",
                style=discord.TextStyle.paragraph,
                max_length=2000,
                required=True
            )
        elif category.lower() in ["feature request", "suggestion"]:
            self.title_input = ui.TextInput(
                label="Feature Title",
                placeholder="Brief description of the feature...",
                max_length=100,
                required=True
            )
            self.description_input = ui.TextInput(
                label="Feature Description",
                placeholder="Detailed description of the requested feature and why it would be useful...",
                style=discord.TextStyle.paragraph,
                max_length=2000,
                required=True
            )
        else:
            self.title_input = ui.TextInput(
                label="Ticket Title",
                placeholder="Brief description of your issue...",
                max_length=100,
                required=True
            )
            self.description_input = ui.TextInput(
                label="Description",
                placeholder="Please provide a detailed description of your issue...",
                style=discord.TextStyle.paragraph,
                max_length=2000,
                required=True
            )
        
        self.add_item(self.title_input)
        self.add_item(self.description_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle ticket creation with enhanced validation"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Business model validation
            bot = interaction.client
            
            # Check feature access
            if not await bot.check_feature_access(interaction.guild.id, 'tickets'):
                embed = discord.Embed(
                    title="🔒 Feature Not Available",
                    description="Ticket creation is not available with your current subscription/license.",
                    color=0xFF6B6B
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Check usage limits
            if bot.config.is_hosted_model():
                usage_stats = await bot._get_usage_stats(interaction.guild.id)
                subscription = await bot.db.get_guild_subscription(interaction.guild.id)
                
                if subscription:
                    max_tickets = subscription.get('features', {}).get('max_tickets', 0)
                    if max_tickets > 0 and usage_stats['total_tickets'] >= max_tickets:
                        embed = discord.Embed(
                            title="📝 Monthly Limit Reached",
                            description=f"You've reached your monthly limit of **{max_tickets} tickets**.",
                            color=0xFF6B6B
                        )
                        embed.add_field(
                            name="💎 Upgrade for More Tickets",
                            value="Use `/subscribe` to upgrade your plan",
                            inline=False
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        return
            
            else:
                # Self-hosted license check
                license_manager = bot.get_cog('LicenseManager')
                if license_manager:
                    usage_stats = await license_manager.get_usage_stats()
                    max_tickets = license_manager.get_feature_limit('max_tickets')
                    
                    if max_tickets > 0 and usage_stats['total_tickets'] >= max_tickets:
                        embed = discord.Embed(
                            title="📝 Monthly Limit Reached",
                            description=f"You've reached your monthly limit of **{max_tickets} tickets**.",
                            color=0xFF6B6B
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        return
            
            # Create the ticket
            result = await self.tickets_cog.create_ticket(
                interaction=interaction,
                category=self.category,
                title=self.title_input.value,
                description=self.description_input.value
            )
            
            if result['success']:
                embed = discord.Embed(
                    title="✅ Ticket Created",
                    description=f"Your ticket has been created: {result['channel'].mention}",
                    color=0x00FF00
                )
                embed.add_field(
                    name="Ticket Number",
                    value=f"#{result['ticket_number']}",
                    inline=True
                )
                embed.add_field(
                    name="Category",
                    value=self.category,
                    inline=True
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(
                    title="❌ Ticket Creation Failed",
                    description=result.get('error', 'Unknown error occurred'),
                    color=0xFF0000
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"An unexpected error occurred: {str(e)}",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

class TicketCog(commands.Cog):
    """Enhanced ticket management system with multi-tenant support"""
    
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.db = bot.db
    
    def is_staff(self, user: discord.Member) -> bool:
        """Check if user is staff"""
        config = self.bot.get_guild_config(user.guild.id)
        staff_roles = [
            config.get('roles', {}).get('admin'),
            config.get('roles', {}).get('moderator'), 
            config.get('roles', {}).get('support')
        ]
        
        user_role_ids = [role.id for role in user.roles]
        return any(role_id in user_role_ids for role_id in staff_roles if role_id)
    
    def is_admin(self, user: discord.Member) -> bool:
        """Check if user is admin"""
        config = self.bot.get_guild_config(user.guild.id)
        admin_role_id = config.get('roles', {}).get('admin')
        
        if admin_role_id:
            return any(role.id == int(admin_role_id) for role in user.roles)
        return user.guild_permissions.administrator
    
    async def create_ticket(self, interaction: discord.Interaction, category: str, title: str, description: str) -> Dict[str, Any]:
        """Create a new ticket with multi-tenant support"""
        try:
            guild = interaction.guild
            user = interaction.user
            
            # Get guild-specific configuration
            config = self.bot.get_guild_config(guild.id)
            
            # Get ticket category channel
            tickets_category_id = config.get('categories', {}).get('tickets')
            if not tickets_category_id:
                return {'success': False, 'error': 'Ticket category not configured'}
            
            tickets_category = guild.get_channel(int(tickets_category_id))
            if not tickets_category:
                return {'success': False, 'error': 'Ticket category not found'}
            
            # Generate ticket number and create database entry
            if self.config.is_hosted_model():
                # Multi-tenant ticket creation
                ticket_id = await self.db.create_ticket(
                    guild_id=guild.id,
                    discord_id=0,  # Will be updated after channel creation
                    user_id=user.id,
                    username=user.name,
                    display_name=user.display_name,
                    ticket_type='ticket',
                    category=category,
                    title=title,
                    description=description
                )
                
                # Get ticket number for this guild
                ticket_number = await self.db._get_next_ticket_number(guild.id) - 1  # Subtract 1 since we just created it
            else:
                # Single-tenant ticket creation
                ticket_id = await self.db.create_ticket(
                    discord_id=0,  # Will be updated after channel creation
                    user_id=user.id,
                    username=user.name,
                    display_name=user.display_name,
                    ticket_type='ticket',
                    category=category,
                    title=title,
                    description=description
                )
                
                # Get ticket number
                ticket_number = await self.db._get_next_ticket_number() - 1
            
            # Create channel name
            clean_title = ''.join(c for c in title if c.isalnum() or c in ' -_').strip()
            clean_title = clean_title.replace(' ', '-').lower()[:20]
            channel_name = f"ticket-{ticket_number}-{clean_title}"
            
            # Set up channel permissions
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                user: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_messages=True,
                    add_reactions=True,
                    attach_files=True
                ),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_messages=True,
                    manage_messages=True,
                    embed_links=True,
                    attach_files=True
                )
            }
            
            # Add staff role permissions
            staff_roles = [
                config.get('roles', {}).get('admin'),
                config.get('roles', {}).get('moderator'),
                config.get('roles', {}).get('support')
            ]
            
            for role_id in staff_roles:
                if role_id:
                    role = guild.get_role(int(role_id))
                    if role:
                        overwrites[role] = discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=True,
                            read_messages=True,
                            manage_messages=True
                        )
            
            # Create the channel
            channel = await guild.create_text_channel(
                name=channel_name,
                category=tickets_category,
                overwrites=overwrites,
                topic=f"Ticket #{ticket_number} | {category} | Created by {user.display_name}"
            )
            
            # Update database with channel ID
            if self.config.is_hosted_model():
                await self.db.execute_query(
                    "UPDATE tickets SET discord_id = %s WHERE id = %s",
                    (channel.id, ticket_id)
                )
            else:
                await self.db.execute_query(
                    "UPDATE tickets SET discord_id = ? WHERE id = ?",
                    (channel.id, ticket_id)
                )
            
            # Create ticket embed
            embed = discord.Embed(
                title=f"🎫 Ticket #{ticket_number}",
                description=f"**Category:** {category}\n**Title:** {title}",
                color=0x0099FF,
                timestamp=datetime.datetime.now()
            )
            
            embed.add_field(
                name="📝 Description",
                value=description[:1024] + ("..." if len(description) > 1024 else ""),
                inline=False
            )
            
            embed.add_field(
                name="👤 Created by",
                value=user.mention,
                inline=True
            )
            
            embed.add_field(
                name="📅 Created at",
                value=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
                inline=True
            )
            
            embed.set_footer(text="Use the buttons below to manage this ticket")
            embed.set_thumbnail(url=user.display_avatar.url)
            
            # Add persistent ticket management buttons
            view = self.bot.get_persistent_ticket_buttons()
            
            # Send the ticket embed
            await channel.send(f"Hello {user.mention}! Your ticket has been created.", embed=embed, view=view)
            
            # Send welcome message
            welcome_embed = discord.Embed(
                title="🎯 How to Use This Ticket",
                description="A staff member will respond to your ticket shortly. In the meantime:",
                color=0x00FF00
            )
            
            welcome_embed.add_field(
                name="📋 Provide Details",
                value="• Add any screenshots or files that might help\n• Include error messages if applicable\n• Describe steps you've already tried",
                inline=False
            )
            
            welcome_embed.add_field(
                name="⏰ Response Time",
                value="• Most tickets are answered within 24 hours\n• Urgent issues are prioritized\n• You'll be notified of any updates",
                inline=False
            )
            
            await channel.send(embed=welcome_embed)
            
            # Update statistics if available
            if hasattr(self.bot, 'stats_events'):
                await self.bot.stats_events.on_ticket_created({
                    'id': ticket_id,
                    'ticket_number': ticket_number,
                    'user_id': user.id,
                    'guild_id': guild.id,
                    'category': category,
                    'title': title,
                    'channel_id': channel.id,
                    'created_at': datetime.datetime.now().isoformat()
                })
            
            # Report usage analytics
            await self.bot._report_usage("ticket_created", {
                "category": category,
                "user_id": user.id,
                "guild_id": guild.id,
                "ticket_number": ticket_number
            })
            
            return {
                'success': True,
                'channel': channel,
                'ticket_number': ticket_number,
                'ticket_id': ticket_id
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def close_channel(self, channel: discord.TextChannel, user: discord.Member):
        """Close a ticket channel with transcript generation"""
        try:
            # Get ticket data
            if self.config.is_hosted_model():
                ticket_data = await self.db.execute_query(
                    "SELECT * FROM tickets WHERE discord_id = %s AND guild_id = %s",
                    (channel.id, channel.guild.id)
                )
            else:
                ticket_data = await self.db.execute_query(
                    "SELECT * FROM tickets WHERE discord_id = ?",
                    (channel.id,)
                )
            
            if not ticket_data:
                await channel.send("❌ Could not find ticket data for transcript generation.")
                return
            
            ticket_info = ticket_data[0] if ticket_data else {}
            
            # Generate transcript
            transcript = await self._generate_transcript(channel, ticket_info)
            
            # Update database
            if self.config.is_hosted_model():
                await self.db.execute_query(
                    "UPDATE tickets SET status = 'closed', closed_at = NOW() WHERE discord_id = %s",
                    (channel.id,)
                )
            else:
                await self.db.execute_query(
                    "UPDATE tickets SET status = 'closed', closed_at = CURRENT_TIMESTAMP WHERE discord_id = ?",
                    (channel.id,)
                )
            
            # Send transcript to user
            try:
                transcript_file = discord.File(
                    io.StringIO(transcript),
                    filename=f"ticket-{ticket_info.get('ticket_number', 'unknown')}-transcript.txt"
                )
                
                embed = discord.Embed(
                    title="🎫 Ticket Closed",
                    description=f"Your ticket **#{ticket_info.get('ticket_number', 'Unknown')}** has been closed.",
                    color=0x808080
                )
                embed.add_field(
                    name="📄 Transcript",
                    value="A full transcript of your ticket conversation is attached.",
                    inline=False
                )
                embed.set_footer(text="Thank you for using our ticket system!")
                
                await user.send(embed=embed, file=transcript_file)
                
            except discord.HTTPException:
                # If DM fails, try to send to a logs channel
                config = self.bot.get_guild_config(channel.guild.id)
                logs_channel_id = config.get('channels', {}).get('logs')
                
                if logs_channel_id:
                    logs_channel = channel.guild.get_channel(int(logs_channel_id))
                    if logs_channel:
                        transcript_file = discord.File(
                            io.StringIO(transcript),
                            filename=f"ticket-{ticket_info.get('ticket_number', 'unknown')}-transcript.txt"
                        )
                        
                        embed = discord.Embed(
                            title="📄 Ticket Transcript",
                            description=f"Transcript for ticket #{ticket_info.get('ticket_number', 'Unknown')} (user could not be DMed)",
                            color=0x808080
                        )
                        
                        await logs_channel.send(embed=embed, file=transcript_file)
            
            # Delete the channel after a short delay
            await asyncio.sleep(5)
            await channel.delete(reason="Ticket closed and transcript generated")
            
        except Exception as e:
            await channel.send(f"❌ Error closing ticket: {str(e)}")
    
    async def _generate_transcript(self, channel: discord.TextChannel, ticket_info: dict) -> str:
        """Generate a text transcript of the ticket conversation"""
        transcript_lines = []
        
        # Header
        transcript_lines.append("=" * 60)
        transcript_lines.append(f"TICKET TRANSCRIPT")
        transcript_lines.append("=" * 60)
        transcript_lines.append(f"Ticket Number: #{ticket_info.get('ticket_number', 'Unknown')}")
        transcript_lines.append(f"Category: {ticket_info.get('category', 'Unknown')}")
        transcript_lines.append(f"Title: {ticket_info.get('title', 'Unknown')}")
        transcript_lines.append(f"Created by: {ticket_info.get('username', 'Unknown')} (ID: {ticket_info.get('user_id', 'Unknown')})")
        transcript_lines.append(f"Created at: {ticket_info.get('created_at', 'Unknown')}")
        transcript_lines.append(f"Channel: #{channel.name}")
        transcript_lines.append("-" * 60)
        transcript_lines.append("")
        
        # Messages
        try:
            async for message in channel.history(limit=None, oldest_first=True):
                timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                author = f"{message.author.display_name} ({message.author.name}#{message.author.discriminator})"
                
                transcript_lines.append(f"[{timestamp}] {author}:")
                
                if message.content:
                    # Split long messages into multiple lines
                    content_lines = message.content.split('\n')
                    for line in content_lines:
                        transcript_lines.append(f"  {line}")
                
                if message.attachments:
                    for attachment in message.attachments:
                        transcript_lines.append(f"  [ATTACHMENT: {attachment.filename} - {attachment.url}]")
                
                if message.embeds:
                    for embed in message.embeds:
                        transcript_lines.append(f"  [EMBED: {embed.title or 'No Title'}]")
                        if embed.description:
                            transcript_lines.append(f"    {embed.description[:200]}...")
                
                transcript_lines.append("")
                
        except Exception as e:
            transcript_lines.append(f"Error retrieving messages: {str(e)}")
        
        # Footer
        transcript_lines.append("-" * 60)
        transcript_lines.append(f"Transcript generated at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        transcript_lines.append("=" * 60)
        
        return '\n'.join(transcript_lines)
    
    @commands.slash_command(name="setup_panel", description="Create ticket creation panel")
    @commands.has_permissions(administrator=True)
    async def setup_panel(self, ctx):
        """Create the main ticket creation panel"""
        try:
            # Check feature access
            if not await self.bot.check_feature_access(ctx.guild.id, 'tickets'):
                await ctx.respond("❌ Ticket system not available with current subscription/license.", ephemeral=True)
                return
            
            # Get categories from database
            categories = await self.db.get_categories() if hasattr(self.db, 'get_categories') else []
            
            if not categories:
                # Create default categories
                categories = ["General Support", "Bug Report", "Feature Request", "Billing Issue"]
                if hasattr(self.db, 'add_category'):
                    for category in categories:
                        await self.db.add_category(category)
            
            embed = discord.Embed(
                title="🎫 Create a Ticket",
                description="Select a category below to create a new support ticket. Our team will respond as soon as possible!",
                color=0x0099FF
            )
            
            embed.add_field(
                name="📋 Available Categories",
                value="\n".join([f"• {cat}" for cat in categories]),
                inline=False
            )
            
            embed.add_field(
                name="⏱️ Response Time",
                value="• Most tickets answered within 24 hours\n• Urgent issues are prioritized\n• You'll receive updates via DM",
                inline=False
            )
            
            embed.set_footer(text="HyperTicky Pro - Professional Ticket Management")
            
            from main import CommercialPersistentCategoryView
            view = CommercialPersistentCategoryView()
            
            # Update view with fresh categories
            select = view.children[0]
            select.options = [
                discord.SelectOption(
                    label=cat,
                    value=cat,
                    description=f"Create a {cat.lower()} ticket"
                ) for cat in categories
            ]
            
            await ctx.respond(embed=embed, view=view)
            
        except Exception as e:
            await ctx.respond(f"❌ Error creating panel: {str(e)}", ephemeral=True)
    
    @commands.slash_command(name="ticket_stats", description="View ticket statistics")
    async def ticket_stats(self, ctx):
        """Display ticket statistics"""
        try:
            if self.config.is_hosted_model():
                usage_stats = await self.bot._get_usage_stats(ctx.guild.id)
                subscription = await self.db.get_guild_subscription(ctx.guild.id)
                
                embed = discord.Embed(
                    title="📊 Ticket Statistics",
                    color=0x0099FF
                )
                
                embed.add_field(
                    name="📝 This Month",
                    value=f"Total: {usage_stats['total_tickets']}\nTickets: {usage_stats['tickets']}\nReports: {usage_stats['reports']}",
                    inline=True
                )
                
                if subscription:
                    max_tickets = subscription.get('features', {}).get('max_tickets', 0)
                    if max_tickets > 0:
                        percentage = (usage_stats['total_tickets'] / max_tickets) * 100
                        embed.add_field(
                            name="📈 Usage",
                            value=f"{usage_stats['total_tickets']}/{max_tickets} ({percentage:.1f}%)",
                            inline=True
                        )
                    else:
                        embed.add_field(
                            name="📈 Usage",
                            value="Unlimited",
                            inline=True
                        )
                        
                    embed.add_field(
                        name="💎 Plan",
                        value=subscription['subscription_tier'].title(),
                        inline=True
                    )
            else:
                license_manager = self.bot.get_cog('LicenseManager')
                if license_manager:
                    usage_stats = await license_manager.get_usage_stats()
                    max_tickets = license_manager.get_feature_limit('max_tickets')
                    
                    embed = discord.Embed(
                        title="📊 Ticket Statistics",
                        color=0x0099FF
                    )
                    
                    embed.add_field(
                        name="📝 This Month",
                        value=f"Total: {usage_stats['total_tickets']}\nTickets: {usage_stats['tickets']}\nReports: {usage_stats['reports']}",
                        inline=True
                    )
                    
                    if max_tickets > 0:
                        percentage = (usage_stats['total_tickets'] / max_tickets) * 100
                        embed.add_field(
                            name="📈 Usage",
                            value=f"{usage_stats['total_tickets']}/{max_tickets} ({percentage:.1f}%)",
                            inline=True
                        )
                    else:
                        embed.add_field(
                            name="📈 Usage",
                            value="Unlimited",
                            inline=True
                        )
                else:
                    embed = discord.Embed(
                        title="❌ Statistics Unavailable",
                        description="License manager not available",
                        color=0xFF0000
                    )
            
            await ctx.respond(embed=embed, ephemeral=True)
            
        except Exception as e:
            await ctx.respond(f"❌ Error getting statistics: {str(e)}", ephemeral=True)

def setup(bot):
    bot.add_cog(TicketCog(bot))