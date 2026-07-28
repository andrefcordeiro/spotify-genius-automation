# Spotify/Genius Automation

Spotify Genius is a lightweight command-line tool that automatically opens the Genius lyrics page for the song currently playing on Spotify desktop app.

Currently working on Windows and Linux.

## Install as pip package

```
pip install spotify-genius
```

## How to download

Go to [releases](https://github.com/andrefcordeiro/spotify-genius-automation/releases) and download the latest version.

## Hot to run by yourself

### Requirements

- Python >=3.10

### Steps

1. Install dependencies

```
pip install .
```

2. Run

```
spotify-genius
```

### Linux browser window behavior

On Linux, Genius pages open in a dedicated browser profile so the first song opens a separate window and later songs open as tabs in that same window. This is supported for Chrome, Chromium, Brave, Edge, Vivaldi, and Firefox. If no supported browser is found, the app falls back to the system browser opener.

You can choose the browser command with `SPOTIFY_GENIUS_BROWSER` and the profile directory with `SPOTIFY_GENIUS_BROWSER_PROFILE`.

## How to generate the windows .exe

### Requirements

- Python >=3.10

### Steps

1. Install [PyInstaller](https://pyinstaller.org/en/stable/).

```
pip install pyinstaller
```

2. In the root folder of the project, run

```
pip install .
pyinstaller --clean --onefile --icon=assets/spotify-genius.ico --name spotify-genius-win --collect-all pywin32 --paths src src/spotify_genius/main.py
```

The binary `spotify-genius-win.exe` will be created in `dist`.

## How to generate linux executable

### Requirements

- Python >=3.10

### Steps

1. Install [PyInstaller](https://pyinstaller.org/en/stable/).

```
pip install pyinstaller
```

2. In the root folder of the project, run

```
pyinstaller --onefile --name spotify-genius-linux src/spotify_genius/main.py
```

The executable will be created in `dist`.
