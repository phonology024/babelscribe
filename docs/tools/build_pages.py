"""Build the SEO guide pages in docs/ from the PAGES table below: python docs/tools/build_pages.py"""
import html
import json
from pathlib import Path

BASE = "https://phonology024.github.io/babelscribe/"
DOCS = Path(__file__).resolve().parents[1]

CSS = """:root{--bg:#f7f8fb;--fg:#141a2b;--mut:#5a6378;--line:#e3e6ee;--acc:#0b7fc7;--code:#eef2f8}
@media (prefers-color-scheme:dark){:root{--bg:#0f1422;--fg:#e8ecf5;--mut:#9aa4bb;--line:#263049;--acc:#5ac8ff;--code:#1d2640}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.65 system-ui,-apple-system,"Segoe UI","Noto Sans Thai",sans-serif}
main{max-width:780px;margin:0 auto;padding:36px 16px 64px}a{color:var(--acc)}h1{font-size:1.75rem;line-height:1.25}h2{margin-top:2em;font-size:1.25rem}
.lead{color:var(--mut);font-size:1.08rem}pre{background:var(--code);padding:14px 16px;border-radius:10px;overflow-x:auto;font-size:.9rem}
code{font-family:ui-monospace,Consolas,monospace}p code,li code,td code{background:var(--code);padding:1px 5px;border-radius:5px}
table{border-collapse:collapse;width:100%;font-size:.95rem}td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left}
.nav{font-size:.95rem}.foot{color:var(--mut);margin-top:3em;font-size:.9rem}"""


def page(slug, lang, title, desc, h1, lead, body, faq):
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "TechArticle", "headline": h1, "description": desc, "inLanguage": lang, "url": BASE + slug,
         "author": {"@type": "Person", "name": "phonology024"}, "dateModified": "2026-10-10",
         "about": {"@type": "SoftwareApplication", "name": "babelscribe", "url": BASE}},
        {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q,
                                            "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}]}
    faq_html = "".join(f"<h3>{html.escape(q)}</h3><p>{html.escape(a)}</p>" for q, a in faq)
    faq_title = "คำถามที่พบบ่อย" if lang == "th" else "FAQ"
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="{BASE}{slug}"><link rel="icon" href="icon.png">
<meta property="og:title" content="{html.escape(title)}"><meta property="og:description" content="{html.escape(desc)}">
<meta property="og:url" content="{BASE}{slug}"><meta property="og:image" content="{BASE}icon.png">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script><style>{CSS}</style></head>
<body><main><p class="nav"><a href="./">babelscribe</a> · <a href="https://github.com/phonology024/babelscribe">GitHub</a></p>
<h1>{html.escape(h1)}</h1><p class="lead">{lead}</p>{body}<h2>{faq_title}</h2>{faq_html}
<p class="foot">babelscribe is free and open source (MIT) · <a href="privacy.html">Privacy</a></p></main></body></html>"""


PAGES = [
    ("whisper-amd-gpu-windows.html", "en",
     "How to run Whisper on an AMD GPU on Windows (no ROCm, no CUDA) — babelscribe",
     "Run OpenAI Whisper speech-to-text on an AMD Radeon GPU on Windows in two commands. Vulkan build of whisper.cpp, "
     "no ROCm, no CUDA, no compiling.",
     "How to run Whisper on an AMD Radeon GPU on Windows",
     "Short answer: <code>pip install babelscribe</code>, then <code>babelscribe video.mp4</code>. It downloads a Vulkan "
     "build of whisper.cpp that runs on Radeon cards — no ROCm, no CUDA, no Visual Studio.",
     """<h2>Why Whisper is hard on AMD + Windows</h2>
<p>Most Whisper tools (openai-whisper, faster-whisper, WhisperX) use PyTorch or CTranslate2 with CUDA, so on a Radeon card they fall back to the CPU. ROCm on Windows covers only some cards and some libraries. whisper.cpp does run on AMD through <b>Vulkan</b>, but its official releases ship no Windows Vulkan binary, so you would normally install the Vulkan SDK and Visual Studio and compile it yourself.</p>
<h2>Two-command setup</h2>
<pre><code>pip install babelscribe
babelscribe "my video.mp4"            # writes my video.srt and my video.json
babelscribe devices                   # shows which GPUs Vulkan sees</code></pre>
<p>On first run babelscribe downloads a prebuilt <code>whisper-cli</code> (Vulkan, AVX2-compatible) and the <code>large-v3-turbo</code> model (~1.6 GB), then picks your discrete Radeon over the integrated GPU automatically. Use <code>--device N</code> to choose another card.</p>
<h2>How fast is it?</h2>
<table><tr><th>GPU</th><th>Audio</th><th>Time</th><th>Speed</th></tr><tr><td>AMD Radeon RX 9070 XT (Vulkan)</td><td>19.3 min TED talk</td><td>48 s</td><td>~24x real time</td></tr></table>
<p>Accuracy on that talk: 1.5% word error rate against the human captions. Use <code>--accurate</code> (large-v3 with beam search) when you want fewer errors and can wait about twice as long.</p>
<h2>Other formats and languages</h2>
<pre><code>babelscribe talk.mp4 -f srt,vtt,txt,json   # all outputs
babelscribe talk.mp4 -l ja                 # force Japanese (default: auto-detect)
babelscribe talk.mp4 --accurate            # fewest errors</code></pre>""",
     [("Does Whisper work on AMD GPUs?",
       "Yes. whisper.cpp runs on AMD Radeon GPUs through Vulkan on Windows and Linux. babelscribe downloads a prebuilt "
       "Vulkan build so you don't have to compile it."),
      ("Do I need ROCm to run Whisper on a Radeon card?",
       "No. The Vulkan backend works with the normal AMD Adrenalin driver; ROCm is not needed."),
      ("Which AMD cards are supported?",
       "Any card with a Vulkan 1.2+ driver should work; it has been tested on an RX 9070 XT. Reports for other cards are "
       "welcome on GitHub."),
      ("Can I use it without the command line?",
       "Yes: add babelscribe to Claude Desktop, Claude Code, Codex, Gemini CLI or Cursor as an MCP server and ask for "
       "subtitles in chat.")]),
    ("thai-speech-to-text.html", "th",
     "ถอดเสียงภาษาไทยเป็นข้อความและทำซับไทยฟรี แม่นยำ ใช้การ์ดจอในเครื่อง — babelscribe",
     "ถอดเสียงภาษาไทยจากวิดีโอหรือไฟล์เสียงเป็นข้อความและซับ SRT ฟรี ไม่ต้องอัปโหลด ใช้การ์ดจอ AMD NVIDIA Intel หรือ Mac "
     "แม่นกว่า Whisper ปกติเกือบเท่าตัวด้วย Pathumma Whisper",
     "ถอดเสียงภาษาไทยเป็นข้อความ ฟรี แม่นยำ ทำงานในเครื่อง",
     "คำตอบสั้นๆ: <code>pip install babelscribe</code> แล้วสั่ง <code>babelscribe คลิป.mp4 -l th --accurate</code> "
     "จะได้ไฟล์ซับ <code>.srt</code> ภาษาไทยข้างไฟล์วิดีโอ ไม่มีการอัปโหลดไฟล์ไปไหน",
     """<h2>แม่นแค่ไหน</h2>
<p>วัดบนชุดทดสอบ FLEURS ของ Google (ภาษาไทย 50 ประโยค) ด้วยอัตราความผิดพลาดระดับตัวอักษร (CER) ยิ่งน้อยยิ่งดี</p>
<table><tr><th>โมเดล</th><th>CER</th></tr>
<tr><td>Whisper large-v3-turbo (ค่าเริ่มต้น)</td><td>15.9%</td></tr>
<tr><td>Whisper large-v3</td><td>11.5%</td></tr>
<tr><td>Typhoon Whisper</td><td>11.9%</td></tr>
<tr><td>Thonburian Whisper (<code>--text-model thai-thonburian</code>)</td><td>9.1%</td></tr>
<tr><td><b>Pathumma Whisper ของ NECTEC (<code>--accurate</code>)</b></td><td><b>8.9%</b></td></tr></table>
<p>กับคลิป TEDxBangkok ยาว 14 นาทีที่พูดเร็วและมีศัพท์วัยรุ่น ความผิดพลาดลดจาก 22.7% เหลือ 16.4%</p>
<h2>ทำไมแม่นขึ้น</h2>
<p>โมเดลที่ฝึกเฉพาะภาษาไทยสะกดคำไทยได้ดีกว่ามาก แต่มักบอกเวลาของแต่ละช่วงไม่ได้ babelscribe จึงใช้ <b>โหมดไฮบริด</b> คือเอาข้อความจาก Pathumma Whisper แล้วเอาเวลาจาก Whisper turbo มาจับคู่กันทีละตัวอักษร และตัดซับเฉพาะตรงรอยต่อคำ (ใช้ pythainlp) จะได้ไม่มีคำไทยขาดกลางคำ</p>
<h2>ใช้งาน</h2>
<pre><code>pip install babelscribe
babelscribe คลิป.mp4 -l th              # เร็ว
babelscribe คลิป.mp4 -l th --accurate   # แม่นที่สุด (ช้ากว่า)
babelscribe คลิป.mp4 -l th -f srt,txt   # ได้ทั้งซับและข้อความล้วน</code></pre>
<p>ไม่อยากพิมพ์คำสั่ง: ติดตั้ง babelscribe ใน Claude Desktop แล้วพิมพ์ในแชทว่า “ทำซับไทยให้คลิปล่าสุดในโฟลเดอร์ดาวน์โหลด” ได้เลย</p>""",
     [("ถอดเสียงภาษาไทยฟรีโปรแกรมไหนแม่นที่สุด",
       "จากการวัดบน FLEURS ของ Google การใช้ Pathumma Whisper ของ NECTEC ผ่าน babelscribe --accurate ได้ CER 8.9% "
       "เทียบกับ Whisper turbo ปกติที่ 15.9%"),
      ("ต้องมีการ์ดจอ NVIDIA ไหม",
       "ไม่ต้อง ใช้ได้กับการ์ด AMD Radeon, Intel Arc, NVIDIA และ Mac (Apple Silicon) หรือใช้ CPU ก็ได้แต่ช้ากว่า"),
      ("ไฟล์ถูกอัปโหลดไปที่ไหนไหม", "ไม่ ทุกอย่างทำงานในเครื่องของคุณเอง ดาวน์โหลดแค่โปรแกรมและโมเดลครั้งแรก"),
      ("ทำซับไทยให้คลิป YouTube หรือ TikTok ได้ไหม",
       "ได้ ถ้ามีไฟล์วิดีโอในเครื่อง babelscribe จะสร้างไฟล์ .srt ที่นำไปอัปโหลดเป็นคำบรรยายได้ทันที")]),
    ("free-offline-subtitles.html", "en",
     "Generate SRT subtitles from a video for free, offline, in 99 languages — babelscribe",
     "Create SRT or VTT subtitles from any video or audio file for free and offline with Whisper on your own GPU "
     "(AMD, NVIDIA, Intel, Apple). No upload, no account.",
     "Generate SRT subtitles from a video — free and offline",
     "Short answer: <code>pip install babelscribe</code>, then <code>babelscribe video.mp4 -f srt</code>. You get "
     "<code>video.srt</code> next to the video, made on your own computer.",
     """<h2>Steps</h2>
<pre><code>pip install babelscribe              # Python 3.9+, Windows / Linux / macOS
babelscribe lecture.mp4 -f srt       # -> lecture.srt (language auto-detected)
babelscribe lecture.mp4 -f srt,vtt   # also WebVTT for web players
babelscribe lecture.mp4 --accurate   # fewer errors, slower</code></pre>
<p>Any format ffmpeg reads works as input: mp4, mkv, mov, webm, mp3, wav, m4a and more (ffmpeg is bundled). Long recordings are safe: babelscribe disables Whisper's context carry-over, which prevents the classic “same sentence repeated forever” bug on long files.</p>
<h2>Why offline</h2>
<p>Online subtitle generators upload your video, often limit length, and charge per minute. babelscribe runs OpenAI's Whisper model on your own GPU — AMD Radeon and Intel Arc via Vulkan, NVIDIA via Vulkan or CUDA, Apple Silicon via Metal — so private recordings never leave your machine and there are no limits.</p>
<h2>Accuracy</h2>
<p>On Google FLEURS, error rates with <code>--accurate</code> include English 5.7%, Spanish 4.2%, German 4.0%, Japanese 5.7% (CER) and Korean 3.9% (CER). The full 16-language table is in the <a href="https://github.com/phonology024/babelscribe#benchmark-16-languages-on-fleurs">README</a>.</p>""",
     [("How do I make subtitles for a video for free?",
       "Install babelscribe with pip and run babelscribe video.mp4 -f srt. It creates video.srt using Whisper on your own "
       "computer, free and without uploading the video."),
      ("Can I generate subtitles without uploading my video?",
       "Yes. babelscribe runs entirely offline after downloading the model once."),
      ("Which subtitle formats are supported?", "SRT, WebVTT, plain text and JSON with word timings."),
      ("Which languages can it subtitle?", "All 99 languages Whisper supports, with automatic language detection.")]),
    ("mcp-transcribe-audio-video.html", "en",
     "MCP server to transcribe audio and video with Claude, Codex or Gemini CLI — babelscribe",
     "Add a local speech-to-text MCP server to Claude Desktop, Claude Code, Codex, Gemini CLI or Cursor. Transcribe "
     "audio and video into SRT subtitles on your own GPU, offline.",
     "A speech-to-text MCP server for Claude, Codex and Gemini CLI",
     "Short answer: run <code>uvx babelscribe mcp</code> as a local MCP server. Your AI app can then find a video on your "
     "computer, transcribe it on your own GPU and write <code>.srt</code> subtitles next to it — nothing is uploaded.",
     """<h2>Install</h2>
<pre><code># Claude Code
claude mcp add babelscribe -- uvx babelscribe mcp
# OpenAI Codex CLI
codex mcp add babelscribe -- uvx babelscribe mcp
# Claude Desktop: download babelscribe.mcpb from the GitHub releases and double-click it</code></pre>
<p>For Gemini CLI, Cursor, Google Antigravity and VS Code, add <code>{"command": "uvx", "args": ["babelscribe", "mcp"]}</code> to the app's MCP config; the <a href="https://github.com/phonology024/babelscribe#use-it-from-an-ai-app-mcp--no-terminal-needed">README</a> has the exact file for each app.</p>
<h2>Tools</h2>
<table><tr><th>Tool</th><th>What it does</th></tr>
<tr><td><code>transcribe</code></td><td>Audio or video file to subtitles (SRT, VTT) and text, 99 languages</td></tr>
<tr><td><code>find_media</code></td><td>Finds the newest audio/video in Downloads, Videos, Desktop</td></tr>
<tr><td><code>list_devices</code></td><td>Shows the GPUs available</td></tr>
<tr><td><code>list_languages_and_models</code></td><td>Lists languages, models and fine-tunes</td></tr></table>
<h2>Try it</h2>
<p>Ask in plain words: “make Thai subtitles for the newest video in my Downloads”, then “proofread the names” or “translate to English”. Set the tool timeout to 3600 seconds for long videos (Codex defaults to 60 s).</p>""",
     [("Is there an MCP server for speech to text?",
       "Yes. babelscribe is a local MCP server (uvx babelscribe mcp) that transcribes audio and video with Whisper on your own GPU."),
      ("Can Claude transcribe a video on my computer?",
       "Yes. Add babelscribe as an MCP server in Claude Desktop (one-click .mcpb) or Claude Code, then ask for subtitles in chat."),
      ("Does it upload my files?", "No. Transcription runs locally; there is no telemetry and no cloud call."),
      ("Can I use it from ChatGPT or Grok on the web?",
       "No. Web chat apps can only reach servers on the internet, not your computer. Use Claude Desktop, Claude Code, Codex CLI, Gemini CLI or Cursor.")]),
    ("faster-whisper-alternative-amd-intel-gpu.html", "en",
     "faster-whisper alternative for AMD and Intel GPUs — babelscribe",
     "faster-whisper and WhisperX need an NVIDIA GPU for GPU speed. babelscribe runs Whisper on AMD Radeon, Intel Arc, "
     "NVIDIA and Apple GPUs through whisper.cpp, no CUDA.",
     "A faster-whisper alternative that uses your AMD or Intel GPU",
     "Short answer: faster-whisper is excellent on NVIDIA. If your GPU is AMD Radeon, Intel Arc or Apple Silicon, "
     "<code>pip install babelscribe</code> gives you GPU-speed Whisper through whisper.cpp (Vulkan / Metal) with no CUDA.",
     """<h2>Comparison</h2>
<table><tr><th></th><th>babelscribe</th><th>faster-whisper / WhisperX</th></tr>
<tr><td>GPU support</td><td>Vulkan (AMD, Intel, NVIDIA), CUDA, Metal (Apple), CPU</td><td>NVIDIA CUDA; otherwise CPU</td></tr>
<tr><td>Windows setup</td><td><code>pip install babelscribe</code>; prebuilt whisper-cli downloaded for you</td><td>pip, plus CUDA / cuDNN for GPU</td></tr>
<tr><td>Video in, subtitles out</td><td>Yes, ffmpeg bundled; SRT, VTT, TXT, JSON</td><td>Yes (library; you write the glue)</td></tr>
<tr><td>Better Thai / Hindi text</td><td>Yes, <code>--accurate</code> (hybrid fine-tune + turbo timing)</td><td>Manual</td></tr>
<tr><td>AI-app integration</td><td>MCP server for Claude, Codex, Gemini CLI, Cursor</td><td>Third-party wrappers</td></tr></table>
<p>If you have an NVIDIA card and like Python APIs, faster-whisper is a fine choice. babelscribe does not replace it; it covers the GPUs it does not. Speed: about 20x real time on an AMD Radeon RX 9070 XT (19-minute talk in 48 s).</p>
<pre><code>pip install babelscribe
babelscribe interview.mp4 -f srt</code></pre>""",
     [("Is there a faster-whisper alternative for AMD GPUs?",
       "Yes. babelscribe runs Whisper through whisper.cpp with Vulkan, which works on AMD Radeon and Intel Arc GPUs."),
      ("Does faster-whisper work on AMD?",
       "Its GPU path targets NVIDIA CUDA; on AMD it runs on the CPU. babelscribe uses the AMD GPU through Vulkan."),
      ("Is babelscribe as accurate as faster-whisper?",
       "Both run the same Whisper models, so base accuracy is comparable. babelscribe adds an --accurate mode with language-specific fine-tunes for Thai and Hindi.")]),
    ("whisper-cpp-vulkan-prebuilt-windows.html", "en",
     "whisper.cpp Vulkan build for Windows, prebuilt, no compiling — babelscribe",
     "Official whisper.cpp releases ship no Windows Vulkan build. babelscribe downloads a prebuilt whisper-cli with Vulkan "
     "for AMD, Intel and NVIDIA GPUs and wraps it with ffmpeg and models.",
     "A prebuilt whisper.cpp Vulkan build for Windows",
     "Short answer: skip the Vulkan SDK and CMake. <code>pip install babelscribe</code> fetches a prebuilt Vulkan "
     "<code>whisper-cli</code> for your system and runs it for you.",
     """<h2>What it handles</h2>
<ul><li>Downloads a prebuilt <code>whisper-cli</code> (Windows / Linux Vulkan, Linux CUDA, macOS Metal, CPU) from this project's releases.</li>
<li>Converts any media to 16 kHz WAV with bundled ffmpeg; whisper.cpp itself only reads WAV.</li>
<li>Picks the discrete GPU over the integrated one (<code>babelscribe devices</code>, <code>--device N</code>).</li>
<li>Uses <code>--max-context 0</code> so long files do not loop on one sentence.</li></ul>
<p>Already have your own build? <code>babelscribe talk.mp4 --bin /path/to/whisper-cli</code>. Self-host the binaries with <code>BABELSCRIBE_RELEASES</code>.</p>
<pre><code>pip install babelscribe
babelscribe devices
babelscribe talk.mp4</code></pre>""",
     [("Does whisper.cpp have a Windows Vulkan release?", "The official releases do not ship a Windows Vulkan build. babelscribe publishes prebuilt Vulkan binaries and downloads the right one."),
      ("Do I need the Vulkan SDK?", "No. You only need a GPU driver with Vulkan support, which AMD, Intel and NVIDIA drivers include."),
      ("Can I use my own whisper.cpp build?", "Yes, pass --bin /path/to/whisper-cli.")]),
    ("hindi-speech-to-text.html", "en",
     "Hindi speech-to-text and subtitles, free and offline — babelscribe",
     "Transcribe Hindi audio and video to text and SRT offline. --accurate cuts the word error rate from 28.4% to 12.6% on "
     "Google FLEURS using the vasista22 fine-tune.",
     "Hindi speech-to-text and subtitles, free and offline",
     "Short answer: <code>babelscribe video.mp4 -l hi --accurate</code>. Plain Whisper turbo misses a lot of Hindi; "
     "the community fine-tune used by <code>--accurate</code> brings it to 12.6% word error rate.",
     """<h2>Accuracy on Google FLEURS (Hindi, 50 utterances)</h2>
<table><tr><th>Setup</th><th>WER</th></tr><tr><td>Whisper large-v3-turbo (default)</td><td>28.4%</td></tr>
<tr><td><b>--accurate</b>: vasista22/whisper-hindi-large-v2 + turbo timing</td><td><b>12.6%</b></td></tr>
<tr><td>--accurate, ignoring extra words at clip edges</td><td>11.1%</td></tr></table>
<p>The fine-tune is by vasista22 (Speech Lab, IIT Madras). Install the converter once with <code>pip install "babelscribe[finetune]"</code>; weights are converted on your machine, never redistributed.</p>
<pre><code>pip install babelscribe
babelscribe lecture.mp4 -l hi --accurate -f srt,txt</code></pre>""",
     [("What is the best free Hindi speech-to-text?", "On Google FLEURS, babelscribe --accurate with the vasista22 Hindi fine-tune reaches 12.6% WER versus 28.4% for plain Whisper turbo."),
      ("Does it work offline?", "Yes. After the one-time model download everything runs on your computer."),
      ("Can I get Hindi subtitles for a video?", "Yes, add -f srt to get a .srt file next to the video.")]),
    ("private-offline-transcription.html", "en",
     "Private, offline transcription: interviews, meetings, lectures — babelscribe",
     "Transcribe sensitive audio and video on your own computer. No account, no telemetry, no cloud: audio never leaves "
     "your machine. Free and open source (MIT).",
     "Transcribe private recordings without uploading them",
     "Short answer: <code>pip install babelscribe</code> and transcribe locally. There is no account, no telemetry and no "
     "upload; after downloading the model once it works without internet.",
     """<h2>What leaves your computer</h2>
<p>Nothing from your recordings. The only network use is downloading the whisper program from GitHub releases, models from Hugging Face and packages from PyPI. Full text: <a href="privacy.html">privacy policy</a>.</p>
<h2>Good for</h2>
<ul><li>Interviews and journalism, legal or medical notes, internal meetings, lecture recordings.</li>
<li>Files too long or too numerous for per-minute cloud pricing.</li></ul>
<p>Used from an AI app via MCP, the transcript text is returned to that app, so its own privacy policy applies to the text; the audio still stays local.</p>
<pre><code>pip install babelscribe
babelscribe meeting.m4a -f txt,srt</code></pre>""",
     [("Is there a free offline transcription tool?", "Yes. babelscribe is free (MIT) and runs OpenAI Whisper on your own GPU or CPU."),
      ("Does babelscribe send my audio anywhere?", "No. It has no telemetry or accounts and never uploads audio, video or transcripts."),
      ("Does it need internet?", "Only for the first download of the program and model.")]),
    ("thai-subtitles-claude-desktop.html", "th",
     "ทำซับไทยด้วย Claude Desktop โดยไม่ต้องพิมพ์คำสั่ง — babelscribe",
     "ติดตั้ง babelscribe ใน Claude Desktop ด้วยการดับเบิลคลิกไฟล์เดียว แล้วสั่งในแชทให้ทำซับไทยหรือถอดเสียงคลิปในเครื่อง ฟรี ไม่อัปโหลดไฟล์",
     "ทำซับไทยด้วย Claude Desktop ไม่ต้องพิมพ์คำสั่ง",
     "คำตอบสั้นๆ: โหลด <code>babelscribe.mcpb</code> จากหน้า Releases บน GitHub แล้วดับเบิลคลิก จากนั้นพิมพ์ในแชทว่า “ทำซับไทยให้คลิปล่าสุดในโฟลเดอร์ดาวน์โหลด”",
     """<h2>ขั้นตอน</h2>
<ol><li>ดาวน์โหลด <code>babelscribe.mcpb</code> จาก <a href="https://github.com/phonology024/babelscribe/releases/latest">GitHub Releases</a></li>
<li>ดับเบิลคลิก หรือเปิด Claude Desktop → Settings → Extensions → Install extension</li>
<li>พิมพ์ในแชท เช่น “ทำซับไทยให้คลิปล่าสุดใน Downloads” แล้ว Claude จะหาไฟล์ ถอดเสียงด้วยการ์ดจอของคุณ และบันทึก <code>.srt</code> ไว้ข้างไฟล์</li>
<li>สั่งต่อได้ เช่น “ตรวจชื่อคนให้หน่อย” หรือ “แปลซับเป็นอังกฤษ”</li></ol>
<p>ใช้ Claude Code ได้เหมือนกัน: <code>claude mcp add babelscribe -- uvx babelscribe mcp</code> ภาษาไทยให้เลือกโหมดแม่นยำสูง (Pathumma Whisper ของ NECTEC, CER 8.9% บน FLEURS) ดูรายละเอียดที่ <a href="thai-speech-to-text.html">ถอดเสียงภาษาไทย</a></p>""",
     [("ทำซับไทยด้วย Claude ได้ไหม", "ได้ ติดตั้ง babelscribe เป็น MCP ใน Claude Desktop แล้วสั่งในแชท Claude จะถอดเสียงคลิปในเครื่องของคุณให้"),
      ("ไฟล์วิดีโอถูกอัปโหลดไหม", "ไม่ การถอดเสียงทำงานในเครื่องของคุณ ไม่มีการอัปโหลดไฟล์เสียงหรือวิดีโอ"),
      ("ใช้ ChatGPT หรือ Grok บนเว็บได้ไหม", "ไม่ได้ เพราะแอปเว็บเข้าถึงได้เฉพาะเซิร์ฟเวอร์บนอินเทอร์เน็ต ไม่ใช่คอมพิวเตอร์ของคุณ ให้ใช้ Claude Desktop, Claude Code, Codex CLI, Gemini CLI หรือ Cursor")]),
]

if __name__ == "__main__":
    for slug, *rest in PAGES:
        (DOCS / slug).write_text(page(slug, *rest), encoding="utf-8")
    urls = [BASE, BASE + "privacy.html"] + [BASE + p[0] for p in PAGES]
    (DOCS / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc><lastmod>2026-10-10</lastmod></url>\n" for u in urls) + "</urlset>\n",
        encoding="utf-8")
    print("built", len(PAGES), "pages")
