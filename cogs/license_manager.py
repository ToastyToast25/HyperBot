# cogs/license_manager.py - License validation for self-hosted model
import discord
from discord.ext import commands, tasks
import aiohttp
import json
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import asyncio

class LicenseManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.db = bot.db
        
        # License configuration
        self.license_key = self.config.get('license_key')
        self.license_server_url = self.config.get('license_server.url')
        self.cache_duration = self.config.get('license_server.cache_duration', 3600)  # 1 hour
        
        # License status
        self.license_valid = False
        self.license_features = {}
        self.license_expires = None
        self.last_validation = None
        
        # Only run if self-hosted model
        if self.config.is_self_hosted_model():
            self.validate_license_task.start()
            self.bot.loop.create_task(self._initial_validation())
    
    def cog_unload(self):
        """Clean up tasks when cog unloads"""
        if hasattr(self, 'validate_license_task'):
            self.validate_license_task.cancel()
    
    async def _initial_validation(self):
        """Perform initial license validation on startup"""
        await self.bot.wait_until_ready()
        await asyncio.sleep(2)  # Wait for database connection
        
        print("🔑 Performing initial license validation...")
        
        # Try to load cached license first
        cached_license = await self._load_cached_license()
        if cached_license and self._is_cache_valid(cached_license):
            self._apply_license_data(cached_license)
            print("✅ Using cached license validation")
        else:
            # Perform online validation
            await self._validate_license_online()
        
        if not self.license_valid:
            print("❌ License validation failed - bot will run in limited mode")
            await self._notify_license_issue("invalid")
    
    async def _validate_license_online(self) -> bool:
        """Validate license with remote server"""
        if not self.license_key or not self.license_server_url:
            print("❌ Missing license key or server URL")
            return False
        
        try:
            # Create validation payload
            payload = {
                'license_key': self.license_key,
                'guild_id': self.config.get('guild_id'),
                'bot_version': getattr(self.bot, 'version', '1.0.0'),
                'timestamp': int(time.time())
            }
            
            # Add signature for security
            payload['signature'] = self._create_signature(payload)
            
            timeout = aiohttp.ClientTimeout(total=self.config.get('license_server.timeout', 30))
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.license_server_url}/api/validate",
                    json=payload,
                    headers={'Content-Type': 'application/json'}
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        if data.get('valid'):
                            self._apply_license_data(data)
                            await self._cache_license_data(data)
                            print(f"✅ License validated - Tier: {data.get('tier', 'Unknown')}")
                            return True
                        else:
                            print(f"❌ License invalid: {data.get('message', 'Unknown error')}")
                            return False
                    else:
                        print(f"❌ License server error: {response.status}")
                        return False
                        
        except asyncio.TimeoutError:
            print("❌ License validation timeout")
            return False
        except Exception as e:
            print(f"❌ License validation error: {e}")
            return False
    
    def _create_signature(self, payload: Dict[str, Any]) -> str:
        """Create security signature for license validation"""
        # Create deterministic string from payload
        sorted_items = sorted(payload.items())
        payload_string = '&'.join(f"{k}={v}" for k, v in sorted_items if k != 'signature')
        
        # Create hash with license key as secret
        signature_string = f"{payload_string}:{self.license_key}"
        return hashlib.sha256(signature_string.encode()).hexdigest()
    
    def _apply_license_data(self, data: Dict[str, Any]):
        """Apply validated license data"""
        self.license_valid = data.get('valid', False)
        self.license_features = data.get('features', {})
        self.license_expires = datetime.fromisoformat(data['expires_at']) if data.get('expires_at') else None
        self.last_validation = datetime.utcnow()
        
        # Store additional license info
        self.license_tier = data.get('tier', 'unknown')
        self.license_customer = data.get('customer_info', {})
    
    async def _cache_license_data(self, data: Dict[str, Any]):
        """Cache license validation data"""
        cache_data = {
            **data,
            'cached_at': datetime.utcnow().isoformat(),
            'validation_count': (await self._get_validation_count()) + 1
        }
        
        query = """
            INSERT OR REPLACE INTO license_cache 
            (license_key, features, expires_at, last_validated, validation_count)
            VALUES (?, ?, ?, ?, ?)
        """
        
        await self.db.execute_query(query, (
            self.license_key,
            json.dumps(cache_data),
            self.license_expires.isoformat() if self.license_expires else None,
            datetime.utcnow().isoformat(),
            cache_data['validation_count']
        ))
    
    async def _load_cached_license(self) -> Optional[Dict[str, Any]]:
        """Load cached license data"""
        query = "SELECT features FROM license_cache WHERE license_key = ?"
        result = await self.db.execute_query(query, (self.license_key,))
        
        if result and result[0]:
            try:
                return json.loads(result[0][0])
            except json.JSONDecodeError:
                return None
        return None
    
    def _is_cache_valid(self, cached_data: Dict[str, Any]) -> bool:
        """Check if cached license data is still valid"""
        try:
            cached_at = datetime.fromisoformat(cached_data['cached_at'])
            cache_age = (datetime.utcnow() - cached_at).total_seconds()
            
            # Cache is valid if within duration and license hasn't expired
            cache_valid = cache_age < self.cache_duration
            
            if cached_data.get('expires_at'):
                license_expires = datetime.fromisoformat(cached_data['expires_at'])
                license_valid = datetime.utcnow() < license_expires
            else:
                license_valid = True
            
            return cache_valid and license_valid and cached_data.get('valid', False)
        except Exception:
            return False
    
    async def _get_validation_count(self) -> int:
        """Get current validation count"""
        query = "SELECT validation_count FROM license_cache WHERE license_key = ?"
        result = await self.db.execute_query(query, (self.license_key,))
        return result[0][0] if result and result[0] else 0
    
    @tasks.loop(hours=1)
    async def validate_license_task(self):
        """Periodically validate license"""
        try:
            # Check if we need to revalidate
            if self.last_validation:
                time_since_validation = (datetime.utcnow() - self.last_validation).total_seconds()
                if time_since_validation < self.cache_duration:
                    return  # Still within cache period
            
            # Perform validation
            success = await self._validate_license_online()
            
            if not success and self.license_valid:
                # Try to use cached data as fallback
                cached_license = await self._load_cached_license()
                if cached_license and self._is_cache_valid(cached_license):
                    print("⚠️ Online validation failed, using cached license")
                else:
                    self.license_valid = False
                    print("❌ License validation failed and no valid cache available")
                    await self._notify_license_issue("validation_failed")
            
        except Exception as e:
            print(f"Error in license validation task: {e}")
    
    async def _notify_license_issue(self, issue_type: str):
        """Notify about license issues"""
        guild = self.bot.get_guild(int(self.config.get('guild_id', 0)))
        if not guild:
            return
        
        # Find appropriate channel to send notification
        log_channel_id = self.config.get('channels.logs')
        channel = None
        
        if log_channel_id:
            channel = guild.get_channel(int(log_channel_id))
        
        if not channel:
            # Fallback to system channel or first text channel
            channel = guild.system_channel
            if not channel:
                channel = next((ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages), None)
        
        if not channel:
            return
        
        # Create appropriate embed based on issue type
        if issue_type == "invalid":
            embed = discord.Embed(
                title="❌ Invalid License",
                description="Your HyperTicky license is invalid or expired. Some features may be disabled.",
                color=0xff0000
            )
            embed.add_field(
                name="🔧 What to do",
                value="• Check your license key in config\n• Verify your subscription is active\n• Contact support if needed",
                inline=False
            )
        elif issue_type == "validation_failed":
            embed = discord.Embed(
                title="⚠️ License Validation Failed",
                description="Could not validate license with server. Running on cached validation.",
                color=0xff9900
            )
            embed.add_field(
                name="ℹ️ Information",
                value="• Bot will continue running normally\n• Check internet connection\n• License server may be temporarily unavailable",
                inline=False
            )
        elif issue_type == "expired":
            embed = discord.Embed(
                title="⏰ License Expired",
                description="Your HyperTicky license has expired. Please renew to continue using all features.",
                color=0xff0000
            )
            embed.add_field(
                name="💰 Renewal Required",
                value="• Visit your customer portal to renew\n• Contact billing support\n• Bot functionality will be limited",
                inline=False
            )
        
        embed.set_footer(text=f"License Key: {self.license_key[:8]}...")
        
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass
    
    def check_feature_access(self, feature: str) -> bool:
        """Check if a feature is available with current license"""
        if not self.license_valid:
            return False
        
        # Basic features always available
        basic_features = ['tickets', 'reports', 'applications', 'suggestions']
        if feature in basic_features:
            return True
        
        # Premium features require license validation
        return self.license_features.get(feature, False)
    
    def get_feature_limit(self, feature: str) -> int:
        """Get limit for a specific feature (-1 = unlimited, 0 = disabled)"""
        if not self.license_valid:
            # Default limits for invalid license
            default_limits = {
                'max_tickets': 50,
                'max_staff_positions': 3,
                'api_requests_per_hour': 100
            }
            return default_limits.get(feature, 0)
        
        return self.license_features.get(feature, 0)
    
    async def get_usage_stats(self) -> Dict[str, int]:
        """Get current usage statistics"""
        # Use the bot's method for consistency
        return await self.bot._get_usage_stats(0)  # Guild ID not needed for self-hosted
    
    @commands.slash_command(name="license", description="Check license status and information")
    @commands.has_permissions(administrator=True)
    async def license_info(self, ctx):
        """Display license information"""
        if not self.config.is_self_hosted_model():
            await ctx.respond("❌ This command is only available in self-hosted mode.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🔑 License Information",
            color=0x00ff00 if self.license_valid else 0xff0000
        )
        
        # License status
        status_emoji = "✅" if self.license_valid else "❌"
        status_text = "Valid" if self.license_valid else "Invalid/Expired"
        
        embed.add_field(
            name="📊 Status",
            value=f"{status_emoji} {status_text}",
            inline=True
        )
        
        if self.license_valid:
            embed.add_field(
                name="💎 Tier",
                value=self.license_tier.title(),
                inline=True
            )
            
            if self.license_expires:
                days_left = (self.license_expires - datetime.utcnow()).days
                embed.add_field(
                    name="⏰ Expires",
                    value=f"In {days_left} days\n{self.license_expires.strftime('%B %d, %Y')}",
                    inline=True
                )
            
            # Usage statistics
            usage_stats = await self.get_usage_stats()
            max_tickets = self.get_feature_limit('max_tickets')
            
            if max_tickets > 0:
                ticket_usage = f"{usage_stats['total_tickets']}/{max_tickets}"
                percentage = (usage_stats['total_tickets'] / max_tickets) * 100
            else:
                ticket_usage = f"{usage_stats['total_tickets']} (Unlimited)"
                percentage = 0
            
            embed.add_field(
                name="🎫 Ticket Usage (30 days)",
                value=ticket_usage + (f" ({percentage:.1f}%)" if max_tickets > 0 else ""),
                inline=True
            )
            
            # Features
            feature_list = []
            if self.check_feature_access('api_access'):
                feature_list.append("✅ API Access")
            if self.check_feature_access('priority_support'):
                feature_list.append("✅ Priority Support")
            if self.check_feature_access('dedicated_support'):
                feature_list.append("✅ Dedicated Support")
            if self.check_feature_access('source_code_access'):
                feature_list.append("✅ Source Code Access")
            
            if feature_list:
                embed.add_field(
                    name="🚀 Features",
                    value="\n".join(feature_list),
                    inline=False
                )
        else:
            embed.add_field(
                name="❌ Issues",
                value="License validation failed\nContact support or check configuration",
                inline=False
            )
        
        # Last validation
        if self.last_validation:
            embed.set_footer(text=f"Last validated: {self.last_validation.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        
        await ctx.respond(embed=embed, ephemeral=True)
    
    @commands.slash_command(name="validate_license", description="Force license validation")
    @commands.has_permissions(administrator=True)
    async def force_validation(self, ctx):
        """Force immediate license validation"""
        if not self.config.is_self_hosted_model():
            await ctx.respond("❌ This command is only available in self-hosted mode.", ephemeral=True)
            return
        
        await ctx.respond("🔄 Validating license...", ephemeral=True)
        
        success = await self._validate_license_online()
        
        if success:
            embed = discord.Embed(
                title="✅ License Validation Successful",
                description=f"License validated successfully!\n**Tier:** {self.license_tier.title()}",
                color=0x00ff00
            )
            
            if self.license_expires:
                days_left = (self.license_expires - datetime.utcnow()).days
                embed.add_field(
                    name="⏰ Expires",
                    value=f"In {days_left} days",
                    inline=True
                )
        else:
            embed = discord.Embed(
                title="❌ License Validation Failed",
                description="Could not validate license with server.\nCheck your internet connection and license key.",
                color=0xff0000
            )
        
        await ctx.edit_original_response(content=None, embed=embed)
    
    @commands.slash_command(name="license_features", description="Show available features for your license")
    @commands.has_permissions(administrator=True)
    async def license_features(self, ctx):
        """Display available features and limits"""
        if not self.config.is_self_hosted_model():
            await ctx.respond("❌ This command is only available in self-hosted mode.", ephemeral=True)
            return
        
        if not self.license_valid:
            await ctx.respond("❌ No valid license found.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🚀 License Features & Limits",
            description=f"**{self.license_tier.title()}** License",
            color=0x7289da
        )
        
        # Feature limits
        limits_text = []
        
        max_tickets = self.get_feature_limit('max_tickets')
        if max_tickets == -1:
            limits_text.append("🎫 Unlimited Tickets")
        else:
            limits_text.append(f"🎫 {max_tickets:,} Tickets/month")
        
        max_positions = self.get_feature_limit('max_staff_positions')
        if max_positions == -1:
            limits_text.append("👥 Unlimited Staff Positions")
        else:
            limits_text.append(f"👥 {max_positions} Staff Positions")
        
        api_limit = self.get_feature_limit('api_requests_per_hour')
        if api_limit == -1:
            limits_text.append("🔗 Unlimited API Requests")
        elif api_limit > 0:
            limits_text.append(f"🔗 {api_limit:,} API Requests/hour")
        
        embed.add_field(
            name="📊 Limits",
            value="\n".join(limits_text),
            inline=False
        )
        
        # Available features
        features_text = []
        
        if self.check_feature_access('api_access'):
            features_text.append("✅ REST API Access")
        else:
            features_text.append("❌ REST API Access")
        
        if self.check_feature_access('priority_support'):
            features_text.append("✅ Priority Support")
        else:
            features_text.append("❌ Priority Support")
        
        if self.check_feature_access('dedicated_support'):
            features_text.append("✅ Dedicated Support")
        else:
            features_text.append("❌ Dedicated Support")
        
        if self.check_feature_access('source_code_access'):
            features_text.append("✅ Source Code Access")
        else:
            features_text.append("❌ Source Code Access")
        
        embed.add_field(
            name="🎯 Features",
            value="\n".join(features_text),
            inline=False
        )
        
        # Current usage
        usage_stats = await self.get_usage_stats()
        usage_text = [
            f"🎫 {usage_stats['total_tickets']} Total Tickets (30 days)",
            f"📝 {usage_stats['tickets']} Support Tickets",
            f"📊 {usage_stats['reports']} Reports",
            f"💼 {usage_stats['applications']} Applications",
            f"💡 {usage_stats['suggestions']} Suggestions"
        ]
        
        embed.add_field(
            name="📈 Current Usage",
            value="\n".join(usage_text),
            inline=False
        )
        
        await ctx.respond(embed=embed, ephemeral=True)
    
    def license_required(self, feature: str = None):
        """Decorator to check license before command execution"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                # Get context from args
                ctx = args[1] if len(args) > 1 else args[0]
                
                # Check if license is valid
                if not self.license_valid:
                    await ctx.respond("❌ This feature requires a valid license.", ephemeral=True)
                    return
                
                # Check specific feature if provided
                if feature and not self.check_feature_access(feature):
                    await ctx.respond(f"❌ This feature ({feature}) is not included in your license.", ephemeral=True)
                    return
                
                # Check usage limits
                if feature == 'tickets':
                    usage_stats = await self.get_usage_stats()
                    max_tickets = self.get_feature_limit('max_tickets')
                    
                    if max_tickets > 0 and usage_stats['total_tickets'] >= max_tickets:
                        await ctx.respond(f"❌ Monthly ticket limit reached ({max_tickets}). Upgrade your license for more tickets.", ephemeral=True)
                        return
                
                # Execute original function
                return await func(*args, **kwargs)
            
            return wrapper
        return decorator


def setup(bot):
    bot.add_cog(LicenseManager(bot))