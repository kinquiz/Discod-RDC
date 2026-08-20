# Discord Rich Presence Client

A little Python CLI app that lets you control your Discord Rich Presence status ("Playing...", "Listening...", etc.) and change everything on the fly — no restarting the script every time you want to tweak something.

## What it does

- Connects to your local Discord app via `pypresence` (Discord's IPC protocol).
- Lets you freely edit: Details/State text, activity type (Playing/Listening/Watching/Competing), large & small images with hover text, up to two link buttons, and a timer (elapsed or countdown).
- Every change goes live immediately — no restart needed.
- Save multiple presets to `presets.json` and switch between them whenever.
- Auto-reconnects if you close and reopen Discord while the script is running.
- Gives you clear error messages instead of cryptic tracebacks (Discord not running, bad Client ID, rejected asset, etc.).

## What you need

- Python 3.10+
- Discord desktop app running (Discord IPC only works locally — it won't show up if you're using Discord in a browser).

## Install

```bash
pip install -r requirements.txt
```

## Getting a Client ID

You need an "application" registered on Discord's side — it's free and takes a minute.

1. Go to https://discord.com/developers/applications and log in.
2. Click **New Application**, give it any name (this name isn't necessarily what shows up in your status — that depends on your assets/text).
3. On the app's page, under **General Information**, copy the **Application ID**. That's your `client_id`.
4. Drop it into `config.json`:

   ```json
   {
     "client_id": "1234567890123456789"
   }
   ```

   Or just run `python main.py` and set it through the **Settings** menu — it'll save it for you.

## Uploading images (assets)

Want a custom large/small image in your status? Here's how:

1. In the Developer Portal, open your app → **Rich Presence → Art Assets**.
2. Click **Add Image(s)** and upload a PNG/JPG (square images, at least 512×512, work best).
3. Each image gets a **key name** (like `large_logo`) — that key is what you type into the app's "Large image" / "Small image" fields, not a filename or URL.
4. Discord sometimes takes a few minutes to pick up new assets. If your image isn't showing, wait a bit and reconnect (there's a menu option for that).

### Using a direct URL instead

You can also just paste a direct `https://...` image link instead of an asset key. Support for this varies across Discord clients/versions and isn't guaranteed over RPC — if it doesn't show up, fall back to uploading it as an asset (see above).

## Running it

```bash
python main.py
```

If you haven't set a `client_id` yet, the app will point you to the Settings menu. Once connected, you get a menu where you can:

- edit status fields one at a time — each edit is sent to Discord right away;
- save your current setup as a named preset and switch between presets;
- manually reconnect (though it also reconnects automatically the next time it tries to send an update);
- clear your status or quit — both clear the Rich Presence in Discord.

## Project layout

```
main.py         — entry point, starts the CLI
config.py       — reads/writes config.json and presets.json
rpc_client.py   — wraps pypresence: connecting, reconnecting, sending updates
ui.py           — the CLI menu and field/preset editing logic
config.json     — app settings (Client ID)
presets.json    — your saved presets
requirements.txt
```

## Things Discord's RPC just won't do

- **Streaming** isn't a real option here — Discord only supports that activity type through its Gateway/streaming integrations, not over local RPC. You get Playing/Listening/Watching/Competing.
- Buttons: max two, and each needs a proper `http://` or `https://` link.
- Rich Presence only shows up in the desktop app — not on mobile, not in browser.
- If Discord isn't running, the app tells you and keeps going — just start Discord and try again from the menu.
