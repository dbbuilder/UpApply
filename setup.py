#!/usr/bin/env python3
"""
Setup script for Upwork Automation Tool

Installs dependencies and sets up the environment for the tool.
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

def run_command(command, description):
    """Run a command and handle errors"""
    print(f"📦 {description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed:")
        print(f"Error: {e.stderr}")
        return False

def check_python_version():
    """Check if Python version is 3.9 or higher"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 9):
        print(f"❌ Python 3.9+ required, but found {version.major}.{version.minor}")
        return False
    print(f"✅ Python {version.major}.{version.minor}.{version.micro} detected")
    return True

def create_virtual_environment():
    """Create virtual environment if it doesn't exist"""
    venv_path = Path("venv")
    if venv_path.exists():
        print("✅ Virtual environment already exists")
        return True
    
    return run_command(f"{sys.executable} -m venv venv", "Creating virtual environment")

def get_pip_command():
    """Get the appropriate pip command for the current platform"""
    if platform.system() == "Windows":
        return "venv\\Scripts\\pip"
    else:
        return "venv/bin/pip"

def get_python_command():
    """Get the appropriate python command for the current platform"""
    if platform.system() == "Windows":
        return "venv\\Scripts\\python"
    else:
        return "venv/bin/python"

def install_dependencies():
    """Install Python dependencies"""
    pip_cmd = get_pip_command()
    
    # Upgrade pip first
    if not run_command(f"{pip_cmd} install --upgrade pip", "Upgrading pip"):
        return False
    
    # Install requirements
    if not run_command(f"{pip_cmd} install -r requirements.txt", "Installing Python dependencies"):
        return False
    
    return True

def install_playwright():
    """Install Playwright browsers"""
    python_cmd = get_python_command()
    
    return run_command(f"{python_cmd} -m playwright install", "Installing Playwright browsers")

def create_directories():
    """Create necessary directories"""
    directories = [
        "data",
        "data/cover_letters", 
        "logs",
        "screenshots"
    ]
    
    for directory in directories:
        path = Path(directory)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            print(f"📁 Created directory: {directory}")
    
    print("✅ Directory structure created")
    return True

def setup_environment_file():
    """Create .env file template if it doesn't exist"""
    env_file = Path(".env")
    if env_file.exists():
        print("✅ .env file already exists")
        return True
    
    env_template = """# OpenAI API Key (required)
OPENAI_API_KEY=your-openai-api-key-here

# Optional: Upwork credentials for auto-login
UPWORK_EMAIL=your-upwork-email@example.com

# Optional: Logging level override
LOG_LEVEL=INFO

# Optional: Browser settings override
BROWSER_HEADLESS=false
"""
    
    try:
        with open(env_file, 'w') as f:
            f.write(env_template)
        print("✅ Created .env template file")
        print("⚠️  Please edit .env file with your OpenAI API key")
        return True
    except Exception as e:
        print(f"❌ Failed to create .env file: {e}")
        return False

def test_installation():
    """Test that the installation works"""
    python_cmd = get_python_command()
    
    print("🧪 Testing installation...")
    try:
        # Test import of main modules
        test_command = f"{python_cmd} -c \"from src.config import get_config; from src.cli import cli; print('✅ All modules imported successfully')\""
        result = subprocess.run(test_command, shell=True, check=True, capture_output=True, text=True)
        print(result.stdout.strip())
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Installation test failed: {e.stderr}")
        return False

def main():
    """Main setup function"""
    print("🚀 Setting up Upwork Automation Tool...")
    print("=" * 50)
    
    # Check Python version
    if not check_python_version():
        sys.exit(1)
    
    # Create virtual environment
    if not create_virtual_environment():
        sys.exit(1)
    
    # Install dependencies
    if not install_dependencies():
        sys.exit(1)
    
    # Install Playwright browsers
    if not install_playwright():
        print("⚠️  Playwright installation failed, but you can install it manually later")
        print("   Run: python -m playwright install")
    
    # Create directories
    if not create_directories():
        sys.exit(1)
    
    # Setup environment file
    if not setup_environment_file():
        sys.exit(1)
    
    # Test installation
    if not test_installation():
        print("⚠️  Installation test failed, but setup is complete")
    
    print("\n" + "=" * 50)
    print("🎉 Setup completed successfully!")
    print("\n📋 Next steps:")
    print("1. Edit .env file with your OpenAI API key")
    print("2. Activate virtual environment:")
    
    if platform.system() == "Windows":
        print("   venv\\Scripts\\activate")
    else:
        print("   source venv/bin/activate")
    
    print("3. Test the tool:")
    print("   python main.py --help")
    print("4. Start using:")
    print("   python main.py refresh")
    print("   python main.py list")
    print("   python main.py apply 1,2,3")

if __name__ == "__main__":
    main()
