"""Store or read the DeepSeek credential using the Mac's login keychain."""
from pathlib import Path
import platform
import subprocess
import tempfile


def helper_path():
    if platform.system() != 'Darwin':
        raise ValueError('The DeepSeek keychain preset requires macOS. Use the configurable API backend on other platforms.')
    return Path.home() / '.cache' / 'codex-paper-pdf-to-html' / 'helpers' / 'deepseek-keychain'


def setup_key():
    helper = helper_path()
    if not helper.is_file():
        helper.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=helper.parent) as directory:
            candidate = Path(directory) / helper.name
            source = Path(__file__).with_name('deepseek_keychain.m')
            sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk')
            sdk_flags = ['-isysroot', str(sdk)] if sdk.is_dir() else []
            result = subprocess.run(['/usr/bin/clang', *sdk_flags, '-O2', '-fobjc-arc',
                                     '-mmacosx-version-min=14.0', str(source), '-framework',
                                     'AppKit', '-framework', 'Security', '-o', str(candidate)], check=False)
            if result.returncode:
                raise ValueError('Could not build the Mac keychain helper.')
            candidate.chmod(0o700)
            candidate.replace(helper)
    status = subprocess.run([str(helper), 'save'], check=False).returncode
    if status == 2:
        print('DeepSeek setup was canceled.')
        return
    if status == 3:
        raise ValueError('The API key is blank or has invalid characters.')
    if status:
        raise ValueError('The Mac keychain could not save the API key.')
    print('DeepSeek API key saved to the Mac keychain.')


def load_key():
    helper = helper_path()
    if not helper.is_file():
        raise ValueError('Set up DeepSeek with the reader’s deepseek-setup command first.')
    try:
        result = subprocess.run([str(helper), 'get'], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=45, check=False)
    except subprocess.TimeoutExpired:
        raise ValueError('The Mac keychain did not return the DeepSeek key in time.') from None
    if result.returncode == 6:
        raise ValueError('The Mac keychain has no DeepSeek API key. Run deepseek-setup first.')
    if result.returncode or not result.stdout:
        raise ValueError('The Mac keychain could not read the DeepSeek API key.')
    try:
        key = result.stdout.decode('ascii')
    except UnicodeDecodeError:
        raise ValueError('The stored DeepSeek key has invalid characters. Run deepseek-setup again.') from None
    if any(character.isspace() or not character.isprintable() for character in key):
        raise ValueError('The stored DeepSeek key has invalid characters. Run deepseek-setup again.')
    return key
