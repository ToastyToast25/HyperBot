# database.py - Updated for multi-tenancy
import asyncio
import aiomysql
import aiosqlite
import json
import os
from typing import Optional, Dict, Any, List

class Database:
    def __init__(self, config):
        self.config = config
        self.pool = None
        self.sqlite_db = None
        self.use_mariadb = config.get('database', {}).get('use_mariadb', True)
        self.business_model = config.get('business_model', 'hosted')  # 'hosted' or 'self_hosted'
    
    async def connect(self):
        """Initialize database connection based on business model"""
        if self.business_model == 'hosted' and self.use_mariadb:
            await self._connect_mariadb()
        else:
            await self._connect_sqlite()
    
    async def _connect_mariadb(self):
        """Connect to MariaDB for hosted multi-tenant setup"""
        try:
            self.pool = await aiomysql.create_pool(
                host=self.config['database']['host'],
                port=self.config['database']['port'],
                user=self.config['database']['user'],
                password=self.config['database']['password'],
                db=self.config['database']['database'],
                charset='utf8mb4',
                maxsize=20,
                autocommit=True
            )
            await self._create_multi_tenant_tables()
            print("✅ Connected to MariaDB (Multi-tenant)")
        except Exception as e:
            print(f"❌ MariaDB connection failed: {e}")
            await self._connect_sqlite()
    
    async def _connect_sqlite(self):
        """Connect to SQLite for self-hosted setup"""
        db_path = self.config.get('database', {}).get('sqlite_path', 'data/hyperticky.db')
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.sqlite_db = await aiosqlite.connect(db_path)
        await self._create_single_tenant_tables()
        print("✅ Connected to SQLite (Single-tenant)")
    
    async def _create_multi_tenant_tables(self):
        """Create multi-tenant tables with guild_id isolation"""
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Enhanced tickets table with guild_id for multi-tenancy
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS tickets (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        ticket_number INT NOT NULL,
                        discord_id BIGINT NOT NULL,
                        channel_id BIGINT,
                        user_id BIGINT NOT NULL,
                        username VARCHAR(100),
                        display_name VARCHAR(100),
                        ticket_type ENUM('ticket', 'report', 'application', 'suggestion') DEFAULT 'ticket',
                        category VARCHAR(100),
                        priority INT DEFAULT 1,
                        status ENUM('open', 'closed', 'in_progress', 'pending') DEFAULT 'open',
                        title TEXT,
                        description TEXT,
                        reason TEXT,
                        admin_notes TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        closed_at TIMESTAMP NULL,
                        closed_by BIGINT,
                        assigned_to BIGINT,
                        
                        -- Indexes for multi-tenant performance
                        INDEX idx_guild_tickets (guild_id, ticket_type),
                        INDEX idx_guild_user (guild_id, user_id),
                        INDEX idx_guild_status (guild_id, status),
                        INDEX idx_guild_priority (guild_id, priority),
                        
                        -- Ensure unique ticket numbers per guild
                        UNIQUE KEY unique_ticket_per_guild (guild_id, ticket_number)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                
                # Guild subscriptions table for hosted model
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS guild_subscriptions (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        guild_id BIGINT UNIQUE NOT NULL,
                        subscription_tier ENUM('trial', 'basic', 'pro', 'enterprise') DEFAULT 'trial',
                        stripe_customer_id VARCHAR(100),
                        stripe_subscription_id VARCHAR(100),
                        status ENUM('active', 'inactive', 'cancelled', 'expired') DEFAULT 'active',
                        trial_ends_at TIMESTAMP,
                        subscription_ends_at TIMESTAMP,
                        features JSON,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        
                        INDEX idx_guild_status (guild_id, status),
                        INDEX idx_stripe_customer (stripe_customer_id),
                        INDEX idx_subscription_status (status)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                
                # Usage analytics per guild
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS guild_usage (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        date DATE NOT NULL,
                        tickets_created INT DEFAULT 0,
                        reports_created INT DEFAULT 0,
                        applications_submitted INT DEFAULT 0,
                        suggestions_made INT DEFAULT 0,
                        active_users INT DEFAULT 0,
                        
                        UNIQUE KEY unique_guild_date (guild_id, date),
                        INDEX idx_guild_date (guild_id, date)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
    
    async def _create_single_tenant_tables(self):
        """Create single-tenant tables for self-hosted"""
        # Original table structure without guild_id
        await self.sqlite_db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_number INTEGER NOT NULL,
                discord_id INTEGER NOT NULL,
                channel_id INTEGER,
                user_id INTEGER NOT NULL,
                username TEXT,
                display_name TEXT,
                ticket_type TEXT DEFAULT 'ticket',
                category TEXT,
                priority INTEGER DEFAULT 1,
                status TEXT DEFAULT 'open',
                title TEXT,
                description TEXT,
                reason TEXT,
                admin_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP,
                closed_by INTEGER,
                assigned_to INTEGER
            )
        """)
        
        # License validation cache for self-hosted
        await self.sqlite_db.execute("""
            CREATE TABLE IF NOT EXISTS license_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_key TEXT UNIQUE NOT NULL,
                features JSON,
                expires_at TIMESTAMP,
                last_validated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                validation_count INTEGER DEFAULT 0
            )
        """)
        
        await self.sqlite_db.commit()
    
    # Multi-tenant query methods
    async def execute_query(self, query: str, params: tuple = (), guild_id: Optional[int] = None):
        """Execute query with automatic guild isolation for hosted model"""
        if self.business_model == 'hosted' and guild_id:
            # Add guild_id to WHERE clause for multi-tenant isolation
            if 'WHERE' in query.upper():
                query = query.replace('WHERE', f'WHERE guild_id = {guild_id} AND')
            else:
                query += f' WHERE guild_id = {guild_id}'
        
        if self.pool:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, params)
                    if query.strip().upper().startswith('SELECT'):
                        return await cursor.fetchall()
                    return cursor.lastrowid
        else:
            async with self.sqlite_db.execute(query, params) as cursor:
                if query.strip().upper().startswith('SELECT'):
                    return await cursor.fetchall()
                return cursor.lastrowid
    
    async def create_ticket(self, guild_id: int, **kwargs) -> int:
        """Create a new ticket with proper guild isolation"""
        # Get next ticket number for this guild
        if self.business_model == 'hosted':
            next_number = await self._get_next_ticket_number(guild_id)
            query = """
                INSERT INTO tickets (guild_id, ticket_number, discord_id, user_id, username, 
                                   display_name, ticket_type, category, title, description, reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            params = (guild_id, next_number, kwargs.get('discord_id'), kwargs.get('user_id'),
                     kwargs.get('username'), kwargs.get('display_name'), kwargs.get('ticket_type', 'ticket'),
                     kwargs.get('category'), kwargs.get('title'), kwargs.get('description'), kwargs.get('reason'))
        else:
            next_number = await self._get_next_ticket_number()
            query = """
                INSERT INTO tickets (ticket_number, discord_id, user_id, username, 
                                   display_name, ticket_type, category, title, description, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params = (next_number, kwargs.get('discord_id'), kwargs.get('user_id'),
                     kwargs.get('username'), kwargs.get('display_name'), kwargs.get('ticket_type', 'ticket'),
                     kwargs.get('category'), kwargs.get('title'), kwargs.get('description'), kwargs.get('reason'))
        
        return await self.execute_query(query, params)
    
    async def _get_next_ticket_number(self, guild_id: Optional[int] = None) -> int:
        """Get next ticket number for guild (multi-tenant) or global (single-tenant)"""
        if self.business_model == 'hosted' and guild_id:
            query = "SELECT MAX(ticket_number) FROM tickets WHERE guild_id = %s"
            params = (guild_id,)
        else:
            query = "SELECT MAX(ticket_number) FROM tickets"
            params = ()
        
        result = await self.execute_query(query, params)
        return (result[0][0] or 0) + 1 if result and result[0] and result[0][0] else 1
    
    async def get_guild_subscription(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get subscription info for a guild (hosted model only)"""
        if self.business_model != 'hosted':
            return None
            
        query = "SELECT * FROM guild_subscriptions WHERE guild_id = %s"
        result = await self.execute_query(query, (guild_id,))
        
        if result:
            return {
                'guild_id': result[0][1],
                'subscription_tier': result[0][2],
                'status': result[0][4],
                'trial_ends_at': result[0][6],
                'subscription_ends_at': result[0][7],
                'features': json.loads(result[0][8] or '{}')
            }
        return None
    
    async def create_guild_subscription(self, guild_id: int, tier: str = 'trial') -> bool:
        """Create a new guild subscription (hosted model)"""
        if self.business_model != 'hosted':
            return False
            
        # 7-day trial for new guilds
        from datetime import datetime, timedelta
        trial_end = datetime.utcnow() + timedelta(days=7)
        
        features = {
            'trial': {'max_tickets': 50, 'max_staff_positions': 3, 'api_access': False},
            'basic': {'max_tickets': 200, 'max_staff_positions': 5, 'api_access': False},
            'pro': {'max_tickets': 1000, 'max_staff_positions': 15, 'api_access': True},
            'enterprise': {'max_tickets': -1, 'max_staff_positions': -1, 'api_access': True}
        }
        
        query = """
            INSERT INTO guild_subscriptions (guild_id, subscription_tier, trial_ends_at, features)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                subscription_tier = VALUES(subscription_tier),
                trial_ends_at = VALUES(trial_ends_at),
                features = VALUES(features)
        """
        
        await self.execute_query(query, (guild_id, tier, trial_end, json.dumps(features[tier])))
        return True
    
    async def close(self):
        """Close database connections"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
        if self.sqlite_db:
            await self.sqlite_db.close()