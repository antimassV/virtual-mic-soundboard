# Quick Start Guide for Publishing

## What's Been Prepared

Your soundboard is now ready for GitHub and distribution! Here's what's been set up:

### Files Created:
- ✅ `README.md` - Comprehensive documentation
- ✅ `LICENSE` - MIT License
- ✅ `.gitignore` - Git ignore rules
- ✅ `install.sh` - Universal installer (Ubuntu/Fedora/Arch)
- ✅ `uninstall.sh` - Clean uninstaller
- ✅ `build_appimage.sh` - AppImage builder
- ✅ `setup_github.sh` - GitHub deployment helper
- ✅ `.github/workflows/release.yml` - Automated CI/CD

### Git Repository:
- ✅ Initialized with all files
- ✅ Initial commit created
- ✅ Ready to push to GitHub

## Publishing to GitHub

### Option 1: Automated (Recommended)

```bash
./setup_github.sh
```

This script will:
1. Check if you have GitHub CLI installed
2. Authenticate with GitHub (if needed)
3. Create the repository
4. Push your code
5. Give you next steps

### Option 2: Manual

1. **Create repository on GitHub:**
   - Go to https://github.com/new
   - Name: `virtual-mic-soundboard`
   - Don't initialize with README
   - Click "Create repository"

2. **Push your code:**
   ```bash
   git remote add origin https://github.com/antimassV/virtual-mic-soundboard.git
   git push -u origin main
   ```

## Creating a Release with AppImage

### Option 1: Automated with GitHub Actions

```bash
# Tag the release
git tag v1.0.1
git push origin v1.0.1
```

GitHub Actions will automatically:
- Build the AppImage
- Create a release
- Upload the AppImage as an asset

### Option 2: Manual Build

```bash
# Build AppImage locally
./build_appimage.sh

# Create release on GitHub
gh release create v1.0.1 VirtualMicSoundboard-*.AppImage \
  --title "Virtual Mic Soundboard v1.0.1" \
  --notes "Release v1.0.1"
```

### Option 3: Manual Upload

1. Build locally: `./build_appimage.sh`
2. Go to your repo → Releases → "Create a new release"
3. Tag: `v1.0.1`
4. Upload `VirtualMicSoundboard-1.0.1-x86_64.AppImage`
5. Publish release

## Using on Other Devices

Once published, anyone (including you on other devices) can install with:

### Quick Install:
```bash
curl -fsSL https://raw.githubusercontent.com/antimassV/virtual-mic-soundboard/main/install.sh | bash
```

### AppImage (Portable):
```bash
# Download from releases
wget https://github.com/antimassV/virtual-mic-soundboard/releases/latest/download/VirtualMicSoundboard-x86_64.AppImage

# Make executable and run
chmod +x VirtualMicSoundboard-x86_64.AppImage
./VirtualMicSoundboard-x86_64.AppImage
```

## Updating the README

Before publishing, update these placeholders in `README.md`:
- Replace `antimassV` with your GitHub username
- Update the repository URL
- Add screenshots if desired

## Next Steps

1. Run `./setup_github.sh` to publish
2. Build and release AppImage
3. Share the repository URL
4. Install on your other devices!

## Troubleshooting

### GitHub CLI not installed?
```bash
# Ubuntu/Debian
sudo apt install gh

# Fedora
sudo dnf install gh

# Arch
sudo pacman -S github-cli
```

### AppImage build fails?
Make sure you have:
- `wget` installed
- Internet connection (downloads appimagetool)
- Python 3.8+ and pip

### Need help?
Check the main README.md or create an issue on GitHub!
