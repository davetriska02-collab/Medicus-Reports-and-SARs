# SAR Redact — The Easy Install Guide

*Written for normal humans. No IT knowledge needed. No admin rights needed.
If you can copy a folder and double-click a file, you can do this.*

---

## What you need

- A Windows PC at the practice (any normal NHS machine is fine)
- The SAR Redact zip file (from the download link or a USB stick)
- 10 minutes the first time. After that it starts in seconds.

You do **not** need: admin rights, IT to install anything, an internet
account, or any technical knowledge.

---

## Part 1 — First-time install (do this once)

### Step 1: Put the folder somewhere permanent

1. Find the SAR Redact zip file (probably in your **Downloads** folder)
2. Right-click it → **Extract All…** → click **Extract**
3. You now have a folder called something like `sar-redact`
4. **Copy that whole folder to your C: drive.** Open File Explorer, click
   **This PC** → **Windows (C:)**, and paste it there. Rename it to
   `SAR Redact` if you like.

> ⚠️ **This bit matters.** Don't run it from Downloads, don't run it from
> your Desktop if your Desktop lives on a network drive (lots of NHS
> machines do this — if your files have an address starting with `\\`,
> that's a network drive). The C: drive always works.

### Step 2: Double-click `start_server.bat`

1. Open your `C:\SAR Redact` folder
2. Find the file called **start_server** (it has a cog-like icon)
3. Double-click it

A black window appears with green text. **This is normal. This is the
program.** Don't close it.

If Windows shows a blue "Windows protected your PC" box: click
**More info**, then **Run anyway**. (It says that about anything it hasn't
seen before.)

### Step 3: Wait for the one-time setup

The first run downloads what it needs — takes **3–8 minutes** depending on
your connection. You'll see progress messages like `[1/4] Installing…`.
Make a cup of tea.

When it's done you'll see a box like this:

```
==========================================================
  SAR Redact v2.3.0 — My Surgery
==========================================================
  Local:    http://localhost:5000
  ...
```

**That means it's working.** Every run after this one skips straight here
in a few seconds.

> 💬 **Saw an error about downloads being blocked?** Your practice's
> internet filtering is blocking it. No problem — skip to
> **"Plan B: the USB stick install"** at the bottom of this guide.

### Step 4: Open it in your browser

1. Open Chrome or Edge
2. Type this in the address bar exactly: `localhost:5000`
3. Press Enter

### Step 5: Create the admin account

The first screen asks you to create an admin account. This is YOUR account
— pick a username, your name, and a password (8+ characters).

**Write the password down somewhere safe.** There is no "forgot password"
email — this thing doesn't use the internet, that's the whole point.
(If the admin password is truly lost: close the black window, delete the
file `C:\SAR Redact\data\users.json`, start again — you'll be asked to
create a new admin account. Your SARs are NOT lost, only the user accounts.)

Then go to **Settings** in the top menu and fill in your practice name and
address — they appear on the letters the system generates.

**That's it. You're installed.** Add your GP colleagues under
**Users → Add user**.

---

## Part 2 — Daily use

1. Double-click **start_server** in `C:\SAR Redact` (a few seconds to start)
2. Browser → `localhost:5000`
3. **Leave the black window open while you work.** Minimise it, ignore it,
   just don't close it — closing it stops SAR Redact.
4. Finished for the day? Close the black window. Nothing is lost.

---

## Part 3 — One computer for the whole practice (recommended)

Instead of everyone installing it, put SAR Redact on **one** PC and let
everyone use it from their own desk in a browser. Nothing gets installed on
anyone else's machine.

1. Pick the PC. Ideally one that's on all day (a back-office machine is
   perfect). Do Part 1 on that machine.
2. In the `C:\SAR Redact` folder, double-click **install_as_server**
3. That's it. From now on SAR Redact starts itself whenever that PC is
   logged in, restarts itself if it ever crashes, and creates a file called
   **CONNECT.txt** in the folder.
4. Open **CONNECT.txt**. It contains the address everyone else uses —
   something like:

   ```
   http://RECEPTION-PC2:5000
   ```

5. Email that address to your colleagues. They type it into their browser,
   log in with the account you made them, and bookmark it. Done.

> 💡 **Set up backups** (2 minutes, do it): log in as admin → **Settings**
> → set *Backup folder* to a folder on your practice's shared drive, e.g.
> `\\practice-server\backups\sarredact`. SAR Redact then backs itself up
> every night automatically and keeps the last 7 copies.

---

## Plan B: the USB stick install (when downloads are blocked)

Some practices' internet filtering blocks the first-time download. The fix
is the **offline bundle** — a single zip with everything already inside.

**On any computer with normal internet** (home computer is fine):

1. Get the offline bundle zip (ask whoever gave you SAR Redact for the
   *offline* version, or a techier colleague can build it with one command
   — it's in the manual)
2. Copy the zip onto a USB stick or send it to your NHS email

**On the practice machine:**

1. Copy the zip to the C: drive, right-click → **Extract All…**
2. Double-click **start_server** inside the extracted folder
3. It starts in seconds — no downloads, no internet, nothing to install

Everything else (Steps 4–5, daily use, server setup) is identical.

---

## When something looks wrong

| What you see | What it means | What to do |
|---|---|---|
| Black window flashes and disappears | It hit an error before it could show it | Run it again — the window now stays open and shows the error. Match it below. |
| `UNC paths are not supported` | The folder is on a network drive | Copy the folder to `C:\` and run it from there (Part 1, Step 1) |
| `ERROR: Python download failed` | Internet filtering is blocking the setup download | Use **Plan B** above |
| `Port 5000 is already in use` | SAR Redact is already running (maybe minimised), or had a previous copy | Look in the taskbar for an existing black window and use that. Still stuck? Restart the PC. |
| Browser says "can't reach this page" | The black window isn't running | Start it (double-click **start_server**) and try again |
| Colleagues can't reach the server address | Their machine can't see the server PC, or it's asleep | Check the server PC is on and the black window is running. Check they typed the address from CONNECT.txt exactly. |
| "Windows protected your PC" | Windows being cautious about a new program | **More info** → **Run anyway** |
| Asked to create an admin account again | The user accounts file is missing | If this is unexpected, restore `data\users.json` from your backup before anyone creates a new account |

---

## The three rules

1. **Keep the folder on the C: drive.** Don't move it while it's running.
2. **The black window IS the program.** Minimise it, never close it
   mid-work.
3. **Set the backup folder in Settings.** Two minutes now versus a very bad
   day later.

*Need more detail (HTTPS, server options, technical troubleshooting)? See
[`INSTALL.md`](INSTALL.md).*
