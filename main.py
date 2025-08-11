# main.py - HyperTicky Pro v2.0 - Enhanced Commercial Discord Ticket Bot
import discord
from discord.ext import commands
from discord import ui
import asyncio
import os
import sys
import traceback
from pathlib import Path
import datetime
import logging
from logging.handlers import RotatingFileHandler

# Set UTF-8 encoding for Windows compatibility
os.environ['PYTHONIOENCODING'] = 'utf-8'

# Import our enhanced commercial modules
from config import ConfigManager
from database import Database

def setup_logging():
    """Setup professional logging system with rotation"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s'
    )
    simple_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s'
    )
    
    # Create logs directory
    os.makedirs('logs', exist_ok=True)
    
    # File handler with rotation (10MB max, 5 backups)
    file_handler = RotatingFileHandler(
        'logs/hyperticky.log', 
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(detailed_formatter)
    
    # Console handler with UTF-8 encoding
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    
    # Set console encoding explicitly for Windows
    if hasattr(console_handler.stream, 'reconfigure'):
        console_handler.stream.reconfigure(encoding='utf-8', errors='replace')
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logging.getLogger(__name__)

# Initialize logger
logger = setup_logging()

# Enhanced Persistent Views for Commercial Features
class CommercialPersistentCategorySelect(ui.Select):
    """Enhanced category select with business model validation"""
    
    def __init__(self):
        super().__init__(
            placeholder="Select a category to create ticket...",
            custom_id="persistent_category_select",
            options=[
                discord.SelectOption(
                    label="Loading categories...", 
                    value="loading", 
                    description="Please wait while categories load..."
                )
            ]
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle category selection with comprehensive validation"""
        try:
            bot = interaction.client
            
            # Business model validation
            if bot.config.is_hosted_model():
                # Check subscription status for hosted model
                subscription = await bot.db.get_guild_subscription(interaction.guild.id)
                if not subscription or subscription['status'] != 'active':
                    embed = discord.Embed(
                        title="🔒 Subscription Required",
                        description="Your server's subscription has expired or is inactive.",
                        color=0xFF6B6B
                    )
                    embed.add_field(
                        name="💎 Reactivate Subscription",
                        value="Use `/subscribe` to view available plans",
                        inline=False
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                # Check feature limits
                usage_stats = await bot._get_usage_stats(interaction.guild.id)
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
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                    
            else:
                # Check license for self-hosted model
                license_manager = bot.get_cog('LicenseManager')
                if license_manager and not license_manager.check_feature_access('tickets'):
                    embed = discord.Embed(
                        title="🔒 License Required",
                        description="Ticket creation requires a valid license.",
                        color=0xFF6B6B
                    )
                    embed.add_field(
                        name="💎 Get License",
                        value="Contact sales for licensing information",
                        inline=False
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
            
            # Rate limiting check
            if hasattr(bot, 'rate_limiter'):
                if bot.rate_limiter.is_rate_limited(interaction.user.id):
                    embed = discord.Embed(
                        title="⏰ Rate Limited",
                        description="You're creating tickets too quickly. Please wait before trying again.",
                        color=0xFFAA00
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
            
            # Get fresh categories from database
            categories = await bot.db.get_categories()
            
            # Update options if still loading
            if self.options[0].value == "loading":
                self.options = [
                    discord.SelectOption(
                        label=cat,
                        value=cat,
                        description=f"Create a {cat.lower()} ticket"
                    ) for cat in categories
                ]
            
            category = self.values[0]
            
            if category == "loading":
                await interaction.response.send_message(
                    "⏳ Categories are still loading, please try again in a moment.", 
                    ephemeral=True
                )
                return
            
            # Route to appropriate handler based on category
            if category == "Report Player":
                if not await bot.check_feature_access(interaction.guild.id, 'reports'):
                    embed = discord.Embed(
                        title="🔒 Premium Feature",
                        description="Player reporting requires a premium subscription or license.",
                        color=0xFF6B6B
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                    
                reports_cog = bot.get_cog("ReportsCog")
                if reports_cog:
                    from cogs.reports import ReportPlayerModal
                    await interaction.response.send_modal(ReportPlayerModal(category, reports_cog))
                else:
                    await interaction.response.send_message("❌ Reports system not available.", ephemeral=True)
                    
            elif category == "Report Mod Abuse":
                if not await bot.check_feature_access(interaction.guild.id, 'reports'):
                    embed = discord.Embed(
                        title="🔒 Premium Feature",
                        description="Mod abuse reporting requires a premium subscription or license.",
                        color=0xFF6B6B
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                    
                reports_cog = bot.get_cog("ReportsCog")
                if reports_cog:
                    from cogs.reports import ReportModAbuseModal
                    await interaction.response.send_modal(ReportModAbuseModal(category, reports_cog))
                else:
                    await interaction.response.send_message("❌ Reports system not available.", ephemeral=True)
                    
            else:
                # Regular ticket creation
                tickets_cog = bot.get_cog("TicketCog")
                if tickets_cog:
                    from cogs.tickets import TicketModal
                    await interaction.response.send_modal(TicketModal(category, tickets_cog))
                else:
                    await interaction.response.send_message("❌ Ticket system not available.", ephemeral=True)
            
            # Report usage analytics
            await bot._report_usage("ticket_creation_started", {
                "category": category,
                "user_id": interaction.user.id,
                "guild_id": interaction.guild.id
            })
                    
        except Exception as e:
            logger.error(f"Error in category selection: {e}")
            traceback.print_exc()
            
            embed = discord.Embed(
                title="❌ System Error",
                description="An unexpected error occurred. Please try again or contact support.",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

class CommercialPersistentCategoryView(ui.View):
    """Enhanced category view with timeout disabled"""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CommercialPersistentCategorySelect())

class EnhancedPersistentTicketButtons(ui.View):
    """Enhanced ticket management buttons with instant statistics updates"""
    
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="👤 Claim", style=discord.ButtonStyle.primary, custom_id="persistent_ticket_claim")
    async def claim(self, interaction: discord.Interaction, button: ui.Button):
        """Claim a ticket with staff validation"""
        tickets_cog = interaction.client.get_cog("TicketCog")
        if not tickets_cog or not tickets_cog.is_staff(interaction.user):
            await interaction.response.send_message("🚫 You don't have permission to claim tickets.", ephemeral=True)
            return
        
        ticket_data = await interaction.client.db.get_ticket(interaction.channel.id)
        if not ticket_data:
            await interaction.response.send_message("❌ No ticket data found for this channel.", ephemeral=True)
            return
        
        # Update database
        await interaction.client.db.update_ticket_status(interaction.channel.id, "claimed")
        await interaction.client.db.set_claimed_by(interaction.channel.id, interaction.user.id)
        
        ticket_type = ticket_data.get("type", "ticket")
        type_display = ticket_type.replace("_", " ").title()
        
        embed = discord.Embed(
            title="✅ Ticket Claimed",
            description=f"{type_display} has been claimed by {interaction.user.mention}",
            color=0x00FF00,
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text=f"Claimed by {interaction.user.display_name}")
        
        await interaction.response.send_message(embed=embed)
        
        # Trigger instant statistics update
        if hasattr(interaction.client, 'stats_events'):
            await interaction.client.stats_events.on_ticket_claimed({
                **ticket_data,
                "claimed_by": interaction.user.id,
                "claimed_at": datetime.datetime.now().isoformat()
            })
        
        # Notify user
        try:
            user = await interaction.client.fetch_user(ticket_data["user_id"])
            embed_dm = discord.Embed(
                title="📬 Ticket Update",
                description=f"Your {type_display.lower()} has been claimed by **{interaction.user.display_name}**.",
                color=0x00FF00
            )
            await user.send(embed=embed_dm)
        except:
            logger.warning(f"Could not notify user {ticket_data['user_id']} about ticket claim")

    @ui.button(label="✅ Resolve", style=discord.ButtonStyle.success, custom_id="persistent_ticket_resolve")
    async def resolve(self, interaction: discord.Interaction, button: ui.Button):
        """Resolve a ticket with instant statistics update"""
        tickets_cog = interaction.client.get_cog("TicketCog")
        if not tickets_cog or not tickets_cog.is_staff(interaction.user):
            await interaction.response.send_message("🚫 You don't have permission to resolve tickets.", ephemeral=True)
            return
        
        ticket_data = await interaction.client.db.get_ticket(interaction.channel.id)
        if not ticket_data:
            await interaction.response.send_message("❌ No ticket data found for this channel.", ephemeral=True)
            return
        
        # Update database
        await interaction.client.db.update_ticket_status(interaction.channel.id, "resolved")
        await interaction.client.db.set_resolved_by(interaction.channel.id, interaction.user.id)
        
        ticket_type = ticket_data.get("type", "ticket")
        type_display = ticket_type.replace("_", " ").title()
        
        embed = discord.Embed(
            title="✅ Ticket Resolved",
            description=f"{type_display} has been marked as **resolved** by {interaction.user.mention}",
            color=0x00FF00,
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text=f"Resolved by {interaction.user.display_name}")
        
        await interaction.response.send_message(embed=embed)
        
        # Trigger instant statistics update
        if hasattr(interaction.client, 'stats_events'):
            await interaction.client.stats_events.on_ticket_resolved({
                **ticket_data,
                "resolved_by": interaction.user.id,
                "resolved_at": datetime.datetime.now().isoformat()
            })

    @ui.button(label="🔒 Close", style=discord.ButtonStyle.danger, custom_id="persistent_ticket_close")
    async def close(self, interaction: discord.Interaction, button: ui.Button):
        """Close a ticket with transcript generation"""
        tickets_cog = interaction.client.get_cog("TicketCog")
        if not tickets_cog or not tickets_cog.is_staff(interaction.user):
            await interaction.response.send_message("🚫 You don't have permission to close tickets.", ephemeral=True)
            return
        
        ticket_data = await interaction.client.db.get_ticket(interaction.channel.id)
        if not ticket_data:
            await interaction.response.send_message("❌ No ticket data found for this channel.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            user = await interaction.client.fetch_user(ticket_data["user_id"])
            await tickets_cog.close_channel(interaction.channel, user)
            
            # Trigger instant statistics update
            if hasattr(interaction.client, 'stats_events'):
                await interaction.client.stats_events.on_ticket_closed({
                    **ticket_data,
                    "closed_by": interaction.user.id,
                    "closed_at": datetime.datetime.now().isoformat()
                })
            
        except Exception as e:
            logger.error(f"Error closing ticket: {e}")
            await interaction.followup.send(f"❌ Error closing ticket: {str(e)}", ephemeral=True)

    @ui.button(label="🔄 Reopen", style=discord.ButtonStyle.secondary, custom_id="persistent_ticket_reopen")
    async def reopen(self, interaction: discord.Interaction, button: ui.Button):
        """Reopen a closed ticket (admin only)"""
        tickets_cog = interaction.client.get_cog("TicketCog")
        if not tickets_cog or not tickets_cog.is_admin(interaction.user):
            await interaction.response.send_message("🚫 Only administrators can reopen tickets.", ephemeral=True)
            return
        
        ticket_data = await interaction.client.db.get_ticket(interaction.channel.id)
        if not ticket_data:
            await interaction.response.send_message("❌ No ticket data found for this channel.", ephemeral=True)
            return
        
        user = interaction.guild.get_member(ticket_data["user_id"])
        if user:
            # Restore user permissions
            overwrites = interaction.channel.overwrites
            overwrites[user] = discord.PermissionOverwrite(
                view_channel=True, 
                send_messages=True, 
                read_messages=True,
                add_reactions=True,
                attach_files=True
            )
            await interaction.channel.edit(overwrites=overwrites)
            
            # Update database
            await interaction.client.db.update_ticket_status(interaction.channel.id, "open")
            
            embed = discord.Embed(
                title="🔄 Ticket Reopened",
                description=f"Ticket has been reopened by {interaction.user.mention}",
                color=0x0099FF,
                timestamp=datetime.datetime.now()
            )
            
            await interaction.response.send_message(embed=embed)

class CommercialPersistentStaffApply(ui.View):
    """Enhanced staff application system with business validation"""
    
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="💼 Apply for Staff", style=discord.ButtonStyle.primary, custom_id="persistent_staff_apply")
    async def apply_now(self, interaction: discord.Interaction, button: ui.Button):
        """Handle staff application with feature check"""
        # Check feature access
        if not await interaction.client.check_feature_access(interaction.guild.id, 'applications'):
            embed = discord.Embed(
                title="🔒 Premium Feature",
                description="Staff applications require a premium subscription or license.",
                color=0xFF6B6B
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        applications_cog = interaction.client.get_cog("ApplicationsCog")
        if not applications_cog:
            await interaction.response.send_message("❌ Applications system not available.", ephemeral=True)
            return
            
        open_positions = await interaction.client.db.get_open_positions()
        if not open_positions:
            embed = discord.Embed(
                title="📋 No Open Positions",
                description="There are currently no open staff positions.",
                color=0xFFAA00
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        from cogs.applications import PositionSelect
        view = ui.View()
        view.add_item(PositionSelect(open_positions, applications_cog))
        
        embed = discord.Embed(
            title="💼 Staff Application",
            description=f"Select from **{len(open_positions)}** available position(s):",
            color=0x0099FF
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class CommercialPersistentSuggestion(ui.View):
    """Enhanced suggestion system with business validation"""
    
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="💡 Submit Suggestion", style=discord.ButtonStyle.primary, custom_id="persistent_suggestion")
    async def suggest(self, interaction: discord.Interaction, button: ui.Button):
        """Handle suggestion submission with feature check"""
        # Check feature access
        if not await interaction.client.check_feature_access(interaction.guild.id, 'suggestions'):
            embed = discord.Embed(
                title="🔒 Premium Feature",
                description="Community suggestions require a premium subscription or license.",
                color=0xFF6B6B
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        suggestions_cog = interaction.client.get_cog("SuggestionsCog")
        if not suggestions_cog:
            await interaction.response.send_message("❌ Suggestions system not available.", ephemeral=True)
            return
            
        from cogs.suggestions import SuggestionModal
        await interaction.response.send_modal(SuggestionModal(suggestions_cog))

class HyperTicky(commands.Bot):
    """
    HyperTicky Pro - Commercial Discord Ticket Bot
    Enhanced Version 2.0 with Dual Business Models
    """
    
    def __init__(self):
        # Initialize configuration manager first
        try:
            self.config = ConfigManager()
            logger.info(f"✅ Configuration loaded - Business Model: {self.config.business_model}")
        except Exception as e:
            logger.error(f"❌ Configuration error: {e}")
            sys.exit(1)
        
        # Set up bot intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.guild_messages = True
        intents.guild_reactions = True
        intents.members = True
        
        # Initialize bot with appropriate settings based on business model
        if self.config.is_hosted_model():
            # Multi-guild support for hosted model
            super().__init__(
                command_prefix=self.config.get('prefix', ['!ht.', '!hyperticky.']),
                intents=intents,
                help_command=None,
                case_insensitive=True,
                strip_after_prefix=True
            )
            logger.info("🌐 Initialized in HOSTED mode (multi-guild)")
        else:
            # Single guild for self-hosted
            guild_id = self.config.get('guild_id')
            if guild_id:
                super().__init__(
                    command_prefix=self.config.get('prefix', ['!ht.', '!hyperticky.']),
                    intents=intents,
                    help_command=None,
                    case_insensitive=True,
                    strip_after_prefix=True,
                    debug_guilds=[int(guild_id)]  # Faster slash command sync
                )
                logger.info(f"🏠 Initialized in SELF-HOSTED mode (guild: {guild_id})")
            else:
                logger.error("❌ guild_id required for self-hosted mode")
                sys.exit(1)
        
        # Bot metadata
        self.version = "2.0.0"
        self.startup_time = datetime.datetime.now()
        self.shutdown_initiated = False
        
        # Performance tracking
        self.command_count = 0
        self.error_count = 0
        
        # Database will be initialized in setup_hook
        self.db = None
        
        # Rate limiter for security
        self.rate_limiter = RateLimiter() if hasattr(self, 'RateLimiter') else None
        
        # Track loaded cogs
        self.business_cogs = []
        self.synced = False
        
        # Add persistent views
        self.add_persistent_views()
        
        logger.info("✅ HyperTicky Pro initialized successfully")
    
    def add_persistent_views(self):
        """Add commercial persistent views with enhanced features"""
        try:
            self.add_view(CommercialPersistentCategoryView())
            self.add_view(EnhancedPersistentTicketButtons())
            self.add_view(CommercialPersistentStaffApply())
            self.add_view(CommercialPersistentSuggestion())
            logger.info("✅ Commercial persistent views registered")
        except Exception as e:
            logger.error(f"❌ Failed to add persistent views: {e}")
    
    async def setup_hook(self):
        """Enhanced setup process with comprehensive validation"""
        logger.info("🚀 Starting HyperTicky Pro setup process...")
        
        # Step 1: Initialize Database
        await self._initialize_database()
        
        # Step 2: Business Model Validation
        await self._validate_business_model()
        
        # Step 3: Load Business-Specific Cogs
        await self._load_business_cogs()
        
        # Step 4: Setup Event Systems
        await self._setup_event_systems()
        
        # Step 5: Update UI Components
        await self._update_ui_components()
        
        logger.info("🎯 HyperTicky Pro setup completed successfully")
    
    async def _initialize_database(self):
        """Initialize database with error handling"""
        try:
            logger.info("🗄️ Initializing database...")
            self.db = Database(self.config.config)
            await self.db.connect()
            logger.info(f"✅ Database connected ({self.config.business_model} mode)")
            
            # Test database connectivity
            if self.config.is_hosted_model():
                test_query = "SELECT 1 as test"
                result = await self.db.execute_query(test_query)
                if result:
                    logger.info("✅ Multi-tenant database functionality verified")
            else:
                # SQLite test
                test_query = "SELECT 1 as test"
                result = await self.db.execute_query(test_query)
                if result:
                    logger.info("✅ Single-tenant database functionality verified")
                
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            logger.error("Bot cannot start without database. Please check your configuration.")
            await self.close()
            raise
    
    async def _validate_business_model(self):
        """Validate business model configuration"""
        try:
            if self.config.is_hosted_model():
                logger.info("🔐 Validating hosted service configuration...")
                
                # Check Stripe configuration
                stripe_key = self.config.get('stripe.secret_key')
                if not stripe_key or stripe_key == 'sk_test_your_stripe_secret_key':
                    logger.warning("⚠️ Stripe not configured - subscription features disabled")
                else:
                    logger.info("✅ Stripe configuration found")
                
            else:
                logger.info("🔐 Validating self-hosted license...")
                
                # Check license configuration
                license_key = self.config.get('license_key')
                license_url = self.config.get('license_server.url')
                
                if not license_key or license_key == 'YOUR_LICENSE_KEY_HERE':
                    logger.warning("⚠️ No license key - running in trial mode")
                elif not license_url:
                    logger.warning("⚠️ No license server URL - offline validation only")
                else:
                    logger.info("✅ License configuration found")
                    
        except Exception as e:
            logger.error(f"❌ Business model validation failed: {e}")
    
    async def _load_business_cogs(self):
        """Load cogs based on business model"""
        logger.info("📦 Loading cogs based on business model...")
        
        # Core cogs (always available)
        core_cogs = [
            'cogs.tickets',
            'cogs.reports', 
            'cogs.applications',
            'cogs.suggestions',
            'cogs.statistics',
            'cogs.priorities'
        ]
        
        # Business model specific cogs
        if self.config.is_hosted_model():
            business_cogs = [
                'cogs.subscription_manager',
                'cogs.billing_integration'
            ]
            logger.info("📋 Loading hosted service cogs...")
        else:
            business_cogs = [
                'cogs.license_manager'
            ]
            logger.info("📋 Loading self-hosted cogs...")
        
        # Load all cogs
        all_cogs = core_cogs + business_cogs
        loaded_cogs = []
        failed_cogs = []
        
        for cog in all_cogs:
            try:
                await self.load_extension(cog)
                loaded_cogs.append(cog.split('.')[-1])
                logger.info(f"  ✅ {cog}")
            except commands.ExtensionNotFound:
                failed_cogs.append(cog.split('.')[-1])
                logger.warning(f"  ⚠️ {cog} - File not found")
            except commands.ExtensionFailed as e:
                failed_cogs.append(cog.split('.')[-1])
                logger.error(f"  ❌ {cog} - Load failed: {e.original}")
            except Exception as e:
                failed_cogs.append(cog.split('.')[-1])
                logger.error(f"  ❌ {cog} - Unexpected error: {e}")
        
        self.business_cogs = loaded_cogs
        
        logger.info(f"📦 Cog loading complete: {len(loaded_cogs)} loaded, {len(failed_cogs)} failed")
        if loaded_cogs:
            logger.info(f"✅ Loaded: {', '.join(loaded_cogs)}")
        if failed_cogs:
            logger.info(f"❌ Failed: {', '.join(failed_cogs)}")
    
    async def _setup_event_systems(self):
        """Setup event-driven systems"""
        try:
            logger.info("📊 Setting up event-driven systems...")
            
            # Setup statistics event manager if available
            stats_cog = self.get_cog('StatisticsCog')
            if stats_cog and hasattr(stats_cog, 'setup_event_manager'):
                self.stats_events = await stats_cog.setup_event_manager()
                logger.info("✅ Statistics event system ready")
            else:
                logger.info("ℹ️ Statistics events not available")
            
        except Exception as e:
            logger.error(f"❌ Event system setup failed: {e}")
    
    async def _update_ui_components(self):
        """Update UI components with fresh data"""
        try:
            logger.info("🎨 Updating UI components...")
            await asyncio.sleep(2)  # Wait for database to be fully ready
            
            # Get categories from database
            categories = await self.db.get_categories() if hasattr(self.db, 'get_categories') else []
            
            if categories:
                # Update persistent view options
                for view in self.persistent_views:
                    if isinstance(view, CommercialPersistentCategoryView):
                        select = view.children[0]
                        select.options = [
                            discord.SelectOption(
                                label=cat,
                                value=cat,
                                description=f"Create a {cat.lower()} ticket"
                            ) for cat in categories
                        ]
                        logger.info(f"✅ Updated category options: {', '.join(categories)}")
                        break
            else:
                logger.warning("⚠️ No categories found - using defaults")
                
        except Exception as e:
            logger.error(f"❌ UI update failed: {e}")
    
    async def on_ready(self):
        """Enhanced ready event with comprehensive status display"""
        uptime = datetime.datetime.now() - self.startup_time
        
        # Display startup banner
        logger.info("=" * 60)
        logger.info("🎫 HyperTicky Pro - READY FOR SERVICE")
        logger.info(f"🤖 Bot: {self.user} (ID: {self.user.id})")
        logger.info(f"⏱️ Startup Time: {uptime.total_seconds():.2f} seconds")
        logger.info(f"🌐 Guilds: {len(self.guilds)} connected")
        logger.info(f"👥 Users: {len(self.users)} total")
        logger.info(f"🔧 Cogs: {len(self.cogs)} loaded")
        
        # Business model specific validation
        if self.config.is_hosted_model():
            logger.info(f"📊 Serving {len(self.guilds)} guilds in hosted mode")
            
            # Check for guilds that need subscription setup
            for guild in self.guilds:
                subscription = await self.db.get_guild_subscription(guild.id)
                if not subscription:
                    await self.db.create_guild_subscription(guild.id, 'trial')
                    logger.info(f"  🆕 Created trial for {guild.name} ({guild.id})")
                    
            # Display subscription manager status
            sub_manager = self.get_cog('SubscriptionManager')
            if sub_manager:
                logger.info("✅ Subscription Manager: Active")
            else:
                logger.warning("⚠️ Subscription Manager: Not loaded")
                
        else:
            # Self-hosted mode
            target_guild = None
            guild_id = int(self.config.get('guild_id', 0))
            
            if self.guilds:
                target_guild = self.get_guild(guild_id) or self.guilds[0]
                logger.info(f"🏠 Target Guild: {target_guild.name} ({target_guild.member_count} members)")
            
            # Display license manager status
            license_manager = self.get_cog('LicenseManager')
            if license_manager:
                license_info = {
                    'valid': license_manager.license_valid,
                    'tier': license_manager.license_tier if hasattr(license_manager, 'license_tier') else 'unknown',
                    'expires': license_manager.license_expires if hasattr(license_manager, 'license_expires') else None
                }
                await self._display_license_status(license_info)
            else:
                logger.warning("⚠️ License Manager: Not loaded - running in trial mode")
        
        # Sync commands if needed
        if not self.synced:
            await self._sync_commands_with_validation()
            self.synced = True
        
        # Auto-refresh existing panels
        await self._auto_refresh_panels()
        
        # Display feature availability
        await self._display_feature_status()
        
        # Set bot status
        await self._set_bot_status()
        
        logger.info("=" * 60)
        logger.info("🚀 HyperTicky Pro is FULLY OPERATIONAL!")
        logger.info("📞 Support: https://support.hyperticky.com")
        logger.info("📖 Docs: https://docs.hyperticky.com")
        logger.info("=" * 60)
    
    async def _display_license_status(self, license_info: dict):
        """Display detailed license status for self-hosted"""
        if license_info['valid']:
            tier = license_info['tier'].upper()
            if license_info['expires']:
                days_left = (license_info['expires'] - datetime.datetime.utcnow()).days
                logger.info(f"📜 License: {tier} (expires in {days_left} days)")
                
                if days_left <= 7:
                    logger.warning("⚠️ LICENSE EXPIRING SOON! Please renew.")
                elif days_left <= 30:
                    logger.info("ℹ️ License renewal recommended soon.")
            else:
                logger.info(f"📜 License: {tier} (perpetual)")
        else:
            logger.info("📜 License: TRIAL MODE")
            logger.info("🎯 Trial limitations apply - upgrade for full features")
    
    async def _sync_commands_with_validation(self):
        """Sync commands with business model validation"""
        try:
            logger.info("🔄 Syncing slash commands...")
            
            if self.config.is_hosted_model():
                # Global sync for hosted (slower but works for all guilds)
                synced = await self.tree.sync()
                logger.info(f"✅ Synced {len(synced)} slash commands globally")
            else:
                # Guild-specific sync for self-hosted (faster)
                guild_id = int(self.config.get('guild_id'))
                guild = discord.Object(id=guild_id)
                synced = await self.tree.sync(guild=guild)
                logger.info(f"✅ Synced {len(synced)} slash commands to guild {guild_id}")
            
            # Log command details
            command_names = [cmd.name for cmd in synced]
            if command_names:
                logger.info(f"📋 Active commands: {', '.join(command_names)}")
                
        except Exception as e:
            logger.error(f"❌ Command sync failed: {e}")
            traceback.print_exc()
    
    async def _auto_refresh_panels(self):
        """Auto-refresh existing panels with enhanced detection"""
        try:
            logger.info("🔄 Auto-refreshing existing panels...")
            refreshed_count = 0
            
            # Get categories for updating panels
            categories = await self.db.get_categories() if hasattr(self.db, 'get_categories') else ['General Support', 'Bug Report', 'Feature Request']
            
            for guild in self.guilds:
                if not guild.me.guild_permissions.read_message_history:
                    continue
                    
                for channel in guild.text_channels:
                    if not channel.permissions_for(guild.me).read_message_history:
                        continue
                    if not channel.permissions_for(guild.me).send_messages:
                        continue
                    
                    try:
                        async for message in channel.history(limit=50):
                            if message.author != self.user or not message.embeds:
                                continue
                            
                            embed = message.embeds[0]
                            title = embed.title or ""
                            
                            # Ticket creation panels
                            if any(keyword in title.lower() for keyword in ["ticket", "support", "create"]):
                                view = CommercialPersistentCategoryView()
                                select = view.children[0]
                                select.options = [
                                    discord.SelectOption(label=cat, value=cat, description=f"Create a {cat.lower()} ticket")
                                    for cat in categories
                                ]
                                await message.edit(view=view)
                                refreshed_count += 1
                                logger.info(f"  ✅ Ticket panel refreshed in #{channel.name}")
                            
                            # Staff application panels
                            elif "application" in title.lower() or "staff" in title.lower():
                                view = CommercialPersistentStaffApply()
                                await message.edit(view=view)
                                refreshed_count += 1
                                logger.info(f"  ✅ Staff panel refreshed in #{channel.name}")
                            
                            # Suggestion panels
                            elif "suggestion" in title.lower():
                                view = CommercialPersistentSuggestion()
                                await message.edit(view=view)
                                refreshed_count += 1
                                logger.info(f"  ✅ Suggestion panel refreshed in #{channel.name}")
                            
                            # Ticket management buttons
                            elif (channel.name.startswith(("ticket-", "report-", "suggestion-", "application-")) 
                                  and message.components):
                                view = EnhancedPersistentTicketButtons()
                                await message.edit(view=view)
                                refreshed_count += 1
                                logger.info(f"  ✅ Ticket buttons refreshed in #{channel.name}")
                    
                    except (discord.Forbidden, discord.HTTPException):
                        continue
                    except Exception as e:
                        logger.warning(f"Error refreshing #{channel.name}: {e}")
                        continue
            
            if refreshed_count > 0:
                logger.info(f"✅ Auto-refresh complete: {refreshed_count} panels updated")
            else:
                logger.info("ℹ️ No existing panels found to refresh")
                
        except Exception as e:
            logger.error(f"❌ Auto-refresh failed: {e}")
    
    async def _display_feature_status(self):
        """Display current feature availability"""
        logger.info("🎯 Feature Status:")
        
        features = {
            "tickets": "Core Ticketing",
            "reports": "Player/Mod Reports", 
            "applications": "Staff Applications",
            "suggestions": "Community Suggestions",
            "api_access": "REST API Access",
            "priority_support": "Priority Support"
        }
        
        for feature, name in features.items():
            # Check based on business model
            if self.config.is_hosted_model():
                # For hosted, check if subscription manager can validate
                available = True  # Default to available for hosted
            else:
                # For self-hosted, check license manager
                license_manager = self.get_cog('LicenseManager')
                if license_manager:
                    available = license_manager.check_feature_access(feature)
                else:
                    available = feature in ['tickets', 'reports']  # Basic features only
            
            if available:
                logger.info(f"  ✅ {name}")
            else:
                logger.info(f"  🔒 {name} (requires upgrade)")
    
    async def _set_bot_status(self):
        """Set appropriate bot status"""
        if self.config.is_hosted_model():
            activity = discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} servers | /help"
            )
        else:
            guild_name = self.guilds[0].name if self.guilds else "Server"
            activity = discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{guild_name} | /help"
            )
        
        await self.change_presence(activity=activity)
    
    async def on_guild_join(self, guild):
        """Handle bot joining a new guild"""
        logger.info(f"🎉 Joined new guild: {guild.name} ({guild.id})")
        
        if self.config.is_hosted_model():
            # Create trial subscription for new guild
            subscription_manager = self.get_cog('SubscriptionManager')
            if subscription_manager:
                # Let the subscription manager handle welcome message
                pass
            else:
                # Fallback: create trial manually
                await self.db.create_guild_subscription(guild.id, 'trial')
                logger.info(f"  🆕 Created trial subscription")
        
        # Update bot status
        await self._set_bot_status()
    
    async def on_guild_remove(self, guild):
        """Handle bot being removed from guild"""
        logger.info(f"👋 Left guild: {guild.name} ({guild.id})")
        
        if self.config.is_hosted_model():
            # Mark subscription as inactive
            try:
                query = "UPDATE guild_subscriptions SET status = 'inactive' WHERE guild_id = %s"
                await self.db.execute_query(query, (guild.id,))
                logger.info(f"  📝 Marked subscription as inactive")
            except Exception as e:
                logger.error(f"  ❌ Error updating subscription: {e}")
        
        # Update bot status
        await self._set_bot_status()
    
    async def on_application_command(self, interaction: discord.Interaction):
        """Track command usage and performance"""
        self.command_count += 1
        
        # Log command usage for analytics
        try:
            await self._report_usage("command_executed", {
                "command": interaction.command.name if interaction.command else "unknown",
                "user_id": interaction.user.id,
                "guild_id": interaction.guild.id if interaction.guild else None
            })
        except:
            pass  # Don't let analytics break functionality
    
    async def on_application_command_error(self, interaction: discord.Interaction, error):
        """Enhanced error handling with business model awareness"""
        self.error_count += 1
        
        # Log error
        logger.error(f"Command error in {interaction.command}: {error}")
        
        # Create user-friendly error message
        embed = discord.Embed(
            title="❌ Command Error",
            description="An unexpected error occurred. Please try again later.",
            color=0xFF0000
        )
        
        # Handle specific error types
        if isinstance(error, commands.CommandOnCooldown):
            embed.description = f"⏱️ Command is on cooldown. Try again in {error.retry_after:.1f} seconds."
            embed.color = 0xFFAA00
        elif isinstance(error, commands.MissingPermissions):
            embed.description = "🚫 You don't have permission to use this command."
            embed.color = 0xFF6B6B
        elif isinstance(error, commands.BotMissingPermissions):
            embed.description = "🚫 I don't have the required permissions to execute this command."
            embed.color = 0xFF6B6B
        elif isinstance(error, commands.NoPrivateMessage):
            embed.description = "❌ This command can only be used in a server."
            embed.color = 0xFF6B6B
        
        # Add support information
        embed.set_footer(text="If this persists, contact support")
        
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        except:
            pass  # Don't error on error handling
    
    async def on_error(self, event, *args, **kwargs):
        """Enhanced error logging"""
        logger.error(f"Unhandled error in {event}: {traceback.format_exc()}")
    
    # Utility methods for business logic
    async def check_feature_access(self, guild_id: int, feature: str) -> bool:
        """Check if a guild has access to a specific feature"""
        if self.config.is_hosted_model():
            # Check subscription features
            subscription = await self.db.get_guild_subscription(guild_id)
            if not subscription or subscription['status'] != 'active':
                return False
            
            features = subscription.get('features', {})
            return features.get(feature, False)
        else:
            # Check license features
            license_manager = self.get_cog('LicenseManager')
            if license_manager:
                return license_manager.check_feature_access(feature)
            return True  # Default to true if no license manager
    
    async def get_feature_limit(self, guild_id: int, feature: str) -> int:
        """Get the limit for a specific feature"""
        if self.config.is_hosted_model():
            subscription = await self.db.get_guild_subscription(guild_id)
            if not subscription:
                return 0
            
            features = subscription.get('features', {})
            return features.get(feature, 0)
        else:
            license_manager = self.get_cog('LicenseManager')
            if license_manager:
                return license_manager.get_feature_limit(feature)
            return -1  # Unlimited if no license manager
    
    async def _get_usage_stats(self, guild_id: int) -> dict:
        """Get usage statistics for a guild"""
        if self.config.is_hosted_model():
            # Multi-tenant query
            query = """
                SELECT 
                    COUNT(*) as total_tickets,
                    SUM(CASE WHEN ticket_type = 'ticket' THEN 1 ELSE 0 END) as tickets,
                    SUM(CASE WHEN ticket_type = 'report' THEN 1 ELSE 0 END) as reports,
                    SUM(CASE WHEN ticket_type = 'application' THEN 1 ELSE 0 END) as applications,
                    SUM(CASE WHEN ticket_type = 'suggestion' THEN 1 ELSE 0 END) as suggestions
                FROM tickets 
                WHERE guild_id = %s 
                AND created_at >= DATE_SUB(NOW(), INTERVAL 1 MONTH)
            """
            params = (guild_id,)
        else:
            # Single-tenant query
            query = """
                SELECT 
                    COUNT(*) as total_tickets,
                    SUM(CASE WHEN ticket_type = 'ticket' THEN 1 ELSE 0 END) as tickets,
                    SUM(CASE WHEN ticket_type = 'report' THEN 1 ELSE 0 END) as reports,
                    SUM(CASE WHEN ticket_type = 'application' THEN 1 ELSE 0 END) as applications,
                    SUM(CASE WHEN ticket_type = 'suggestion' THEN 1 ELSE 0 END) as suggestions
                FROM tickets 
                WHERE created_at >= datetime('now', '-1 month')
            """
            params = ()
        
        try:
            result = await self.db.execute_query(query, params)
            if result and result[0]:
                return {
                    'total_tickets': result[0][0] or 0,
                    'tickets': result[0][1] or 0,
                    'reports': result[0][2] or 0,
                    'applications': result[0][3] or 0,
                    'suggestions': result[0][4] or 0
                }
        except Exception as e:
            logger.error(f"Error getting usage stats: {e}")
        
        return {'total_tickets': 0, 'tickets': 0, 'reports': 0, 'applications': 0, 'suggestions': 0}
    
    async def _report_usage(self, event_type: str, data: dict):
        """Report usage analytics"""
        try:
            # For hosted model, could send to analytics service
            # For self-hosted, could send to license server
            if self.config.is_hosted_model():
                # Could implement analytics reporting here
                pass
            else:
                # Report to license server if available
                license_manager = self.get_cog('LicenseManager')
                if license_manager and hasattr(license_manager, 'report_usage'):
                    await license_manager.report_usage(event_type, data)
        except:
            pass  # Don't let analytics break functionality
    
    def get_persistent_ticket_buttons(self):
        """Get enhanced persistent ticket buttons for new tickets"""
        return EnhancedPersistentTicketButtons()
    
    async def close(self):
        """Enhanced cleanup on shutdown"""
        if self.shutdown_initiated:
            return
        
        self.shutdown_initiated = True
        logger.info("🔄 Initiating HyperTicky Pro shutdown...")
        
        # Calculate uptime
        uptime = datetime.datetime.now() - self.startup_time
        
        # Report shutdown statistics
        try:
            await self._report_usage("bot_shutdown", {
                "uptime_seconds": uptime.total_seconds(),
                "commands_executed": self.command_count,
                "errors_encountered": self.error_count
            })
        except:
            pass
        
        # Close database connection
        if self.db:
            try:
                await self.db.close()
                logger.info("✅ Database connection closed")
            except Exception as e:
                logger.error(f"❌ Error closing database: {e}")
        
        # Shutdown logging
        logger.info(f"📊 Session Stats: {self.command_count} commands, {self.error_count} errors")
        logger.info(f"⏱️ Total Uptime: {uptime}")
        logger.info("✅ HyperTicky Pro shutdown complete")
        
        await super().close()

# Simple rate limiter class
class RateLimiter:
    def __init__(self):
        self.user_requests = {}
        self.window_duration = 300  # 5 minutes
        self.max_requests = 5
    
    def is_rate_limited(self, user_id: int, max_requests: int = None, window: int = None) -> bool:
        """Check if user is rate limited"""
        now = datetime.datetime.now()
        max_req = max_requests or self.max_requests
        window_dur = window or self.window_duration
        
        if user_id not in self.user_requests:
            self.user_requests[user_id] = []
        
        # Clean old requests
        cutoff = now - datetime.timedelta(seconds=window_dur)
        self.user_requests[user_id] = [
            req_time for req_time in self.user_requests[user_id] 
            if req_time > cutoff
        ]
        
        # Check limit
        if len(self.user_requests[user_id]) >= max_req:
            return True
        
        # Add current request
        self.user_requests[user_id].append(now)
        return False

# Global exception handler
def handle_exception(exc_type, exc_value, exc_traceback):
    """Handle uncaught exceptions"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception

async def main():
    """Enhanced main function with professional error handling"""
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ required")
        print(f"Current version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        return 1
    
    # Display startup banner
    print("=" * 60)
    print("🎫 HyperTicky Pro - Enterprise Discord Ticket Bot")
    print("Version 2.0.0 - Commercial Edition")
    print("© 2024 HyperTicky Solutions")
    print("🌐 https://hyperticky.com")
    print("=" * 60)
    
    # Create necessary directories
    os.makedirs('data', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    os.makedirs('config', exist_ok=True)
    
    # Check for configuration file
    config_files = ['config.json5', 'config/hosted_config.json5', 'config/self_hosted_config.json5']
    config_exists = any(os.path.exists(f) for f in config_files)
    
    if not config_exists:
        logger.error("❌ No configuration file found!")
        logger.info("Please create a configuration file:")
        logger.info("  - config.json5 (main config)")
        logger.info("  - config/hosted_config.json5 (hosted service)")
        logger.info("  - config/self_hosted_config.json5 (self-hosted)")
        return 1
    
    try:
        # Initialize bot
        logger.info("🔧 Initializing HyperTicky Pro...")
        bot = HyperTicky()
        
        # Validate critical configuration
        bot_token = bot.config.get('bot_token')
        if not bot_token or bot_token in ["YOUR_BOT_TOKEN_HERE", ""]:
            logger.error("❌ Bot token not configured!")
            logger.info("Please edit your configuration file and set your Discord bot token.")
            logger.info("Get your bot token from: https://discord.com/developers/applications")
            return 1
        
        if bot.config.is_self_hosted_model():
            guild_id = bot.config.get('guild_id')
            if not guild_id or guild_id == 0:
                logger.error("❌ Guild ID not configured for self-hosted mode!")
                logger.info("Please edit your configuration file and set your Discord server ID.")
                return 1
        
        # Set event loop policy for Windows
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        # Start the bot
        logger.info("🚀 Starting HyperTicky Pro...")
        await bot.start(bot_token)
        
    except discord.LoginFailure:
        logger.error("❌ Invalid bot token!")
        logger.info("Please check your bot token in the configuration file")
        logger.info("Get a new token from: https://discord.com/developers/applications")
        return 1
        
    except discord.PrivilegedIntentsRequired:
        logger.error("❌ Bot needs privileged intents!")
        logger.info("Enable these intents in Discord Developer Portal:")
        logger.info("• Message Content Intent")
        logger.info("• Server Members Intent")
        logger.info("• Presence Intent")
        return 1
        
    except discord.HTTPException as e:
        logger.error(f"❌ Discord API error: {e}")
        if e.status == 401:
            logger.info("This usually means your bot token is invalid.")
        return 1
        
    except KeyboardInterrupt:
        logger.info("\n👋 Shutdown requested by user")
        return 0
        
    except Exception as e:
        logger.error(f"❌ Unexpected startup error: {e}")
        logger.error("Full traceback:")
        traceback.print_exc()
        return 1
        
    finally:
        # Ensure cleanup
        if 'bot' in locals() and not bot.shutdown_initiated:
            try:
                await bot.close()
            except:
                pass
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)