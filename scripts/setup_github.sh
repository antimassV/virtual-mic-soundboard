#!/bin/bash
# GitHub Setup and Release Script

echo "========================================="
echo "Virtual Mic Soundboard - GitHub Setup"
echo "========================================="
echo ""

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "GitHub CLI (gh) is not installed."
    echo "Install it with:"
    echo "  Ubuntu/Debian: sudo apt install gh"
    echo "  Fedora: sudo dnf install gh"
    echo "  Arch: sudo pacman -S github-cli"
    echo ""
    echo "Or visit: https://cli.github.com/"
    echo ""
    read -p "Continue with manual setup? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
    MANUAL_MODE=true
else
    MANUAL_MODE=false
fi

if [ "$MANUAL_MODE" = false ]; then
    # Automated setup with gh CLI
    echo "Checking GitHub authentication..."
    if ! gh auth status &> /dev/null; then
        echo "Please authenticate with GitHub:"
        gh auth login
    fi
    
    echo ""
    read -p "Enter repository name (default: virtual-mic-soundboard): " REPO_NAME
    REPO_NAME=${REPO_NAME:-virtual-mic-soundboard}
    
    read -p "Make repository public? (Y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        VISIBILITY="--private"
    else
        VISIBILITY="--public"
    fi
    
    echo ""
    echo "Creating GitHub repository..."
    gh repo create "$REPO_NAME" $VISIBILITY --source=. --remote=origin --push
    
    echo ""
    echo "Repository created and code pushed!"
    echo "URL: https://github.com/$(gh api user -q .login)/$REPO_NAME"
    
else
    # Manual setup
    echo "Manual Setup Instructions:"
    echo ""
    echo "1. Go to https://github.com/new"
    echo "2. Create a new repository (suggested name: virtual-mic-soundboard)"
    echo "3. Do NOT initialize with README, .gitignore, or license"
    echo "4. Copy the repository URL"
    echo ""
    read -p "Enter your GitHub repository URL (e.g., https://github.com/username/repo.git): " REPO_URL
    
    if [ -z "$REPO_URL" ]; then
        echo "No URL provided. Exiting."
        exit 1
    fi
    
    echo ""
    echo "Adding remote and pushing..."
    git remote add origin "$REPO_URL"
    git push -u origin main
    
    echo ""
    echo "Code pushed to GitHub!"
fi

echo ""
echo "========================================="
echo "Next Steps:"
echo "========================================="
echo ""
echo "1. Build AppImage locally:"
echo "   cd scripts"
echo "   chmod +x build_appimage.sh"
echo "   ./build_appimage.sh"
echo ""
echo "2. Create a release on GitHub:"
if [ "$MANUAL_MODE" = false ]; then
    echo "   gh release create v1.0.1 VirtualMicSoundboard-*.AppImage --title \"v1.0.1\" --notes \"Release v1.0.1\""
else
    echo "   - Go to your repository on GitHub"
    echo "   - Click 'Releases' → 'Create a new release'"
    echo "   - Tag: v1.0.1"
    echo "   - Upload the AppImage file"
fi
echo ""
echo "3. Or use GitHub Actions (automatic):"
echo "   git tag v1.0.1"
echo "   git push origin v1.0.1"
echo "   (This will automatically build and create a release)"
echo ""
