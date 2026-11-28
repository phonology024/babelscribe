# If something goes wrong

Back to the [README](../README.md). The messages below are the ones babelscribe prints, in a terminal, in the desktop app
and in the answer an AI app gets. Start with `babelscribe doctor`: it downloads nothing, lists what babelscribe found
(Python, memory, ffmpeg, whisper-cli, GPUs, free disk space) and ends with a report you can paste into an
[issue](https://github.com/phonology024/babelscribe/issues).

## Downloads
The first run downloads `whisper-cli` from GitHub and a speech model from Hugging Face (1.6 GB for the default, `turbo`).

**"the download of ... was interrupted (...); trying again ..."**
Nothing to do. babelscribe asks again for the part that is missing, as long as new bytes keep arriving.

**"the download of ... stopped: ... Check the internet connection."**
Several attempts in a row brought nothing. What arrived is kept (the message says how much): run the same command again,
or press the button again in the app, and it continues from there. This also holds after Ctrl+C, *Cancel* or a shutdown.
Behind a proxy, set `HTTPS_PROXY`.

**"... the server's certificate could not be checked ..."**
babelscribe never skips this check. On Windows it also tries once more using only the system's trusted root
certificates, because an outdated certificate in Windows' intermediate store can make a good server fail. If it still
stops: check the computer's date and time, and whether a company proxy or an antivirus "HTTPS scanning" feature sits in
between.

**"checksum mismatch, nothing was installed"**
The file that arrived is not the one this version was tested with, and it was deleted. Run it again. If it repeats,
something on the way is changing downloads (a proxy, or the sign-in page of a public Wi-Fi). For `whisper-cli` you can
also build [whisper.cpp](https://github.com/ggml-org/whisper.cpp) yourself and pass `--bin PATH/whisper-cli`.

**"could not write ... free some disk space"** (or "could not install ... The download is kept")
The disk is full or the folder cannot be written to. Free some space and run it again; what was downloaded is not
fetched twice. Everything is under `~/.babelscribe` (`BABELSCRIBE_HOME` moves it, `BABELSCRIBE_MODELS` moves only the
models).

**"another babelscribe is downloading ...; waiting for it ..."**
The app, a terminal or an AI app is already fetching the same file. This one continues when that one is done.

## Running
**"... needs about N GB of free memory ... it may run very slowly or stop"**, or **"low memory: ... using small instead"**
Close other programs, or pick the smaller model the message names (`-m small`). What each model needs:
[memory.md](memory.md).

**"whisper-cli failed (...)"**
The lines after it are whisper-cli's own. Update the graphics driver first. To find out whether the GPU is the cause,
run the file once on the CPU: `babelscribe FILE --flavor cpu` (slower; not on Apple Silicon).

**It is much slower than expected**
`babelscribe doctor` (or `babelscribe devices`) shows which GPU is used. With none listed, update the graphics driver;
with several, `--device N` chooses.

**"this computer has no Vulkan library (libvulkan1) ... the CPU build is used"** (Linux)
`sudo apt install libvulkan1`, or your distribution's Vulkan loader package, then run babelscribe again.

**"no font for ... text was found on this computer"** (burning subtitles into a video)
Install one of the fonts the message names, or give one you have with `--font "Name"`.

**"no audio or video files found (use -r to look in sub-folders)"**
The folder holds no media at its top level: add `-r`.

## Translation
**"no local LLM answered (...)"**
Translating into languages other than English uses a model running on your computer. Start Ollama, LM Studio,
llama-server or colibri, then try again (*Check again* in the app), or give its address with `--llm`.
`babelscribe llms` shows which ports answer.

## AI apps
**"... has a mistake in it (...), so babelscribe left it exactly as it is"**
The app's settings file cannot be read. Fix the line the message names, or press *Copy* (`babelscribe connect show APP`)
and add the entry yourself.

**"This OpenCode is older than version 2."**
babelscribe connects OpenCode with a command that version 2 added. Update OpenCode, or use *Copy*.

**The AI app does not show babelscribe**
Quit the app completely and open it again. `babelscribe connect status` shows what each app's settings say.

**An AI app stops waiting during a long video**
Its tool time limit is too short. Connect sets a long one where the app has such a setting; if you added babelscribe by
hand, see the [README](../README.md#use-it-from-an-ai-app-mcp--no-terminal-needed).
