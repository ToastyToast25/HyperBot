# config.py - Enhanced for dual business models
import json5
import os
from typing import Dict, Any, Optional

class ConfigManager:
    def __init__(self, config_path: str = None):
        self.config_path = config_path or self._detect_config_path()
        self.config = self._load_config()
        self.business_model = self.config.get('business_model', 'hosted')
    
    def _detect_config_path(self) -> str:
        """Auto-detect which config file to use"""
        # Check for business model environment variable
        business_model = os.getenv('BUSINESS_MODEL', 'hosted')
        
        if business_model == 'hosted':
            if os.path.exists('config/hosted_config.json5'):
                return 'config/hosted_config.json5'
        elif business_model == 'self_hosted':
            if os.path.exists('config/self_hosted_config.json5'):
                return 'config/self_hosted_config.json5'
        
        # Fallback to main config
        return 'config.json5' if os.path.exists('config.json5') else 'config/config.json5.example'
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON5 file"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json5.load(f)
            
            # Merge with environment variables
            config = self._merge_env_vars(config)
            
            # Validate configuration
            self._validate_config(config)
            
            return config
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        except Exception as e:
            raise ValueError(f"Error loading configuration: {e}")
    
    def _merge_env_vars(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge environment variables into config"""
        env_mappings = {
            'DISCORD_TOKEN': ['bot_token'],
            'GUILD_ID': ['guild_id'],
            'DATABASE_HOST': ['database', 'host'],
            'DATABASE_USER': ['database', 'user'],
            'DATABASE_PASSWORD': ['database', 'password'],
            'DATABASE_NAME': ['database', 'database'],
            'STRIPE_SECRET_KEY': ['stripe', 'secret_key'],
            'STRIPE_WEBHOOK_SECRET': ['stripe', 'webhook_secret'],
            'LICENSE_SERVER_URL': ['license_server', 'url'],
            'LICENSE_KEY': ['license_key'],
            'BUSINESS_MODEL': ['business_model']
        }
        
        for env_key, config_path in env_mappings.items():
            env_value = os.getenv(env_key)
            if env_value:
                # Navigate to nested config location
                current = config
                for key in config_path[:-1]:
                    if key not in current:
                        current[key] = {}
                    current = current[key]
                current[config_path[-1]] = env_value
        
        return config
    
    def _validate_config(self, config: Dict[str, Any]):
        """Validate required configuration fields"""
        business_model = config.get('business_model', 'hosted')
        
        # Common required fields
        required_common = ['bot_token']
        
        # Business model specific requirements
        if business_model == 'hosted':
            required_hosted = [
                'database.host', 'database.user', 'database.password', 'database.database',
                'stripe.secret_key', 'stripe.webhook_secret'
            ]
            required_fields = required_common + required_hosted
        else:  # self_hosted
            required_self_hosted = ['license_key', 'license_server.url']
            required_fields = required_common + required_self_hosted
        
        missing_fields = []
        for field in required_fields:
            if '.' in field:
                # Nested field validation
                keys = field.split('.')
                current = config
                for key in keys:
                    if key not in current:
                        missing_fields.append(field)
                        break
                    current = current[key]
            else:
                if field not in config:
                    missing_fields.append(field)
        
        if missing_fields:
            raise ValueError(f"Missing required configuration fields: {missing_fields}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with dot notation support"""
        keys = key.split('.')
        current = self.config
        
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default
        
        return current
    
    def is_hosted_model(self) -> bool:
        """Check if running in hosted business model"""
        return self.business_model == 'hosted'
    
    def is_self_hosted_model(self) -> bool:
        """Check if running in self-hosted business model"""
        return self.business_model == 'self_hosted'
    
    def get_subscription_tiers(self) -> Dict[str, Dict[str, Any]]:
        """Get subscription tier configurations"""
        if self.is_hosted_model():
            return self.get('subscription_tiers', {
                'trial': {
                    'price': 0,
                    'duration_days': 7,
                    'features': {
                        'max_tickets': 50,
                        'max_staff_positions': 3,
                        'api_access': False,
                        'priority_support': False,
                        'custom_branding': False
                    }
                },
                'basic': {
                    'price': 9.99,
                    'features': {
                        'max_tickets': 200,
                        'max_staff_positions': 5,
                        'api_access': False,
                        'priority_support': False,
                        'custom_branding': False
                    }
                },
                'pro': {
                    'price': 29.99,
                    'features': {
                        'max_tickets': 1000,
                        'max_staff_positions': 15,
                        'api_access': True,
                        'priority_support': True,
                        'custom_branding': True
                    }
                },
                'enterprise': {
                    'price': 99.99,
                    'features': {
                        'max_tickets': -1,  # Unlimited
                        'max_staff_positions': -1,  # Unlimited
                        'api_access': True,
                        'priority_support': True,
                        'custom_branding': True,
                        'dedicated_support': True
                    }
                }
            })
        else:  # self_hosted
            return self.get('license_tiers', {
                'pro': {
                    'price': 49.99,
                    'features': {
                        'max_tickets': 1000,
                        'max_staff_positions': 15,
                        'api_access': True,
                        'priority_support': True
                    }
                },
                'enterprise': {
                    'price': 199.99,
                    'features': {
                        'max_tickets': 5000,
                        'max_staff_positions': 50,
                        'api_access': True,
                        'priority_support': True,
                        'dedicated_support': True
                    }
                },
                'unlimited': {
                    'price': 499.99,
                    'features': {
                        'max_tickets': -1,
                        'max_staff_positions': -1,
                        'api_access': True,
                        'priority_support': True,
                        'dedicated_support': True,
                        'source_code_access': True
                    }
                }
            })
    
    def get_feature_limits(self, tier: str) -> Dict[str, Any]:
        """Get feature limits for a specific tier"""
        tiers = self.get_subscription_tiers()
        return tiers.get(tier, {}).get('features', {})
    
    def create_example_configs(self):
        """Create example configuration files for both business models"""
        
        # Hosted service configuration
        hosted_config = {
            "business_model": "hosted",
            "bot_token": "YOUR_BOT_TOKEN_HERE",
            "database": {
                "use_mariadb": True,
                "host": "localhost",
                "port": 3306,
                "user": "hyperticky_user",
                "password": "your_secure_password",
                "database": "hyperticky_hosted"
            },
            "stripe": {
                "secret_key": "sk_test_your_stripe_secret_key",
                "webhook_secret": "whsec_your_webhook_secret",
                "success_url": "https://your-domain.com/success",
                "cancel_url": "https://your-domain.com/cancel"
            },
            "subscription_tiers": self.get_subscription_tiers(),
            "features": {
                "trial_duration_days": 7,
                "auto_cleanup_closed_tickets": True,
                "usage_analytics": True
            }
        }
        
        # Self-hosted configuration
        self_hosted_config = {
            "business_model": "self_hosted",
            "bot_token": "YOUR_BOT_TOKEN_HERE",
            "guild_id": "YOUR_GUILD_ID_HERE",
            "license_key": "YOUR_LICENSE_KEY_HERE",
            "license_server": {
                "url": "https://license.hyperticky.com",
                "timeout": 30,
                "cache_duration": 3600
            },
            "database": {
                "use_mariadb": False,
                "sqlite_path": "data/hyperticky.db"
            },
            "roles": {
                "admin": "ADMIN_ROLE_ID",
                "moderator": "MODERATOR_ROLE_ID",
                "support": "SUPPORT_ROLE_ID"
            },
            "channels": {
                "tickets": "TICKET_CHANNEL_ID",
                "reports": "REPORTS_CHANNEL_ID",
                "applications": "APPLICATIONS_CHANNEL_ID",
                "suggestions": "SUGGESTIONS_CHANNEL_ID",
                "logs": "LOGS_CHANNEL_ID"
            },
            "categories": {
                "tickets": "TICKET_CATEGORY_ID",
                "reports": "REPORTS_CATEGORY_ID",
                "applications": "APPLICATIONS_CATEGORY_ID"
            },
            "features": {
                "auto_cleanup_closed_tickets": True,
                "ticket_transcripts": True,
                "statistics_auto_update": True
            }
        }
        
        # Create config directory if it doesn't exist
        os.makedirs('config', exist_ok=True)
        
        # Write configuration files
        with open('config/hosted_config.json5', 'w', encoding='utf-8') as f:
            json5.dump(hosted_config, f, indent=2, quote_keys=True)
        
        with open('config/self_hosted_config.json5', 'w', encoding='utf-8') as f:
            json5.dump(self_hosted_config, f, indent=2, quote_keys=True)
        
        print("✅ Created example configuration files:")
        print("  - config/hosted_config.json5")
        print("  - config/self_hosted_config.json5")

# Usage example
if __name__ == "__main__":
    config_manager = ConfigManager()
    config_manager.create_example_configs()