#!/usr/bin/env python3
"""
InstaChatBot Startup Script
Tự động setup và khởi chạy bot với validation đầy đủ
"""

import os
import sys
import subprocess
import time
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️  python-dotenv not installed, skipping .env file loading")
    print("💡 Install with: pip install python-dotenv")

def check_python_version():
    """Kiểm tra Python version"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ required!")
        print(f"Current version: {sys.version}")
        return False
    print(f"✅ Python version: {sys.version}")
    return True

def install_requirements():
    """Cài đặt requirements"""
    print("📦 Checking requirements...")
    
    try:
        # Kiểm tra requirements.txt
        if not os.path.exists('requirements.txt'):
            print("❌ requirements.txt not found!")
            return False
        
        # Cài đặt requirements
        print("📥 Installing requirements...")
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            print("❌ Failed to install requirements!")
            print(result.stderr)
            return False
        
        print("✅ Requirements installed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error installing requirements: {str(e)}")
        return False

def create_directories():
    """Tạo các thư mục cần thiết"""
    print("📁 Creating directories...")
    
    directories = [
        'monitoring',
        'security', 
        'analytics',
        'utils',
        'config',
        'memories',
        'temp_memories_backup',
        'chromium_temp_data_dir'
    ]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"✅ Created: {directory}")
    
    return True

def validate_files():
    """Kiểm tra các file cần thiết"""
    print("🔍 Validating files...")
    
    required_files = [
        'app.py',
        'core.py',
        'image_generator.py',
        'llm_memories_manager.py',
        'monitoring/performance_monitor.py',
        'monitoring/error_handler.py',
        'security/security_manager.py',
        'security/session_manager.py',
        'analytics/analytics_engine.py',
        'analytics/conversation_insights.py',
        'utils/cache_manager.py',
        'utils/notification_system.py',
        'config/config_manager.py'
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
        else:
            print(f"✅ Found: {file_path}")
    
    if missing_files:
        print("❌ Missing files:")
        for file_path in missing_files:
            print(f"   - {file_path}")
        return False
    
    print("✅ All required files found!")
    return True

def check_api_key():
    """Kiểm tra API key"""
    print("🔑 Checking API key...")
    
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ GEMINI_API_KEY not found in environment")
        print("💡 Solutions:")
        print("   1. Create .env file from env_example")
        print("   2. Set environment: set GEMINI_API_KEY=your_key")
        print("   3. Get API key from: https://makersuite.google.com/app/apikey")
        return False
    
    if len(api_key) < 30:
        print("⚠️ API key seems too short")
        return False
    
    print("✅ API key found!")
    return True

def check_instagram_credentials():
    """Kiểm tra Instagram credentials"""
    print("📱 Checking Instagram credentials...")
    
    username = os.getenv('INSTAGRAM_USERNAME')
    password = os.getenv('INSTAGRAM_PASSWORD')
    target = os.getenv('TARGET_USERNAME')
    
    missing = []
    if not username:
        missing.append('INSTAGRAM_USERNAME')
    if not password:
        missing.append('INSTAGRAM_PASSWORD')
    if not target:
        missing.append('TARGET_USERNAME')
    
    if missing:
        print(f"❌ Missing credentials: {', '.join(missing)}")
        print("💡 Solutions:")
        print("   1. Create .env file from env_example")
        print("   2. Set environment variables:")
        for var in missing:
            print(f"      set {var}=your_value")
        return False
    
    print("✅ Instagram credentials found!")
    return True

def validate_config():
    """Validate configuration"""
    print("⚙️ Validating configuration...")
    
    try:
        # Import config manager
        sys.path.append('.')
        from config.config_manager import get_config_manager
        
        config_manager = get_config_manager()
        
        # Validate each config
        config_types = ['app', 'ai', 'security', 'monitoring', 'cache']
        for config_type in config_types:
            is_valid, errors = config_manager.validate_config(config_type)
            if is_valid:
                print(f"✅ {config_type} config valid")
            else:
                print(f"⚠️ {config_type} config issues: {errors}")
        
        return True
        
    except Exception as e:
        print(f"⚠️ Config validation error: {str(e)}")
        return True  # Non-critical

def test_imports():
    """Test critical imports"""
    print("🧪 Testing imports...")
    
    critical_imports = [
        ('selenium', 'selenium'),
        ('google.generativeai', 'google-generativeai'),
        ('psutil', 'psutil'),
        ('cryptography', 'cryptography'),
        ('requests', 'requests')
    ]
    
    failed_imports = []
    for module_name, package_name in critical_imports:
        try:
            __import__(module_name)
            print(f"✅ {module_name}")
        except ImportError:
            failed_imports.append(package_name)
            print(f"❌ {module_name}")
    
    if failed_imports:
        print(f"❌ Failed imports: {failed_imports}")
        print("💡 Try: pip install " + " ".join(failed_imports))
        return False
    
    print("✅ All imports successful!")
    return True

def setup_environment():
    """Setup environment variables"""
    print("🌍 Setting up environment...")
    
    # Set default environment variables if not exist
    env_vars = {
        'PYTHONPATH': '.',
        'PYTHONUNBUFFERED': '1'
    }
    
    for var, value in env_vars.items():
        if not os.getenv(var):
            os.environ[var] = value
            print(f"✅ Set {var}={value}")
    
    return True

def show_startup_info():
    """Hiển thị thông tin khởi động"""
    print("\n" + "="*50)
    print("🤖 INSTACHATBOT STARTUP")
    print("="*50)
    print(f"📍 Working directory: {os.getcwd()}")
    print(f"🐍 Python: {sys.executable}")
    print(f"⏰ Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50 + "\n")

def run_bot():
    """Chạy bot chính"""
    print("🚀 Starting InstaChatBot...")
    
    try:
        # Import và chạy bot
        sys.path.append('.')
        
        # Import app module
        import app
        
        print("✅ Bot started successfully!")
        print("📱 Bot is now running...")
        print("⏹️ Press Ctrl+C to stop")
        
        # Bot sẽ chạy trong app.py
        
    except KeyboardInterrupt:
        print("\n⏹️ Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Bot error: {str(e)}")
        return False
    
    return True

def main():
    """Main function"""
    show_startup_info()
    
    # Validation steps
    steps = [
        ("Python Version", check_python_version),
        ("Create Directories", create_directories),
        ("Install Requirements", install_requirements),
        ("Validate Files", validate_files),
        ("Test Imports", test_imports),
        ("Check API Key", check_api_key),
        ("Check Instagram Credentials", check_instagram_credentials),
        ("Setup Environment", setup_environment),
        ("Validate Config", validate_config)
    ]
    
    print("🔧 VALIDATION STEPS:")
    print("-" * 30)
    
    for step_name, step_func in steps:
        print(f"\n📋 {step_name}...")
        if not step_func():
            print(f"❌ {step_name} failed!")
            print("🛑 Startup aborted!")
            return False
    
    print("\n" + "="*50)
    print("✅ ALL VALIDATIONS PASSED!")
    print("="*50)
    
    # Chạy bot
    return run_bot()

if __name__ == "__main__":
    try:
        success = main()
        if success:
            print("\n✅ Bot completed successfully!")
        else:
            print("\n❌ Bot failed!")
            sys.exit(1)
    except Exception as e:
        print(f"\n💥 Critical error: {str(e)}")
        sys.exit(1) 